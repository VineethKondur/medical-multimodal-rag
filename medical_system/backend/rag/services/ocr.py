import logging
from functools import lru_cache
from typing import List

import cv2
import fitz  # PyMuPDF
import numpy as np

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_ocr_reader():
    """Get cached EasyOCR reader instance."""
    try:
        import easyocr
        return easyocr.Reader(['en'], gpu=False, verbose=False)
    except Exception as e:
        logger.error(f"Failed to initialize EasyOCR reader: {e}")
        raise


def _preprocess_image(image: np.ndarray) -> np.ndarray:
    """Convert image to grayscale for better OCR results."""
    if len(image.shape) == 3:
        return cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    return image


def _pdf_page_to_image(pdf_document, page_num: int) -> np.ndarray:
    """Convert a PDF page to a numpy image array."""
    page = pdf_document[page_num]
    mat = fitz.Matrix(2, 2)  # 2x zoom for better OCR quality
    pix = page.get_pixmap(matrix=mat)
    img_data = pix.tobytes("png")
    
    # Convert to numpy array
    nparr = np.frombuffer(img_data, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    # Convert BGR to RGB
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


def extract_text_with_ocr(file_path: str) -> str:
    """
    Extract text from a PDF using OCR (EasyOCR).
    
    This function is used as a fallback when normal text extraction fails.
    It converts each PDF page to an image and runs OCR on it.
    
    Args:
        file_path: Path to the PDF file
        
    Returns:
        Extracted text from all pages
    """
    logger.info(f"Starting OCR for PDF: {file_path}")
    
    try:
        reader = _get_ocr_reader()
    except Exception as e:
        logger.error(f"Cannot initialize OCR reader: {e}")
        return ""
    
    text_parts: List[str] = []
    
    try:
        with fitz.open(file_path) as pdf:
            num_pages = len(pdf)
            logger.info(f"Processing {num_pages} pages with OCR")
            
            for page_num in range(num_pages):
                try:
                    # Convert page to image
                    image = _pdf_page_to_image(pdf, page_num)
                    
                    # Preprocess: convert to grayscale
                    gray_image = _preprocess_image(image)
                    
                    # Run OCR
                    results = reader.readtext(gray_image)
                    
                    # Extract text from results
                    page_text = " ".join([result[1] for result in results])
                    
                    if page_text.strip():
                        text_parts.append(page_text)
                        logger.debug(f"Page {page_num + 1}: extracted {len(page_text)} characters")
                    
                except Exception as e:
                    logger.warning(f"OCR failed on page {page_num + 1}: {e}")
                    continue
        
        combined_text = " ".join(text_parts)
        logger.info(f"OCR completed: extracted {len(combined_text)} characters")
        
        return combined_text
        
    except Exception as e:
        logger.error(f"OCR processing failed: {e}")
        return ""
