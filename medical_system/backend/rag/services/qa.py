import os
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


# 🔥 SAFE LLM FOR GENERAL QUESTIONS
def generate_answer(context: str, question: str) -> str:
    client = get_groq_client()

    prompt = f"""
You are a medical assistant.

STRICT RULES:
- Answer ONLY using the given context
- If answer is not present → say "Not found in report"
- Do NOT guess
- Keep answers short and clear

Context:
{context}

Question:
{question}

Answer:
"""

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )

    return response.choices[0].message.content.strip()


# 🔥 NEW: EXPLAIN ANY TEST (WITH CACHE)
def generate_test_explanation(test_name: str) -> str:
    cache_key = f"explain_{test_name.lower()}"
    cached = cache.get(cache_key)

    if cached:
        return cached

    client = get_groq_client()

    prompt = f"""
Explain the medical test: {test_name}

Rules:
- Keep it simple (2 lines max)
- Do NOT include values
- Do NOT assume patient condition
- Just explain what the test measures

Answer:
"""

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )

    explanation = response.choices[0].message.content.strip()

    cache.set(cache_key, explanation, timeout=86400)  # 1 day cache

    return explanation