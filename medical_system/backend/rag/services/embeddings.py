from langchain_huggingface import HuggingFaceEmbeddings

# Cache the embedding model to avoid reloading on every request
_cached_embedding_model = None

def get_embedding_model():
    global _cached_embedding_model

    if _cached_embedding_model is None:
        _cached_embedding_model = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={"device": "cpu"},
            encode_kwargs={"batch_size": 64}
        )
    return _cached_embedding_model


def clear_embedding_cache():
    """Clear the cached embedding model"""
    global _cached_embedding_model
    _cached_embedding_model = None
