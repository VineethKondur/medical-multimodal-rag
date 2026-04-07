import os
import re
import json
from dotenv import load_dotenv
from groq import Groq
from django.core.cache import cache

load_dotenv()

_cached_client = None


def get_groq_client():
    global _cached_client
    if _cached_client is None:
        _cached_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    return _cached_client


# ════════════════════════════════════════════════════════════════════
# LEGACY: Single Test Explanation (Keep for backward compatibility)
# ══════════════════════════════════════════════════════════════════

def generate_test_explanation(test_name: str) -> str:
    """Explain a medical test with 1-day cache."""
    cache_key = f"explain_{test_name.lower()}"
    cached = cache.get(cache_key)

    if cached:
        return cached

    client = get_groq_client()

    prompt = f"""Explain the medical test: {test_name}

Rules:
- Keep it simple (2 lines max)
- Do NOT include values
- Do NOT assume patient condition
- Just explain what the test measures

Answer:"""

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )

    explanation = response.choices[0].message.content.strip()
    cache.set(cache_key, explanation, timeout=86400)  # 1 day cache

    return explanation


# ════════════════════════════════════════════════════════════════════
# 🆕 NEW: Flexible Lab Query Handler (Uses Actual Report Data)
# ══════════════════════════════════════════════════════════════════

def ask_about_lab_report(question: str, extracted_data: list[dict], llm_client=None) -> str:
    """
    Ask ANY question about lab results.
    
    LLM will use ONLY the data you provide (no hallucination).
    Works with ANY lab report type (CBC, LFT, Lipid, etc.)
    """
    
    if not extracted_data:
        return "⚠️ No laboratory data available."
    
    # Step 1: Prepare clean data context
    data_context = format_data_for_llm(extracted_data)
    
    # Step 2: Build smart prompt that prevents hallucination
    prompt = build_grounded_prompt(question, data_context)
    
    # Debug log
    print("\n" + "="*60)
    print(f"🔍 Question: {question}")
    print(f"📊 Data points: {len(extracted_data)}")
    print("="*60)
    
    # Step 3: Call LLM
    client = llm_client or get_groq_client()
    
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": GROUNDED_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=1000,
        )
        
        answer = response.choices[0].message.content.strip()
        
        print(f"✅ Response generated ({len(answer)} chars)")
        print("="*60 + "\n")
        
        return answer
    
    except Exception as e:
        print(f"❌ Error: {e}")
        return f"⚠️ Error generating response: {str(e)}"


def format_data_for_llm(data: list[dict]) -> str:
    """
    Convert extraction output to clean LLM-friendly format.
    Minimal processing - just structure the facts clearly.
    """
    
    lines = []
    
    # Summary stats
    total = len(data)
    abnormal = [t for t in data if t.get('flag')]
    normal_count = total - len(abnormal)
    
    lines.append("<LAB_REPORT_DATA>")
    lines.append(f"Parameters tested: {total} | Normal: {normal_count} | Abnormal: {len(abnormal)}")
    lines.append("")
    
    # Results table
    lines.append("<RESULTS>")
    for i, t in enumerate(data, 1):
        name = t.get('test', 'Unknown')
        value = t.get('value', '-')
        unit = t.get('unit', '')
        ref = t.get('range', '')
        flag = t.get('flag', '')
        
        line = f"{i}. {name}: {value}"
        if unit:
            line += f" {unit}"
        if ref and ref.lower() != 'n/a':
            line += f" (ref: {ref})"
        if flag:
            line += f" [{flag.upper()}]"
        
        lines.append(line)
    
    lines.append("</RESULTS>")
    
    # Raw JSON for precise parsing
    lines.append("")
    lines.append("<RAW_DATA>")
    lines.append(json.dumps(data, indent=2))
    lines.append("</RAW_DATA>")
    
    return "\n".join(lines)


GROUNDED_SYSTEM_PROMPT = """You are a clinical laboratory interpretation expert. You have DEEP knowledge of ALL medical tests (hematology, biochemistry, immunology, endocrinology, urinalysis, lipid profiles, coagulation, toxicology, etc.).

CRITICAL RULES:
1. **USE ONLY THE DATA PROVIDED** - Do NOT invent values, ranges, or test results
2. **If a test is not in the data**, say "Not measured in this report"
3. **Reference the user's actual values** when explaining
4. **Do NOT diagnose** - say "suggests", "consistent with", "may indicate"
5. **Flag dangerous findings clearly** (critically low platelets, very high WBC, etc.)
6. **Adapt your response style** to the question asked
7. **End with**: ⚕ *Consult your doctor for proper interpretation*

RESPONSE STYLE GUIDE:
- "explain all/define all" → List each test with 2-line definition + patient's value
- "what's wrong/worry" → Focus on abnormal values only, rank by severity
- "am I healthy?" → Nuanced assessment with caveats
- Comparison questions → Show numbers side-by-side
- "like I'm 5" → Use simple analogies
- Diet questions → Tie advice to specific abnormal values found"""


