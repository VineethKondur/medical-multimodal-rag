import warnings
import fitz  # PyMuPDF
import easyocr
import numpy as np
import cv2
import os

# 🔥 SUPPRESS DEPRECATION WARNINGS
warnings.filterwarnings('ignore', category=DeprecationWarning)
warnings.filterwarnings('ignore', message='ARC4 has been moved')

# Initialize the OCR reader once to avoid reloading the model on every call.
# This is a heavy object.
print("Initializing EasyOCR Reader...")
try:
    # 🔥 GPU ENABLED - Set to True for CUDA support. Falls back to CPU if GPU unavailable.
    reader = easyocr.Reader(['en'], gpu=True, verbose=False) 
    print("✓ EasyOCR Reader initialized successfully (GPU enabled).")
except Exception as e:
    reader = None
    print(f"⚠️  GPU initialization failed or CUDA not available. Falling back to CPU...")
    print(f"   Error: {e}")
    try:
        # Fallback to CPU if GPU fails
        reader = easyocr.Reader(['en'], gpu=False, verbose=False)
        print("✓ EasyOCR Reader initialized successfully (CPU mode).")
    except Exception as cpu_error:
        print(f"CRITICAL: Failed to initialize EasyOCR Reader: {cpu_error}")
        print("OCR functionality will be disabled. Please ensure you have installed PyTorch and EasyOCR correctly.")


def extract_text_with_ocr(file_path: str) -> str:
    """
    Extracts text from a PDF using OCR. It converts each page to an image
    and runs OCR on it.
    """
    if not reader:
        print("OCR is not available because the reader failed to initialize.")
        return ""

    print(f"--- Starting OCR process for file: {os.path.basename(file_path)} ---")
    
    try:
        doc = fitz.open(file_path)
    except Exception as e:
        print(f"Error: Could not open PDF file '{file_path}' with PyMuPDF. Details: {e}")
        return ""

    full_text = []
    for page_num, page in enumerate(doc):
        print(f"  - Processing page {page_num + 1}/{len(doc)}")
        try:
            pix = page.get_pixmap(dpi=300)  # Higher DPI improves OCR accuracy
            img_bytes = pix.tobytes("png")
            img_np = np.frombuffer(img_bytes, np.uint8)
            img = cv2.imdecode(img_np, cv2.IMREAD_COLOR)

            result = reader.readtext(img, detail=0) # Removed paragraph=True
            page_text = "\n".join(result)
            full_text.append(page_text)
        except Exception as e:
            print(f"    - Error processing page {page_num + 1} with OCR: {e}")
            continue
    
    doc.close()
    final_text = "\n\n".join(full_text)
    print(f"--- OCR Finished. Total characters extracted: {len(final_text)} ---")
    return final_text

def extract_bboxes_with_ocr(file_path: str) -> list:
    """
    Extracts text with X/Y bounding box coordinates.
    Returns: list of tuples: ( [x_min, y_min, x_max, y_max], text, confidence )
    """
    if not reader:
        return []

    print(f"--- Starting Bbox OCR for table extraction: {os.path.basename(file_path)} ---")
    try:
        doc = fitz.open(file_path)
    except Exception as e:
        return []

    all_bboxes = []
    for page_num, page in enumerate(doc):
        print(f"  - Processing page {page_num + 1}/{len(doc)}")
        try:
            pix = page.get_pixmap(dpi=300)
            img_bytes = pix.tobytes("png")
            img_np = np.frombuffer(img_bytes, np.uint8)
            img = cv2.imdecode(img_np, cv2.IMREAD_COLOR)

            # detail=1 returns coordinates!
            result = reader.readtext(img, detail=1, paragraph=False)
            all_bboxes.extend(result)
        except Exception as e:
            print(f"    - Error processing page {page_num + 1}: {e}")
            continue
    
    doc.close()
    print(f"--- Bbox OCR Finished. Total segments: {len(all_bboxes)} ---")
    return all_bboxes