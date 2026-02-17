import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def generate_answer(context: str, question: str) -> str:
    prompt = f"""
You are an assistant that explains the content of documents clearly and in detail,
based strictly on the provided context.

Rules:
- Use ONLY the information present in the context.
- Answer it by giving a detailed explanation.
- Do NOT explain how you found the answer.
- Do NOT mention the context, document, or reasoning process.
- If the answer is not explicitly present, reply exactly with:
  "I cannot find the answer in the document."

Context:
{context}

Question:
{question}

Answer (detailed explanation):
"""

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    return response.choices[0].message.content.strip()
