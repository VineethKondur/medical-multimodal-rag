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
    
    NEW: Also provides classify_pages() for graph awareness!
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


def should_attempt_ocr_table_extraction(pages_info):
    """
    Determine which 'unsafe' pages should attempt OCR→Table parsing.
    
    Scanned lab reports get flagged as 'unsafe' due to large image regions,
    but they still contain tabular test data that can be extracted via OCR.
    
    Returns:
        list: Page numbers (1-indexed) that are candidates for OCR table parsing
    """
    ocr_candidates = []
    
    for page_info in pages_info:
        if page_info.get('is_safe', True):
            continue  # Safe pages use normal extraction
            
        reason = page_info.get('reason', '').lower()
        
        # ECG-specific keywords (these should NOT be parsed as tables)
        ecg_keywords = [
            'ecg', 'electrocardiogram', 'waveform', 'qrs', 
            'pr interval', 'qt interval', 'lead ', 'cardiac',
            'rhythm', 'p-wave', 't-wave', 'sinus rhythm',
            '12-lead', 'heart rate', 'atrial pause'
        ]
        
        chart_keywords = [
            'chart', 'graph', 'plot', 'trend', 'visualization'
        ]
        
        is_likely_ecg = sum(1 for kw in ecg_keywords if kw in reason) >= 2
        is_likely_chart = sum(1 for kw in chart_keywords if kw in reason) >= 1
        
        # If it's just "large image region" without ECG/chart indicators
        # → It's probably a scanned lab report → TRY OCR TABLE PARSING!
        if ('large image region' in reason or 'heavy vector graphics' in reason) \
           and not is_likely_ecg \
           and not is_likely_chart:
            ocr_candidates.append(page_info['page_num'])
    
    if ocr_candidates:
        print(f"\n   📋 Found {len(ocr_candidates)} scanned page(s) for OCR table parsing\n")
    
    return ocr_candidates

# ══════════════════════════════════════════════════════════════════
# 🔥 NEW: Page Classification for Graph Awareness
# ════════════════════════════════════════════════════════════════

def classify_pages(file_path):
    """
    🔥 MAIN FUNCTION: Analyze each PDF page and detect graphical content.
    
    Returns list of dicts with page info:
    - page_num: int (1-indexed)
    - has_graphics: bool
    - is_safe: bool (True = safe for table extraction)
    - reason: str (why it was flagged if unsafe)
    
    Detection uses:
    1. Image coverage analysis (>20% = likely graphic)
    2. Vector graphics density (lots of lines = chart)
    3. ECG-specific terminology scanning
    
    NO ML training. Deterministic heuristics only.
    """
    import fitz
    
    doc = fitz.open(file_path)
    pages_info = []
    
    print("\n" + "="*60)
    print("🔍 PAGE CLASSIFICATION")
    print("="*60 + "\n")
    
    for i, page in enumerate(doc):
        info = {
            'page_num': i + 1,
            'has_graphics': False,
            'is_safe': True,
            'reason': ''
        }
        
        try:
            # Check 1: Images on page
            images = page.get_images(full=True)
            if len(images) > 0:
                page_area = page.rect.width * page.rect.height
                img_area = sum(
                    (page.get_image_rects(img[0])[0].width * 
                     page.get_image_rects(img[0])[0].height)
                        for img in images 
                        if page.get_image_rects(img[0])
                )
                
                image_ratio = img_area / page_area if page_area > 0 else 0
                
                if image_ratio > 0.20:  # >20% coverage = likely graphic
                    info['has_graphics'] = True
                    info['is_safe'] = False
                    info['reason'] = f'Large image region ({image_ratio:.0%} of page)'
            
            # Check 2: Vector drawings (charts use lots of lines)
            try:
                drawings = page.get_drawings()
                if len(drawings) > 30:  # Lots of drawing ops = likely chart
                    info['has_graphics'] = True
                    info['is_safe'] = False
                    info['reason'] = f'Heavy vector graphics ({len(drawings)} drawing operations)'
            except Exception:
                pass
            
            # Check 3: ECG-specific text patterns
            text = page.get_text().lower()
            ecg_indicators = [
                'ecg', 'electrocardiogram', 
                'lead ', 'limb leads', 'precordial leads',
                'waveform', 'qrs', 'p-wave', 't-wave',
                'sinus rhythm', 'cardiac axis',
                '12-lead', 'cardiology'
            ]
            
            ecg_matches = sum(1 for kw in ecg_indicators if kw in text)
            
            if ecg_matches >= 4:
                info['has_graphics'] = True
                info['is_safe'] = False
                info['reason'] = f'ECG content detected ({ecg_matches} indicators)'
            
        except Exception as page_error:
            # 🔥 NEW: Per-page error handling (don't let one bad page kill everything)
            print(f"  ⚠️ Error analyzing page {i+1}: {page_error}")
            info['is_safe'] = True  # Default to safe on error
            info['reason'] = f'Analysis error: {str(page_error)[:50]}'
        
        pages_info.append(info)
        
        # Log result
        status_icon = "⚠️  SKIP" if not info['is_safe'] else "✅"
        status_text = "UNSAFE" if not info['is_safe'] else "SAFE  "
        
        print(f"  Page {info['page_num']:2d}: [{status_icon}] {status_text}| {info['reason'] or 'Normal text/table'}")
    
    doc.close()
    
    # Summary
    safe_count = sum(1 for p in pages_info if p['is_safe'])
    unsafe_count = len(pages_info) - safe_count
    
    if unsafe_count > 0:
        print(f"\n  🛡️  Will skip {unsafe_count} graphical page(s) during table extraction")
    
    print(f"\n{'='*60}\n")
    
    return pages_info