def build_grounded_prompt(question: str, data_context: str) -> str:
    """
    Build prompt that forces LLM to use provided data.
    Detects question type and tailors instructions.
    """
    
    q = question.lower().strip()
    
    # Detect question intent
    is_definition = any(kw in q for kw in ['explain all', 'define all', 'what are', 'tell me about', 'each test', 'meaning of', 'stand for'])
    is_abnormality = any(kw in q for kw in ['wrong', 'abnormal', 'concern', 'worry', 'problem', 'bad', 'issue', 'flagged', 'high', 'low', 'not normal'])
    is_health = any(kw in q for kw in ['healthy', 'normal', 'ok', 'fine', 'good', 'sick', 'ill', 'disease', 'overall', 'summary', 'assessment'])
    is_comparison = any(kw in q for kw in ['compare', 'difference', 'vs', 'versus', 'higher than', 'lower than', 'relationship', 'why is'])
    is_diet = any(kw in q for kw in ['eat', 'diet', 'food', 'nutrition', 'supplement', 'vitamin', 'lifestyle', 'avoid', 'take what'])
    is_simple = any(kw in q for kw in ["like i'm 5", "simple terms", "easy to understand", "plain english", "for a child", "eli5"])
    
    # Build instructions based on detected intent
    instructions = ""
    
    if is_definition:
        instructions = """TASK: Define EVERY test listed in <RESULTS>.
                        Format for EACH test:
                        **[Test Name]**
                        What it measures: [1 sentence]
                        Patient's result: [value] [unit] (Normal: [range]) [status]
                        Note: [If abnormal: brief significance]
                        Cover ALL tests. Be concise but complete."""
    
    elif is_abnormality:
        instructions = """TASK: Analyze ONLY abnormal values (marked HIGH or LOW).
                        For each abnormal finding:
                        1. **Test & Value**: What it is + patient's number
                        2. **Meaning**: Plain English
                        3. **Possible causes**: Top 3 common reasons (bulleted)
                        4. **Urgency**: 🔴 Immediate / 🟡 Soon / 🟢 Routine
                        Then give:
                        📋 OVERALL: [2-sentence pattern summary]
                        🎯 NEXT STEPS: [Bulleted action items]"""
    
    elif is_health:
        instructions = """TASK: Give nuanced health assessment.
                        Structure:
                        🏥 STATUS: [One sentence - e.g., "Mostly normal with X concerns"]
                        ✅ GOOD: [List normal findings]
                        ⚠️ CONCERNS: [Ranked abnormalities with brief note]
                        🔴 URGENT: [If any need immediate attention]
                        📝 LIMITATIONS: [What this report cannot show]
                        💡 ADVICE: [What to discuss with doctor]
                        Be balanced. Don't alarm unnecessarily."""
    
    elif is_comparison:
        instructions = """TASK: Compare specific values mentioned.
                        Show:
                        • Parameters compared
                        • Patient's actual numbers (side-by-side)
                        • Whether difference is clinically significant
                        • Physiological relationship (if relevant)
                        • What additional info would help"""
    
    elif is_diet:
        instructions = """TASK: Provide diet/lifestyle advice tied SPECIFICALLY to abnormal values found.
                        For each relevant abnormal value:
                        🍎 **[Test]: [Value]**
                        • Connection to nutrition
                        ✓ Eat: [2-3 foods]
                        ✗ Limit: [2-3 items]
                        ⏱️ Timeline: [When changes visible]
                        🥗 General wellness tips: [2-3 broad recommendations]
                        ⚕️ Note: Diet supports but doesn't replace treatment."""
    
    elif is_simple:
        instructions = """TASK: Explain like the patient is 5 years old.
                        Rules:
                        • Use analogies (blood cells = tiny trucks, body = city)
                        • Max 2 sentences per concept
                        • NO jargon without simple explanation
                        • Reassuring tone
                        • One takeaway message"""
    
    else:
        instructions = """TASK: Answer the user's specific question using ONLY the lab data provided.
                        Guidelines:
                        • Reference actual values from the data
                        • Use your expertise to interpret meaning
                        • Be concise but thorough
                        • Format for readability
                        • Include disclaimer at end"""
    
    # Assemble final prompt
    prompt = f"""{GROUNDED_SYSTEM_PROMPT}

{data_context}

═════════════════════════════════════════════════════
USER QUESTION: "{question}"
═════════════════════════════════════════════════════

{instructions}

Now respond based on the data above:"""
    
    return prompt


# ════════════════════════════════════════════════════════════════════
# CONVENIENCE WRAPPER (Easy integration)
# ════════════════════════════════════════════════════════════════════

def process_lab_query(question: str, lab_data_json: str) -> dict:
    """
    Main function to call from your API endpoint.
    
    Usage:
        result = process_lab_query("explain all tests", json_string_from_table_extractor)
        print(result['response'])
    """
    from datetime import datetime
    
    try:
        if isinstance(lab_data_json, str):
            data = json.loads(lab_data_json)
        else:
            data = lab_data_json
    except:
        return {'error': 'Invalid data format', 'response': ''}
    
    if not data:
        return {'error': 'No data', 'response': '⚠️ No lab data available'}
    
    response_text = ask_about_lab_report(question, data)
    
    return {
        'response': response_text,
        'question': question,
        'tests_count': len(data),
        'abnormal_count': len([t for t in data if t.get('flag')]),
        'timestamp': datetime.now().isoformat(),
    }