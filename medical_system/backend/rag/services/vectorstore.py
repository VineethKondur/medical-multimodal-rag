import os
from langchain_community.vectorstores import FAISS
from .embeddings import get_embedding_model

# Persisted FAISS index location
INDEX_PATH = "faiss_index"

def create_vectorstore(docs):
    embeddings = get_embedding_model()

    # Ensure directory exists
    os.makedirs(INDEX_PATH, exist_ok=True)

    vectorstore = FAISS.from_documents(docs, embeddings)
    vectorstore.save_local(INDEX_PATH)

    return vectorstore


def load_vectorstore():
    if not os.path.exists(INDEX_PATH):
        raise FileNotFoundError("FAISS index not found. Upload a document first.")

    embeddings = get_embedding_model()

    return FAISS.load_local(
        INDEX_PATH,
        embeddings,
        allow_dangerous_deserialization=True  # safe: index created locally
    )