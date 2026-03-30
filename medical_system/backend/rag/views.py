from multiprocessing import context
import os
import uuid
import re
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework import status
from .services.pdf_loader import extract_text_from_pdf
from .services.table_extractor import extract_tables
from .services.text_splitter import split_text
from .services.vectorstore import create_vectorstore, load_vectorstore, clear_vectorstore_cache
from .services.qa import generate_answer, generate_test_explanation

MEDIA_DIR = "media"
os.makedirs(MEDIA_DIR, exist_ok=True)


# Fallback reference ranges for common medical tests
FALLBACK_RANGES = {
    "hemoglobin": "13.5-17.5",  # Adult male
    "hb": "13.5-17.5",
    "packed cell volume": "40-50",
    "pcv": "40-50",
    "rbc count": "4.5-5.5",
    "rbc": "4.5-5.5",
    "mcv": "80-100",
    "mch": "27-32",
    "mchc": "31.5-34.5",
    "wbc": "4.5-11.0",
    "tlc": "4.5-11.0",
    "platelet": "150-400",
    "rdw": "11-15",
}

def detect_status_with_fallback(test_name, value, ref_range):
    """
    Detect status with fallback ranges for common tests.
    Returns: (status, used_range_if_fallback)
    """
    # Try to use provided range first
    if ref_range:
        return detect_status(value, ref_range), None
    
    # Try to find fallback using test name
    test_lower = test_name.lower()
    for key, fallback_range in FALLBACK_RANGES.items():
        if key in test_lower:
            status = detect_status(value, fallback_range)
            return status, fallback_range
    
    # No fallback found
    return detect_status(value, ref_range), None

# 🔥 ABNORMAL DETECTION FUNCTION (CORRECT PLACEMENT)
import re

def detect_status(value, ref_range):
    """
    Detect if a lab value is within normal range (NORMAL, HIGH, or LOW).
    
    Args:
        value: The lab test value (as string or number)
        ref_range: Reference range (e.g., "4.0-5.5", ">10", "<200")
    
    Returns:
        Status string: "NORMAL", "HIGH", "LOW", or "UNKNOWN"
    """
    try:
        # Convert value to float
        try:
            value = float(str(value).strip())
        except ValueError:
            return "UNKNOWN"

        if not ref_range or ref_range.lower() in ["nan", "-", "", "not available"]:
            return "UNKNOWN"

        # Normalize reference range
        r = str(ref_range).lower().strip().replace(" ", "")
        
        # Extract all numbers from the reference range
        numbers = re.findall(r"(\d+\.?\d*)", r)
        
        if not numbers:
            return "UNKNOWN"

        try:
            # Handle range format: 4.0-5.5 or 4.0–5.5 or 4.0 - 5.5
            if re.search(r"[\-–]", r):
                if len(numbers) >= 2:
                    low = float(numbers[0])
                    high = float(numbers[1])
                    
                    if value < low:
                        return "LOW"
                    elif value > high:
                        return "HIGH"
                    else:
                        return "NORMAL"

            # Handle less than: < 200
            elif "<" in r:
                if numbers:
                    high = float(numbers[0])
                    if value > high:
                        return "HIGH"
                    else:
                        return "NORMAL"

            # Handle greater than: > 10
            elif ">" in r:
                if numbers:
                    low = float(numbers[0])
                    if value < low:
                        return "LOW"
                    else:
                        return "NORMAL"
                        
        except (ValueError, IndexError):
            return "UNKNOWN"

    except Exception as e:
        print(f"Status detection error for value={value}, range={ref_range}: {e}")

    return "UNKNOWN"


# Conversation History
def get_conversation_history(session_key):
    return cache.get(f"chat_history_{session_key}", [])


def add_to_conversation(session_key, role, content):
    history = get_conversation_history(session_key)
    history.append({
        "role": role,
        "content": content
    })
    if len(history) > 10:
        history = history[-10:]
    cache.set(f"chat_history_{session_key}", history, timeout=3600)


def clear_conversation(session_key):
    cache.delete(f"chat_history_{session_key}")


