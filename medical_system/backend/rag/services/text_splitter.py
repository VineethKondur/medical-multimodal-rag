from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

def split_text(text: str):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=100
    )
    return splitter.create_documents([text])
