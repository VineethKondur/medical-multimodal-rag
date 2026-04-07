import fitz  # PyMuPDF
import re
from collections import Counter

TEXT_LENGTH_THRESHOLD = 50

# Patterns for noise removal (Universal)
NOISE_PATTERNS = [
    # Footers
    r'plot no\.?\s*[\d\-]+',
    r'barcode no\.?\s*:?\s*[\d\-, ]+',
    r'page no\.?\s*:?\s*\d+\s*of\s*\d+',
    r'pvt\.?\s*ltd\.?',
    # Headers (keep test data, remove pure metadata lines)
    r'^report status\s*-\s*final$',
    r'^referring doctor\s*:\s*$',
    r'^accession no\s*:\s*\d+$',
    r'^p\.\s*id\.?\s*no\.?\s*:?\s*\S+$',
    r'^\d{8}\s+\w+',  # Accession + name at line start
]

METHOD_SAMPLE_PATTERN = r'^(Sample|Method)\s*:'


def extract_text_from_pdf(file_path):
    """
    Universal PDF text extractor with OCR fallback.
    Cleans noise while preserving test data.
    """
    raw_text = ""
    page_texts = []
    is_scanned = False

    try:
        doc = fitz.open(file_path)
        for page in doc:
            page_text = page.get_text()
            page_texts.append(page_text)
            raw_text += page_text + "\n"
        doc.close()
    except Exception as e:
        print(f"Error during standard text extraction: {e}")
        raw_text = ""

    text_length = len(raw_text.strip())
    print(f"Extracted text length: {text_length}")

    # OCR Fallback for scanned PDFs
    if text_length < TEXT_LENGTH_THRESHOLD:
        is_scanned = True
        print(f"Text below threshold ({TEXT_LENGTH_THRESHOLD}). Using OCR fallback.")
        try:
            from .ocr import extract_text_with_ocr
            raw_text = extract_text_with_ocr(file_path)
            page_texts = [raw_text]
        except Exception as e:
            print(f"FATAL: OCR failed: {e}")
            return ""

    # Clean the text
    cleaned_text = _clean_extracted_text(page_texts, is_scanned)
    noise_removed = len(raw_text) - len(cleaned_text)
    print(f"Cleaned text length: {len(cleaned_text)} (removed {noise_removed} chars)")
    
    return cleaned_text


def _clean_extracted_text(page_texts, is_scanned=False):
    """
    Clean text while preserving test data.
    Less aggressive for scanned PDFs.
    """
    if not page_texts:
        return ""

    # For scanned PDFs, be less aggressive with cleaning
    if is_scanned:
        # Only remove obvious noise patterns
        cleaned_pages = []
        for page_text in page_texts:
            lines = page_text.split('\n')
            cleaned_lines = []
            
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    cleaned_lines.append(line)
                    continue
                
                # Only remove method/sample lines for OCR
                if re.match(METHOD_SAMPLE_PATTERN, stripped, re.IGNORECASE):
                    continue
                
                cleaned_lines.append(line)
            
            cleaned_pages.append('\n'.join(cleaned_lines))
        
        cleaned_text = '\n'.join(cleaned_pages)
        cleaned_text = re.sub(r'\n{3,}', '\n\n', cleaned_text).strip()
        return cleaned_text

    # For digital PDFs, find and remove repeated headers/footers
    repeated_lines = _find_repeated_lines(page_texts)

    cleaned_pages = []

    for page_text in page_texts:
        lines = page_text.split('\n')
        cleaned_lines = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                cleaned_lines.append(line)
                continue

            # Skip repeated headers/footers
            if _is_noise_line(stripped, repeated_lines):
                continue

            # Skip Method/Sample metadata
            if re.match(METHOD_SAMPLE_PATTERN, stripped, re.IGNORECASE):
                continue

            cleaned_lines.append(line)

        cleaned_pages.append('\n'.join(cleaned_lines))

    cleaned_text = '\n'.join(cleaned_pages)
    cleaned_text = re.sub(r'\n{3,}', '\n\n', cleaned_text).strip()
    return cleaned_text


def _find_repeated_lines(page_texts, threshold=0.4):
    """Find lines appearing on >40% of pages."""
    if len(page_texts) < 2:
        return set()

    total_pages = len(page_texts)
    line_page_count = Counter()

    for page_text in page_texts:
        seen_on_this_page = set()
        for line in page_text.split('\n'):
            normalized = re.sub(r'\s+', ' ', line.strip().lower())
            if normalized and len(normalized) > 10:
                seen_on_this_page.add(normalized)
        
        for line in seen_on_this_page:
            line_page_count[line] += 1

    repeated = set()
    min_pages = max(2, int(total_pages * threshold))
    
    for line, count in line_page_count.items():
        if count >= min_pages:
            repeated.add(line)

    if repeated:
        print(f"  🔍 Found {len(repeated)} repeated noise patterns")
    return repeated


def _is_noise_line(line, repeated_lines):
    """Check if a line is noise (header/footer/pattern)."""
    normalized = re.sub(r'\s+', ' ', line.strip().lower())
    
    # 🔥 FIX: Exact match only for dynamic repeated lines
    if normalized in repeated_lines:
        return True
    
    # Check against static patterns (these use regex, so 'in' is fine if designed that way, 
    # but your NOISE_PATTERNS use search(), so keep it as is)
    for pattern in NOISE_PATTERNS:
        if re.search(pattern, line, re.IGNORECASE):
            return True
    
    return False