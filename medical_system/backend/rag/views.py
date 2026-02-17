import os
from django.shortcuts import render
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework import status

# Import custom logic
from .services.pdf_loader import extract_text_from_pdf
from .services.text_splitter import split_text
from .services.vectorstore import create_vectorstore, load_vectorstore
from .services.qa import generate_answer

MEDIA_DIR = "media"
os.makedirs(MEDIA_DIR, exist_ok=True)

# API: Upload & Index PDF
@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
def upload_and_index(request):
    if "file" not in request.FILES:
        return Response({"error": "No file uploaded"}, status=status.HTTP_400_BAD_REQUEST)

    pdf = request.FILES["file"]
    file_path = os.path.join(MEDIA_DIR, pdf.name)

    with open(file_path, "wb") as f:
        for chunk in pdf.chunks():
            f.write(chunk)

    # RAG pipeline
    try:
        text = extract_text_from_pdf(file_path)
        docs = split_text(text)
        create_vectorstore(docs)
        return Response({"message": "PDF indexed successfully"}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# API: Query Document
@api_view(["POST"])
def query_document(request):
    question = request.data.get("question")

    if not question:
        return Response({"error": "Question is required"}, status=status.HTTP_400_BAD_REQUEST)

    if not os.path.exists("faiss_index"):
        return Response({"error": "No document indexed yet. Please upload a PDF first."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        vectorstore = load_vectorstore()
        docs = vectorstore.similarity_search(question, k=4)

        if not docs:
            return Response({"answer": "No relevant information found in the document."})

        context = "\n\n".join(doc.page_content for doc in docs)
        answer = generate_answer(context, question)

        return Response({"answer": answer}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# UI: Serves the base page
def ui(request):
    return render(request, "rag/index.html")