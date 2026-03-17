import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

# Cache the Groq client to avoid recreating it on every request
_cached_client = None

def get_groq_client():
    """Get or create cached Groq client singleton"""
    global _cached_client
    if _cached_client is None:
        _cached_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    return _cached_client


def generate_answer(context: str, question: str) -> str:
    print("LLM request started")

    client = get_groq_client()

    prompt = f"""
Answer the question using only the context below.

Context:
{context}

Question:
{question}

Answer:
"""

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )

    print("LLM response received")

    return response.choices[0].message.content.strip()
