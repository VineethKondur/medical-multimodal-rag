import os
from langchain_community.vectorstores import FAISS
from .embeddings import get_embedding_model

INDEX_PATH = "faiss_index"

_cached_vectorstore = None

def create_vectorstore(docs):
    global _cached_vectorstore
    embeddings = get_embedding_model()
    os.makedirs(INDEX_PATH,exist_ok=True)
    vectorstore = FAISS.from_documents(docs,embeddings)
    vectorstore.save_local(INDEX_PATH)
    _cached_vectorstore = vectorstore
    return vectorstore

def load_vectorstore():
    global _cached_vectorstore
    if not os.path.exists(INDEX_PATH):
        raise FileNotFoundError("FAISS index not found")
    if _cached_vectorstore:
        return _cached_vectorstore
    embeddings = get_embedding_model()
    _cached_vectorstore = FAISS.load_local(
        INDEX_PATH,
        embeddings,
        allow_dangerous_deserialization=True
    )
    return _cached_vectorstore

def clear_vectorstore_cache():
    global _cached_vectorstore
    _cached_vectorstore = None