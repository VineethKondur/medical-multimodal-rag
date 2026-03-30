import logging

import fitz  # PyMuPDF

from .ocr import extract_text_with_ocr

logger = logging.getLogger(__name__)

# Minimum text length threshold to consider extraction successful
TEXT_LENGTH_THRESHOLD = 50


def extract_text_from_pdf(file_path: str) -> str:
    """
    Extract text from a PDF file.
    
    First attempts to extract text using PyMuPDF.
    If the extracted text is below the threshold, falls back to OCR.
    
    Args:
        file_path: Path to the PDF file
        
    Returns:
        Extracted text from the PDF
    """
    logger.info(f"Extracting text from PDF: {file_path}")
    
    # Attempt normal text extraction
    text = ""
    with fitz.open(file_path) as pdf:
        for page in pdf:
            text += page.get_text("text")
    
    logger.info(f"PyMuPDF extracted {len(text)} characters")
    
    # Check if text extraction was successful
    if len(text.strip()) < TEXT_LENGTH_THRESHOLD:
        logger.warning(
            f"Low text detected ({len(text)} characters), "
            f"switching to OCR fallback"
        )
        text = extract_text_with_ocr(file_path)
        logger.info(f"OCR extracted {len(text)} characters")
    
    return text