# Upload & Index PDF
@csrf_exempt
@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
def upload_and_index(request):

    if "file" not in request.FILES:
        return Response({"error": "No file uploaded"}, status=400)

    pdf = request.FILES["file"]

    unique_filename = f"{uuid.uuid4()}_{pdf.name}"
    file_path = os.path.join(MEDIA_DIR, unique_filename)

    with open(file_path, "wb") as f:
        for chunk in pdf.chunks():
            f.write(chunk)

    try:
        print("INDEXING PDF...")

        clear_vectorstore_cache()

        text = extract_text_from_pdf(file_path)
        table_text = extract_tables(file_path)
        print("\n===== TABLE TEXT DEBUG =====")
        # Table text loaded from cache
        print("===========================\n")

        cache.set("latest_table_data", table_text, timeout=3600)

        final_text = text + "\n\n" + table_text if table_text else text

        docs = split_text(final_text)
        create_vectorstore(docs)

        session_key = request.session.session_key or \
            request.META.get("REMOTE_ADDR", "default")

        clear_conversation(session_key)

        print("PDF INDEXED SUCCESSFULLY")

        return Response({"message": "PDF indexed successfully"})

    except Exception as e:
        print("INDEX ERROR:", e)
        return Response({"error": str(e)}, status=500)
@csrf_exempt
@api_view(["POST"])
@parser_classes([JSONParser])
def query_document(request):
    import re

    question = request.data.get("question", "").strip()
    if not question:
        return Response({"error": "Question is required"}, status=400)

    q = question.lower()

    session_key = request.session.session_key or request.META.get("REMOTE_ADDR", "default")
    history = get_conversation_history(session_key)

    # =========================
    # LOAD TABLE DATA
    # =========================
    table_text = cache.get("latest_table_data")
    table_rows = []

    if table_text:
        clean = table_text.replace("\n", " ")

        for chunk in clean.split("TABLE ROW →"):
            if not chunk.strip():
                continue

            try:
                parts = [p.strip() for p in chunk.split(",")]

                row = {"test": "", "value": "", "unit": "", "range": "", "status": "UNKNOWN"}

                for part in parts:
                    if ":" not in part:
                        continue

                    key, val = part.split(":", 1)
                    key = key.lower().strip()
                    val = val.strip()

                    if "test" in key:
                        row["test"] = val

                    elif "value" in key:
                        # Improved: Extract first number-like sequence, handle decimals and negatives
                        match = re.search(r"[-+]?(?:\d+\.?\d*|\.\d+)", val)
                        if match:
                            row["value"] = match.group()
                        else:
                            row["value"] = val

                    elif "unit" in key:
                        row["unit"] = val

                    elif "range" in key:
                        row["range"] = val

                # 🔥 FILTER BAD ROWS
                if "%" in row["unit"] and len(row["test"]) > 50:
                    continue

                if row["test"] and row["value"]:
                    status, used_range = detect_status_with_fallback(row["test"], row["value"], row["range"])
                    row["status"] = status
                    if used_range and not row["range"]:
                        row["range"] = used_range
                    
                    table_rows.append(row)

            except Exception as e:
                pass

    # =========================
    # CLEAN DATA
    # =========================
    
    unique = []
    seen = {}  # Changed from set to dict to store row data

    for r in table_rows:
        key = r["test"].lower().strip()
        
        # If we haven't seen this test, or if this row has a range and the previous didn't
        if key not in seen:
            seen[key] = r
            unique.append(r)
        elif r["range"] and not seen[key]["range"]:
            # Replace with version that has range
            # Recalculate status for the replacement row with its range
            new_status, _ = detect_status_with_fallback(r["test"], r["value"], r["range"])
            r["status"] = new_status
            idx = unique.index(seen[key])
            unique[idx] = r
            seen[key] = r
        else:
            # Skip duplicate (keep first or one with range)
            pass

    table_rows = unique

    # =========================
    # INTENT DETECTION
    # =========================
    def detect_intent(q):
        if any(w in q for w in ["meaning of all", "definition of all", "explain all", "what are all"]):
            return "DEFINITIONS"
        if any(w in q for w in ["table", "list", "all", "report", "full"]):
            return "FULL_TABLE"
        if any(w in q for w in ["abnormal", "high", "low", "issue"]):
            return "ABNORMAL"
        if any(w in q for w in ["summary", "summarize", "overall"]):
            return "SUMMARY"
        if any(w in q for w in ["what is", "meaning", "explain"]):
            return "EXPLANATION"
        return "TEST"

    # =========================
    # TEST EXTRACTION
    # =========================
    TEST_ALIASES = {
        "hemoglobin": ["hb", "haemoglobin"],
        "rbc": ["rbc count", "red blood cell"],
        "wbc": ["wbc count", "tlc", "white blood cell"],
        "platelet": ["platelet count", "platelets"]
    }

    def extract_tests(q):
        found = []
        for std, aliases in TEST_ALIASES.items():
            if std in q:
                found.append(std)
                continue
            for a in aliases:
                if a in q:
                    found.append(std)
                    break
        return list(set(found))

    intent = detect_intent(q)
    tests = extract_tests(q)

    # =========================
    # 1. FULL TABLE
    # =========================
    if intent == "FULL_TABLE":
        return Response({"type": "table", "data": table_rows, "history": history})

    # =========================
    # 2. ABNORMAL
    # =========================
    if intent == "ABNORMAL":
        abnormal = [r for r in table_rows if r["status"] in ["HIGH", "LOW"]]
        return Response({"type": "table", "data": abnormal, "history": history})

    # =========================
    # 3. SUMMARY
    # =========================
    if intent == "SUMMARY":
        abnormal = [r for r in table_rows if r["status"] in ["HIGH", "LOW"]]

        context = f"""
Abnormal values:
{abnormal}

Total tests: {len(table_rows)}
"""

        answer = generate_answer(context, question)

        return Response({"type": "text", "answer": answer, "history": history})

    # =========================
    # 3.5 DEFINITIONS (All Test Explanations)
    # =========================
    if intent == "DEFINITIONS":
        definitions = []
        for idx, row in enumerate(table_rows, 1):
            explanation = generate_test_explanation(row["test"])
            definitions.append({
                "number": idx,
                "test": row["test"],
                "value": row["value"],
                "unit": row["unit"],
                "status": row["status"],
                "definition": explanation
            })
        
        # Format as numbered, well-structured text with clear separation
        answer = ""
        for d in definitions:
            answer += f"\n{d['number']}. **{d['test']}**\n"
            answer += f"   (Value: {d['value']} {d['unit']} | Status: {d['status']})\n"
            answer += f"   {d['definition']}\n"
            answer += "\n" + "─" * 80 + "\n"
        
        return Response({"type": "text", "answer": answer.strip(), "history": history})

    # =========================
    # 4. HEALTH CHECK
    # =========================
    if "healthy" in q or "normal" in q:
        abnormal = [r for r in table_rows if r["status"] in ["HIGH", "LOW"]]

        if not abnormal:
            return Response({
                "type": "text",
                "answer": "All values are within normal range. Patient appears healthy.",
                "history": history
            })
        else:
            return Response({
                "type": "text",
                "answer": f"Patient has {len(abnormal)} abnormal values. Not fully normal.",
                "history": history
            })

    # =========================
    # 5. TEST QUERY (🔥 HYBRID RESPONSE)
    # =========================
    if tests:
        result = []

        for row in table_rows:
            for t in tests:
                if t in row["test"].lower():
                    result.append(row)
                    break

        if result:
            # 🔥 SINGLE TEST → explanation + value
            if len(result) == 1:
                row = result[0]

                explanation = generate_test_explanation(row["test"])

                answer = f"""
{explanation}

Value: {row['value']} {row['unit']}
Status: {row['status']}
"""

                return Response({
                    "type": "text",
                    "answer": answer.strip(),
                    "history": history
                })

            # 🔥 MULTI TEST → table
            return Response({
                "type": "table",
                "data": result,
                "history": history
            })

        return Response({
            "type": "text",
            "answer": "Requested tests not found",
            "history": history
        })

    # =========================
    # 6. LLM FALLBACK
    # =========================
    from .services.vectorstore import INDEX_PATH
    
    if os.path.exists(INDEX_PATH):
        try:
            vectorstore = load_vectorstore()
            docs = vectorstore.similarity_search(question, k=5)

            context = "\n\n".join(doc.page_content for doc in docs)

            answer = generate_answer(context, question)

            return Response({"type": "text", "answer": answer, "history": history})
        except Exception as e:
            print(f"Vector search failed: {e}")

    return Response({
        "type": "text",
        "answer": "Could not understand query",
        "history": history
    })


# UI
def ui(request):
    return render(request, "rag/index.html")