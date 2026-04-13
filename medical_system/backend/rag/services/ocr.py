import warnings
import fitz  # PyMuPDF
import easyocr
import numpy as np
import cv2
import os

# 🔥 SUPPRESS DEPRECATION WARNINGS
warnings.filterwarnings('ignore', category=DeprecationWarning)
warnings.filterwarnings('ignore', message='ARC4 has been moved')

# ============================================
# NEW MEMORY-SAFE VERSION:
# ============================================
print("Initializing EasyOCR Reader (memory-safe mode)...")
def initialize_ocr_reader():
    """
    Initialize EasyOCR with automatic GPU/CPU detection.
    
    SMART LOGIC:
    - Checks VRAM availability before using GPU
    - Leaves 1.5GB buffer for system + other models (Moondream2)
    - Falls back to CPU if insufficient VRAM
    """
    global reader
    
    try:
        import torch
        
        # Check GPU availability AND free memory
        gpu_available = False
        gpu_reason = ""
        
        if torch.cuda.is_available():
            # Get GPU properties
            device_props = torch.cuda.get_device_properties(0)
            total_vram_gb = device_props.total_mem / 1e9  # Convert bytes to GB
            
            # Try to get free memory (may not work on all systems)
            try:
                free_vram_gb = (torch.cuda.mem_get_info()[0]) / 1e9
            except:
                free_vram_gb = total_vram_gb * 0.5  # Estimate 50% free
            
            # Require at least 1.5GB free VRAM for EasyOCR GPU mode
            MIN_VRAM_NEEDED_GB = 1.5
            
            if free_vram_gb >= MIN_VRAM_NEEDED_GB:
                gpu_available = True
                gpu_reason = f"GPU OK ({free_vram_gb:.1f}GB free)"
            else:
                gpu_reason = f"Insufficient VRAM ({free_vram_gb:.1f}GB free, need {MIN_VRAM_NEEDED_GB}GB)"
        else:
            gpu_reason = "CUDA not available"
        
        # Make decision
        if gpu_available:
            print(f"🎮 Attempting GPU mode... ({gpu_reason})")
            reader = easyocr.Reader(['en'], gpu=True, verbose=False)
            print(f"✅ EasyOCR Reader initialized successfully (GPU enabled)")
        else:
            print(f"💻 Using CPU mode... ({gpu_reason})")
            reader = easyocr.Reader(['en'], gpu=False, verbose=False)
            print(f"✅ EasyOCR Reader initialized successfully (CPU mode)")
        
        return True
        
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        reader = None
        return False
        
    except Exception as e:
        print(f"⚠️ GPU failed, trying CPU: {e}")
        try:
            reader = easyocr.Reader(['en'], gpu=False, verbose=False)
            print(f"✅ EasyOCR Reader initialized (CPU fallback)")
            return True
        except Exception as cpu_err:
            print(f"❌ CPU also failed: {cpu_err}")
            reader = None
            return False

# Initialize on module load
reader = None
initialize_ocr_reader()

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