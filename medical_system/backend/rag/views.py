import os
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework import status
from .services.pdf_loader import extract_text_from_pdf
from .services.text_splitter import split_text
from .services.vectorstore import create_vectorstore, load_vectorstore, clear_vectorstore_cache
from .services.qa import generate_answer

MEDIA_DIR = "media"
os.makedirs(MEDIA_DIR, exist_ok=True)

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
        return Response(
            {"error": "No file uploaded"},
            status=status.HTTP_400_BAD_REQUEST
        )
    pdf = request.FILES["file"]
    file_path = os.path.join(MEDIA_DIR, pdf.name)
    with open(file_path, "wb") as f:
        for chunk in pdf.chunks():
            f.write(chunk)
    try:
        print("INDEXING PDF...")
        clear_vectorstore_cache()
        text = extract_text_from_pdf(file_path)
        docs = split_text(text)
        create_vectorstore(docs)
        session_key = request.session.session_key or \
        request.META.get("REMOTE_ADDR", "default")
        clear_conversation(session_key)
        print("PDF INDEXED SUCCESSFULLY")
        return Response({
            "message": "PDF indexed successfully"
        })
    except Exception as e:
        print("INDEX ERROR:", e)
        return Response({
            "error": str(e)
        }, status=500)

# Query Document
@csrf_exempt
@api_view(["POST"])
@parser_classes([JSONParser])

def query_document(request):
    question = request.data.get("question")
    if not question:
        return Response({
            "error": "Question is required"
        }, status=400)
    if not os.path.exists("faiss_index"):
        return Response({
            "error": "Upload a PDF first"
        }, status=400)
    try:
        session_key = request.session.session_key or \
        request.META.get("REMOTE_ADDR", "default")
        history = get_conversation_history(session_key)
        print("STEP 1: loading vectorstore")
        vectorstore = load_vectorstore()
        print("STEP 2: searching vectors")
        docs = vectorstore.similarity_search(question, k=2)
        if not docs:
            return Response({
                "answer": "No relevant info found",
                "history": history
            })
        print("STEP 3: building context")
        context = "\n\n".join(
            doc.page_content[:800]
            for doc in docs
        )
        print("STEP 4: calling LLM")
        answer = generate_answer(context, question)
        print("STEP 5: LLM finished")
        add_to_conversation(session_key, "user", question)
        add_to_conversation(session_key, "assistant", answer)
        return Response({
            "answer": answer,
            "history": get_conversation_history(session_key)
        })
    except Exception as e:
        print("QUERY ERROR:", e)
        return Response({
            "error": str(e)
        }, status=500)

# UI
def ui(request):
    return render(request, "rag/index.html")