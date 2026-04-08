#!/usr/bin/env python3
"""
🏥 COMPLETE MEDICAL LAB REPORT EXTRACTOR v17.0 - UNIVERSAL EDITION
==========================================================================
Handles: 
✅ 1-page structured PDFs (Camelot + pdfplumber)
✅ Scanned/image PDFs (OCR + Smart Parser v3.0)
✅ ECG/Graphical PDFs (auto-detect + skip)
✅ Multi-page lab reports (7+ pages, with microscopic extraction)

Author: Fixed & Optimized for Production Use
"""

import gc
import camelot
import re
import json
import pdfplumber
import pandas as pd
import numpy as np


# ============================================================================
# 🔥 PATTERNS & CONSTANTS
# ============================================================================

RANGE_PATTERN = r'\d+(?:\.\d+)?\s*[-–—]\s*\d+(?:\.\d+)?|<[ ]*\d+(?:\.\d+)?|>[ ]*\d+(?:\.\d+)?'

GARBAGE_PATTERNS = [
    r'\b\d{1,2}:\d{2}\b', r'\b(am|pm)\b',
    r'\b\d{1,2}\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b',
    r'plot\s*no', r'barcode\s*no', r'page\s*no',
]

NARRATIVE_PATTERNS = [
    r'\b(should|must|may|can)\s+be\b', r'\b(please|kindly|advised)\b',
    r'\b(recommend|suggest)\b', r'\bassociated\s+with\b',
    r'\bin\s+case\s+of\b', r'\bas\s+per\b', r'\bcomprises?\b',
    r'\bis\s*used\s+to\b', r'\bclinical\s+significance\b',
    r'\bthis\s+(test|is|should)\b',
]

METADATA_PATTERNS = [
    r'^sample\s*:', r'^method\s:*', r'patient\s*(id|name)', r'billing\s*date',
    r'sample\s*(collected|received)', r'report\s*(released|status|date)',
    r'referring\s*doctor', r'accession\s*no', r'p\.\s*id', r'processed\s*by',
    r'end\s+of\s*report', r'pvt\.?\s*ltd', r'diagnostics', r'consultant',
    r'senior\s*consultant', r'\bdr\.?\b', r'\bmd\b', r'\bhospital\b',
    r'\bipd\b', r'\bopd\b', r'\btechnician\b', r'\bsignature\b', r'\bsigned\b',
    r'\bpathologist\b', r'\bverified\s+by\b', r'\bauthorized\b',
    r'time\s*\d', r'\d{2}:\d{2}', r'report\s+(release|time)',
    r'sample\s*id', r'(mr|op|ip)\s*(no|number)',
    r'age\s*:?', r'sex\s*:?', r'doctor\s*:?',
    r'(equipment|method|specimen)\s*:',
    r'(monitored|checked|verified|authorized)\s+by',
]

SEROLOGICAL_TEST_PATTERNS = [
    r'(hiv|hcv|hbv|hbsag|hbeag)', r'(vdrl|rpr|tpha)',
    r'(dengue|malaria|widal)', r'(igg|igm|iga)',
    r'(rapid|elisa|pcr|rt-pcr)', r'(antibody|antigen)',
    r'(blood\s*group|rh\s*typing|grouping)', r'(pregnancy|preg\s*test)',
    r'(card\s*test|slide)',
]

BLOCKED_TESTS = {
    "cgdtre", "dhfferentiacquni", "dhfferentiabquni", "absqlute cqunis",
    "fully", "computerised", "pathological", "laboratory",
    "complete blood count", "absolute counts", "differential count",
    "unknown", "test", "value", "unit", "range", "status", "result",
    "test result",
    "differential leucocyte count", "dlc", "absolute count",
}

VALID_CATEGORICAL_VALUES = {
    'normal', 'abnormal', 'borderline', 'low', 'high',
    'positive', 'negative', 'reactive', 'non-reactive', 'non reactive',
    'detected', 'not detected', 'present', 'absent',
    'none', 'no', 'yes', 'trace', 'small', 'moderate', 'large',
    'good', 'fair', 'poor', 'clear', 'cloudy', 'turbid',
    'pale yellow', 'yellow', 'straw', 'amber', 'red', 'brown',
    'colorless', 'white', 'translucent', 'opaque',
    '1+', '2+', '3+', '4+', '++', '+++', '++++',
    'a', 'b', 'ab', 'o',
    'scarce', 'occasional', 'few', 'many', 'plenty',
    'non-hemolyzed', 'hemolyzed', 'nil', 'within normal limits',
    'adequate', 'inadequate',
}


# ============================================================================
# 🔥 VALIDATION FUNCTIONS (From your WORKING old version)
# ============================================================================

def is_garbage_value(value_str):
    if not value_str:
        return False
    for pattern in GARBAGE_PATTERNS:
        if re.search(pattern, value_str, re.IGNORECASE):
            return True
    return False


def is_narrative_text(text):
    if not text:
        return False
    for pattern in NARRATIVE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def is_metadata_text(text):
    """Check if text looks like metadata (not a test result)"""
    if not text:
        return False
    
    text_lower = str(text).lower().strip()
    
    metadata_keywords = [
        'sample', 'method', 'patient', 'doctor', 'report', 'accession',
        'p. id', 'processed', 'end of', 'pvt', 'diagnostic', 'consultant',
        'dr.', 'md', 'hospital', 'ipd', 'opd', 'technician', 'signature',
        'signed', 'pathologist', 'verified', 'authorized', 'time', 'age',
        'sex', 'equipment', 'specimen', 'monitored', 'checked',
        'atul', 'vadhavkar', 'micro', 'd.m.l.t', 'shrge', 'cgdtre',
        'sunday', 'murbad', 'kalyan', 'report release',
    ]
    
    for keyword in metadata_keywords:
        if keyword in text_lower:
            return True
    
    # Check for patterns that look like addresses
    if re.search(r'(road|street|lane|sector|near|opposite|behind)\b', text, re.IGNORECASE):
        return True
    
    # Check for timestamp patterns
    if re.search(r'\d{1,2}:\d{2}(:\d{2})?', text):
        return True
    
    # Then regex patterns
    for pattern in METADATA_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    
    return False


def is_serological_test(test_name):
    test_lower = str(test_name).lower()
    for pattern in SEROLOGICAL_TEST_PATTERNS:
        if re.search(pattern, test_lower):
            return True
    return False


def is_valid_in_table_context(test_name, value, unit="", ref_range=""):
    if not test_name or not value:
        return False

    test = str(test_name).strip()
    value_str = str(value).strip()

    if not re.search(r'[a-zA-Z]', test): return False
    if len(test) < 2 or len(test) > 100: return False
    if re.match(r'^[\d\s\.\-]+$', test): return False
    if is_metadata_text(test): return False
    if is_garbage_value(value_str): return False
    if is_narrative_text(test) or is_narrative_text(value_str): return False
    if len(test.split()) > 15: return False

    has_number = bool(re.search(r'\d', value_str))
    is_short_categorical = len(value_str) < 30 and not re.search(r'[.!?]', value_str)

    if not has_number and not is_short_categorical: return False
    if re.search(r'\b(is|are|was|were|has|have)\b', value_str, re.IGNORECASE) and not has_number: 
        return False

    return True


def is_valid_in_text_context(test_name, value, unit="", ref_range=""):
    if not test_name or not value: return False
    test = str(test_name).strip()
    value_str = str(value).strip()

    if not is_valid_in_table_context(test_name, value, unit, ref_range): return False

    has_number = bool(re.search(r'\d', value_str))
    if has_number:
        if re.match(r'^\d{4,}$', value_str): return False
        return True

    value_lower = value_str.lower()
    if re.match(r'^(non\s*[-]?\s*)?reactive(\s+\d+[:]\d+)?(\s+na)?$', value_lower): 
        return is_serological_test(test)
    if re.match(r'^(positive|negative|pos|neg)$', value_lower): 
        return is_serological_test(test)
    if re.match(r'^(not\s+)?detected$', value_lower): return True
    if re.match(r'^(not\s+)?seen$', value_lower): return True
    if re.match(r'^(present|absent)$', value_lower): return True
    if re.match(r'^[1-4]\+$', value_str): return True
    if re.match(r'^[ABOab]+[+-]?$', value_str): 
        return bool(re.search(r'(blood\s*group|grouping|abo|rh)', test, re.IGNORECASE))
    if re.match(r'^1:\d+$', value_str): return True
    if value_lower == 'normal': return True
    if value_lower == 'trace': return True

    return False


def is_valid_in_ocr_context(test_name, value, unit="", ref_range=""):
    test = str(test_name).strip()
    value_str = str(value).strip()

    if test.lower().strip() in BLOCKED_TESTS:
        return False

    if not is_valid_in_text_context(test_name, value, unit, ref_range):
        if re.search(r'\d', value_str) and len(test) >= 3:
            if re.search(r'[a-zA-Z]{2,}', test):
                if not is_metadata_text(test) and not is_narrative_text(test):
                    return True
        return False
    return True


# ============================================================================
# 🔥 UTILITY FUNCTIONS (From your WORKING old version)
# ============================================================================

def extract_flag_from_value(value_str):
    flag = ""
    cleaned = str(value_str).strip()
    flag_match = re.search(r'\s*\[?([HL])\]?\s*$', cleaned, re.IGNORECASE)
    if flag_match:
        flag_char = flag_match.group(1).upper()
        flag = "HIGH" if flag_char == "H" else "LOW"
        cleaned = cleaned[:flag_match.start()].strip()
    word_match = re.search(r'\s+(High|Low)\s*$', cleaned, re.IGNORECASE)
    if word_match:
        flag = word_match.group(1).upper()
        cleaned = cleaned[:word_match.start()].strip()
    return cleaned, flag


def extract_first_number(text):
    try:
        normalized = str(text).strip().rstrip(".,;:! ")
        normalized = re.sub(r'(\d+),(\d{1,2})(?!\d)', r'\1.\2', normalized)
        normalized = normalized.replace(",", "")
        match = re.search(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", normalized)
        return float(match.group()) if match else None
    except Exception:
        return None


def extract_numeric_range(range_str):
    try:
        r = str(range_str).strip()
        if not r or r.lower() in ["nan", "-", "", "none", "na", "n/a"]: 
            return None, None
        r = r.replace(",", "")
        numbers = re.findall(r"[-+]?(?:\d+\.?\d*|\.\d+)", r)
        if not numbers: return None, None
        numbers = [float(n) for n in numbers]
        if re.search(r"[\-–—]", r):
            return (numbers[0], numbers[1]) if len(numbers) >= 2 else (numbers[0], numbers[0])
        elif "<" in r: return None, (numbers[0] if numbers else None)
        elif ">" in r: return (numbers[0] if numbers else None), None
        elif numbers: return None, numbers[0]
    except Exception: pass
    return None, None


def clean_test_name(test_str):
    try:
        text = str(test_str).strip()
        if not text: return ""
        text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)

        if len(text) % 2 == 0:
            half = len(text) // 2
            if text[:half].strip().lower() == text[half:].strip().lower():
                text = text[:half].strip()

        words = text.split()
        cleaned = []
        for word in words:
            w_lower = word.lower()
            length = len(word)
            if length % 2 == 0 and length > 2:
                half = length // 2
                if w_lower[:half] == w_lower[half:]: word = word[:half]
            if not cleaned or word.lower() != cleaned[-1].lower(): cleaned.append(word)

        result = " ".join(cleaned)
        result = re.sub(r"[^\w\s\-()/]", "", result)
        return result.title().strip() if result else "Unknown"
    except Exception: return "Unknown"


UNITS_KEYWORDS = [
    'gm/dl', 'g/dl', 'g%dl', 'gldl', 'mg/dl', 'mg%', 'ul', 'iu/l', 'iu/ml',
    'fl', 'pg', '%', 'cmm', 'milllcmm', 'million/cumm', 'x10^3/ul', 'x10^9/l',
    'mmol/l', 'mm/hr', 'sec', 'mg', 'ml', 'l', 'dl', 'ng/ml', 'iu', 'x10',
    'cu/mm', 'k/cumm', 'th/cumm', '10^3/ul', '10^9/l', '/cumm', '/ul'
]
UNITS_SET = {u.replace('.', '').replace('/', '').lower() for u in UNITS_KEYWORDS}


def is_unit(word):
    if not word: return False
    w_clean = word.replace('.', '').replace('/', '').lower().strip()
    
    if w_clean in UNITS_SET: return True
    
    unit_indicators = ['cumm', 'ul', 'dl', 'ml', 'fl', 'pg', 'sec', 'hr', 'mm', 'iu', 'gm', 'mg']
    if any(ind in w_clean for ind in unit_indicators) and len(w_clean) <= 6: 
        return True
    
    ocr_unit_patterns = [
        r'^[/]?u[l1]$', r'^g[/]?d[l1]$', r'^m[g]/?d[l1]$',
        r'^%$', r'^f[l1]$', r'^p[g]$', r'^mill[/]?cmm$',
        r'^[/]?cumm$', r'^i[u][/][l1m]$',
    ]
    for pattern in ocr_unit_patterns:
        if re.match(pattern, w_clean): return True
    
    return False


# ============================================================================
# 🔥🔥🔥 MULTI-LINE SMART PARSER v3.0 (Your WORKING version)
# ============================================================================

def smart_parse_ocr_results(ocr_results):
    """
    Properly handles multi-line test entries.
    CRITICAL FIX: Track consumed rows correctly!
    """
    if not ocr_results:
        return []
    
    print("   🚀 Using MULTI-LINE SMART parser v3.0...")
    
    tokens = []
    for item in ocr_results:
        bbox, text, conf = item[0], item[1], item[2]
        if conf < 0.3 or not text.strip():
            continue
        xs = [p[0] for p in bbox]
        ys = [p[1] for p in bbox]
        
        tokens.append({
            'text': text.strip(),
            'x_min': min(xs), 'x_max': max(xs),
            'y_min': min(ys), 'y_max': max(ys),
            'y_center': (min(ys) + max(ys)) / 2.0,
            'x_center': (min(xs) + max(xs)) / 2.0,
            'conf': conf
        })
    
    print(f"   📊 Total tokens: {len(tokens)}")
    tokens.sort(key=lambda t: (t['y_center'], t['x_min']))
    
    rows = []
    current_row = []
    current_y = None
    Y_TOLERANCE = 18
    
    for token in tokens:
        if current_y is None or abs(token['y_center'] - current_y) > Y_TOLERANCE:
            if current_row:
                current_row.sort(key=lambda t: t['x_min'])
                rows.append(current_row)
            current_row = [token]
            current_y = token['y_center']
        else:
            current_row.append(token)
    
    if current_row:
        current_row.sort(key=lambda t: t['x_min'])
        rows.append(current_row)
    
    print(f"   📑 Formed {len(rows)} physical rows")
    
    classified_rows = []
    for idx, row in enumerate(rows):
        row_texts = [t['text'].strip() for t in row]
        full_text = ' '.join(row_texts).strip()
        
        row_type = classify_row_type_v2(row_texts, full_text)
        classified_rows.append({
            'index': idx,
            'tokens': row,
            'texts': row_texts,
            'full_text': full_text,
            'type': row_type
        })
    
    print(f"   📋 Row classification (first 30):")
    for i, r in enumerate(classified_rows[:30]):
        print(f"      [{r['index']:2d}] {r['type']:18s} | {r['full_text'][:60]}")
    
    results = []
    i = 0
    
    while i < len(classified_rows):
        row = classified_rows[i]
        
        if row['type'] == 'SKIP':
            i += 1
            continue
        
        if row['type'] == 'TEST_NAME_ONLY':
            merged = merge_test_name_with_value(classified_rows, i)
            if merged:
                results.append(merged)
                print(f"      ✅ MERGED [{i:2d}]: {merged['test'][:30]:30s} = {merged['value']:>8s} "
                      f"{merged.get('unit',''):6s} (ref: {merged.get('range','')}) "
                      f"[{merged.get('flag','')}]")
                i += merged['_rows_consumed']
            else:
                i += 1
        
        elif row['type'] == 'MIXED':
            parsed = parse_mixed_row_v2(row)
            if parsed:
                results.append(parsed)
                print(f"      ✅ PARSED [{i:2d}]: {parsed['test'][:30]:30s} = {parsed['value']:>8s} "
                      f"{parsed.get('unit',''):6s} (ref: {parsed.get('range','')}) "
                      f"[{parsed.get('flag','')}]")
            i += 1
        
        elif row['type'] == 'VALUE_ROW':
            i += 1
        
        elif row['type'] == 'UNIT_RANGE_ROW':
            i += 1
            
        elif row['type'] == 'FLAG_ONLY':
            i += 1
        
        else:
            i += 1
    
    print(f"\n   ✅ Parser v3.0 extracted {len(results)} tests total\n")
    return results


def classify_row_type_v2(row_texts, full_text):
    if not full_text.strip():
        return 'SKIP'
    
    if len(row_texts) == 1 and re.match(r'^\[?[HL]\]?$', row_texts[0], re.IGNORECASE):
        return 'FLAG_ONLY'
    
    if is_metadata_text(full_text):
        return 'SKIP'
    
    clean = clean_test_name(full_text)
    if clean.lower() in BLOCKED_TESTS:
        return 'SKIP'
    
    has_numeric = False
    first_numeric_idx = None
    
    for i, text in enumerate(row_texts):
        if re.match(r'^[\d,.]+(\s*\[?[HL]\]?)?$', text, re.IGNORECASE):
            has_numeric = True
            first_numeric_idx = i
            break
        num_match = re.match(r'^([\d,.]+)', text)
        if num_match:
            try:
                val = float(num_match.group(1).replace(',', ''))
                if val > 0 and val < 100000:
                    if not re.match(r'^[\d,.]+\s*[-–—]\s*[\d,.]+$', text):
                        has_numeric = True
                        first_numeric_idx = i
                        break
            except:
                pass
    
    if not has_numeric:
        if is_unit(row_texts[0]) if row_texts else False:
            return 'UNIT_RANGE_ROW'
        if re.search(RANGE_PATTERN, full_text) and len(full_text) < 25:
            return 'UNIT_RANGE_ROW'
        if re.search(r'[a-zA-Z]{3,}', full_text) and len(full_text) > 3:
            return 'TEST_NAME_ONLY'
        return 'SKIP'
    
    if first_numeric_idx == 0:
        return 'VALUE_ROW'
    else:
        return 'MIXED'


def merge_test_name_with_value(classified_rows, start_idx):
    test_row = classified_rows[start_idx]
    test_name = clean_test_name(test_row['full_text'])
    
    if not test_name or test_name.lower() in BLOCKED_TESTS:
        return None
    
    result = {
        'test': test_name,
        'value': '',
        'unit': '',
        'range': '',
        'flag': '',
        '_rows_consumed': 1
    }
    
    if start_idx >= 2:
        prev_row = classified_rows[start_idx - 1]
        
        prev_has_value = False
        for text in prev_row['texts']:
            if re.match(r'^[\d,.]+', text):
                prev_has_value = True
                break
        
        if prev_has_value:
            print(f"      🔍 Found VALUE-BEFORE pattern for: {test_name}")
            
            value_info = extract_value_from_row_v2(prev_row['texts'])
            if value_info and value_info.get('value'):
                result['value'] = value_info['value']
                
                if value_info.get('flag'):
                    result['flag'] = value_info['flag']
                
                if value_info.get('unit'):
                    result['unit'] = value_info['unit']
                
                prev_row['_consumed'] = True
                
                max_lookback = min(4, start_idx)
                
                for offset in range(2, max_lookback + 1):
                    check_row = classified_rows[start_idx - offset]
                    
                    if check_row.get('_consumed'):
                        continue
                    
                    if check_row['type'] == 'TEST_NAME_ONLY':
                        continue
                    
                    found_something_in_this_row = False
                    
                    for text in check_row['texts']:
                        range_match = re.search(RANGE_PATTERN, text)
                        if range_match and not result['range']:
                            candidate_range = range_match.group(0)
                            range_parts = re.split(r'[-–—]', candidate_range)
                            if len(range_parts) == 2:
                                try:
                                    low, high = float(range_parts[0]), float(range_parts[1])
                                    if 0 < low < high < 100000:
                                        result['range'] = candidate_range
                                        found_something_in_this_row = True
                                except ValueError:
                                    pass
                        
                        if is_unit(text) and not result['unit']:
                            result['unit'] = text
                            found_something_in_this_row = True
                        
                        if re.match(r'^\[?[HL]\]?$', text, re.IGNORECASE):
                            if not result['flag']:
                                result['flag'] = "HIGH" if 'H' in text.upper() else "LOW"
                                found_something_in_this_row = True
                    
                    if found_something_in_this_row:
                        check_row['_consumed'] = True
                
                value_num = extract_first_number(result['value'])
                if value_num:
                    result['value'] = str(value_num)
                    
                if is_valid_in_ocr_context(result['test'], result['value'],
                                           result.get('unit',''), result.get('range','')):
                    return result
    
    if start_idx + 1 < len(classified_rows):
        next_row = classified_rows[start_idx + 1]
        
        if next_row.get('_consumed'):
            return None
        
        next_type = next_row['type']
        
        if next_type in ['VALUE_ROW', 'MIXED']:
            value_info = extract_value_from_row_v2(next_row['texts'])
            
            if value_info and value_info.get('value'):
                result['value'] = value_info['value']
                result['flag'] = value_info.get('flag', '')
                result['unit'] = value_info.get('unit', '')
                result['range'] = value_info.get('range', '')
                result['_rows_consumed'] = 2
                
                for extra_offset in range(2, 5):
                    if start_idx + extra_offset < len(classified_rows):
                        extra = classified_rows[start_idx + extra_offset]
                        if extra.get('_consumed'):
                            continue
                        if extra['type'] == 'TEST_NAME_ONLY':
                            break
                        
                        for text in extra['texts']:
                            if extra['type'] == 'FLAG_ONLY' and not result['flag']:
                                if re.match(r'^\[?[HL]\]?$', text, re.IGNORECASE):
                                    result['flag'] = "HIGH" if 'H' in text.upper() else "LOW"
                            elif is_unit(text) and not result['unit']:
                                result['unit'] = text
                            rm = re.search(RANGE_PATTERN, text)
                            if rm and not result['range']:
                                result['range'] = rm.group(0)
                        
                        extra['_consumed'] = True
                
                value_num = extract_first_number(result['value'])
                if value_num:
                    result['value'] = str(value_num)
                    if is_valid_in_ocr_context(result['test'], result['value'],
                                               result.get('unit',''), result.get('range','')):
                        return result
    
    return None


def parse_mixed_row_v2(row):
    texts = row['texts']
    
    value_idx = None
    for i, text in enumerate(texts):
        if re.match(r'^[\d,.]+(\s*\[?[HL]\]?)?$', text, re.IGNORECASE):
            value_idx = i
            break
    
    if value_idx is None or value_idx == 0:
        return None
    
    test_name_parts = texts[:value_idx]
    test_name_parts = [p for p in test_name_parts if p not in [':', '-', '–', '—']]
    test_name = clean_test_name(' '.join(test_name_parts))
    
    if not test_name or test_name.lower() in BLOCKED_TESTS:
        return None
    
    remaining = texts[value_idx:]
    value_str = ' '.join(remaining)
    value_clean, flag = extract_flag_from_value(value_str)
    
    value_num = extract_first_number(value_clean)
    if value_num is None:
        return None
    
    unit = ''
    ref_range = ''
    for text in remaining[1:]:
        if is_unit(text) and not unit:
            unit = text
        range_match = re.search(RANGE_PATTERN, text)
        if range_match and not ref_range:
            ref_range = range_match.group(0)
    
    result = {
        'test': test_name,
        'value': str(value_num),
        'unit': unit,
        'range': ref_range,
        'flag': flag,
        '_rows_consumed': 1
    }
    
    if not is_valid_in_ocr_context(result['test'], result['value'], result['unit'], result['range']):
        return None
    
    return result


def extract_value_from_row_v2(texts):
    if not texts:
        return None
    
    result = {'value': '', 'flag': '', 'unit': '', 'range': ''}
    
    value_raw = texts[0]
    value_clean, flag = extract_flag_from_value(value_raw)
    
    value_num = extract_first_number(value_clean)
    if not value_num:
        return None
    
    result['value'] = str(value_num)
    result['flag'] = flag
    
    for text in texts[1:]:
        if re.match(r'^\[?[HL]\]?$', text, re.IGNORECASE):
            if not result['flag']:
                result['flag'] = "HIGH" if 'H' in text.upper() else "LOW"
        elif is_unit(text) and not result['unit']:
            result['unit'] = text
        else:
            range_match = re.search(RANGE_PATTERN, text)
            if range_match and not result['range']:
                result['range'] = range_match.group(0)
    
    return result


# ============================================================================
# 🔥 TABLE DETECTION (For digital PDFs - Your WORKING version)
# ============================================================================

def get_headers(df):
    header_keywords = ["test", "value", "range", "result", "unit", "name", "parameter",
                       "description", "biological", "ref", "normal"]
    for i in range(min(5, len(df))):
        row = [str(x).lower().strip() for x in df.iloc[i]]
        row_text = " ".join(row)
        if sum(1 for keyword in header_keywords if keyword in row_text) >= 2:
            return df.iloc[i], i, True
    if len(df) > 0: return df.iloc[0], 0, False
    return None, 0, False


ECG_QUALITATIVE_TABLE_INDICATORS = {
    'ecg quality', 'physiologist', 'morphology', 'rhythm present',
    'other rhythm', 'atrial ectopics', 'ventricular ectopics',
    'av conduction', 'p-wave morphology', 'qrs morphology', 
    't-wave morphology', 'st segment', 'q-wave',
    'cardiac axis', 'sinus rhythm', 'atrial pause'
}

def is_ecg_qualitative_table(headers):
    if not headers:
        return False
    
    header_text = ' '.join(str(h).lower() for h in headers)
    
    lab_report_indicators = [
        'hemoglobin', 'rbc', 'wbc', 'platelet', 'cbc', 'blood count',
        'differential', 'neutrophil', 'lymphocyte', 'eosinophil', 'monocyte',
        'basophil', 'pcv', 'hematocrit', 'mcv', 'mch', 'mchc', 'rdw',
        'glucose', 'creatinine', 'urea', 'bilirubin', 'protein',
        'sodium', 'potassium', 'chloride', 'lipid', 'cholesterol'
    ]
    
    lab_indicator_count = sum(1 for ind in lab_report_indicators if ind in header_text)
    if lab_indicator_count >= 1:
        return False
    
    ecg_indicator_count = sum(1 for indicator in ECG_QUALITATIVE_TABLE_INDICATORS 
                         if indicator in header_text)
    return ecg_indicator_count >= 2


def table_contains_qualitative_values(df, start_idx=1):
    total_cells = 0
    text_cells = 0
    numeric_cells = 0
    
    for i in range(start_idx, min(start_idx + 15, len(df))):
        row = df.iloc[i]
        for val in row:
            val_str = str(val).strip()
            
            if not val_str or val_str.lower() in ['nan', '', 'none', 'na', 'n/a']:
                continue
                
            total_cells += 1
            
            if re.match(r'^[\d.,eE+-]+$', val_str):
                try:
                    float(val_str.replace(',', ''))
                    numeric_cells += 1
                    continue
                except ValueError:
                    pass
            
            lab_friendly_values = [
                'normal', 'abnormal', 'borderline', 'low', 'high',
                'positive', 'negative', 'reactive', 'non-reactive',
                'detected', 'not detected', 'present', 'absent',
                'none', 'no', 'yes', 'trace', 'small', 'moderate',
                '1+', '2+', '3+', '4+',  # Grading scales
                'normal', 'prolonged', 'within normal limits'
            ]
            
            if val_str.lower() in lab_friendly_values:
                text_cells += 0.3
            else:
                if not re.search(r'\d', val_str):
                    text_cells += 1
    
    if total_cells == 0:
        return False
    
    text_ratio = text_cells / total_cells
    numeric_ratio = numeric_cells / total_cells
    
    if numeric_ratio >= 0.20:
        return False
    
    return text_ratio > 0.85


def format_table(df, context="table"):
    rows = []
    try:
        headers, start_idx, has_headers = get_headers(df)
        if headers is None: return []
        headers = [str(h).lower().strip() for h in headers]
        
        # Skip ECG tables
        if is_ecg_qualitative_table(headers):
            print(f"      ⏭️ Skipping ECG qualitative table")
            return []
        
        # Skip qualitative tables
        if table_contains_qualitative_values(df, start_idx):
            print("      ⏭️ Skipping qualitative table (>85% text values)")
            return []
        
        test_idx = value_idx = unit_idx = range_idx = status_idx = None
        
        for i, h in enumerate(headers):
            h_lower = h.lower()
            if test_idx is None and any(x in h_lower for x in ["test", "parameter", "name", "analyte", "description"]): test_idx = i
            elif value_idx is None and any(x in h_lower for x in ["result", "value"]): value_idx = i
            elif unit_idx is None and "unit" in h_lower: unit_idx = i
            elif range_idx is None and any(x in h_lower for x in ["range", "reference", "ref", "normal", "biological"]): range_idx = i

        for i in range(len(headers)):
            if i < df.shape[1]:
                col_values = " ".join(str(df.iloc[j, i]).lower() for j in range(min(5, df.shape[0])))
                if any(word in col_values for word in ["low", "high", "normal", "borderline"]):
                    if i not in [test_idx, value_idx, unit_idx, range_idx]: status_idx = i; break

        if test_idx is None: test_idx = 0
        if value_idx is None and len(headers) > 1: value_idx = 1
        if unit_idx is None and len(headers) > 2: unit_idx = 2
        if range_idx is None and len(headers) > 3: range_idx = 3

        validator = is_valid_in_ocr_context if context == "ocr" else is_valid_in_table_context
        actual_start = start_idx + 1 if has_headers else start_idx

        for i in range(actual_start, len(df)):
            row = df.iloc[i]
            test = str(row.iloc[test_idx]).strip() if test_idx < len(row) else ""
            value_raw = str(row.iloc[value_idx]).strip() if value_idx is not None and value_idx < len(row) else ""
            unit = str(row.iloc[unit_idx]).strip() if unit_idx is not None and unit_idx < len(row) else ""
            range_raw = str(row.iloc[range_idx]).strip() if range_idx is not None and range_idx < len(row) else ""

            flag = ""
            if status_idx is not None and status_idx < len(row):
                status_val = str(row.iloc[status_idx]).strip().upper()
                if status_val in ["HIGH", "H", "LOW", "L"]: flag = "HIGH" if status_val in ["HIGH", "H"] else "LOW"

            if value_raw == test:
                parts = re.split(r'\s{2,}', test)
                if len(parts) >= 2:
                    test, value_raw = parts[0].strip(), parts[1].strip()
                    if len(parts) >= 3 and parts[2].lower() in ["low", "high"]:
                        flag = "HIGH" if parts[2].lower() == "high" else "LOW"
                        if len(parts) >= 4: range_raw = parts[3].strip()
                        if len(parts) >= 5: unit = parts[4].strip()
                    else:
                        if len(parts) >= 3: range_raw = parts[2].strip()
                        if len(parts) >= 4: unit = parts[3].strip()

            if unit and unit.lower() in ["low", "high"]: flag = "HIGH" if unit.lower() == "high" else "LOW"; unit = ""
            if not test or not value_raw: continue
            if test.lower() in ["nan", "-", "", "none", "na"] or value_raw.lower() in ["nan", "-", "", "none", "na"]: continue

            if re.search(RANGE_PATTERN, unit) and not re.search(RANGE_PATTERN, range_raw): unit, range_raw = range_raw, unit
            unit = unit.strip() if unit else ""
            if len(unit) > 25 or "\n" in unit: unit = unit.split("\n")[0][:25].strip()

            test = re.sub(r'\s+\d+(\.\d+)?.*$', '', test)
            test = re.sub(r'\b(low|high|normal|borderline)\b', '', test, flags=re.IGNORECASE)
            test_clean = clean_test_name(test)

            merged_pattern = r"(.*?)\s*(\d+(?:\.\d+)?\s*[-–—]\s*\d+(?:\.\d+)?|<[ ]*\d+(?:\.\d+)?|>[ ]*\d+(?:\.\d+)?)$"
            match = re.search(merged_pattern, value_raw)
            if match:
                val_part, range_part = match.group(1).strip(), match.group(2).strip()
                if val_part and (extract_first_number(val_part) is not None):
                    if not range_raw or range_raw.lower() in ["nan", "-", "", "none", "na"]: range_raw = range_part
                    value_raw = val_part

            value_raw, value_flag = extract_flag_from_value(value_raw)
            if value_flag and not flag: flag = value_flag

            has_number = bool(re.search(r'\d', value_raw))
            if has_number:
                value_num = extract_first_number(value_raw)
                if value_num is None: continue
                final_value = str(value_num)
            else:
                final_value = value_raw.strip()
                if len(final_value) > 35: continue

            range_clean = range_raw.strip() if range_raw else ""
            if not validator(test_clean, final_value, unit, range_clean): continue

            rows.append({"test": test_clean, "value": final_value, "unit": unit, "range": range_clean, "flag": flag})
    except Exception as e:
        print(f"⚠️ Table formatting error: {e}")
        return []

    unique_rows, seen = [], {}
    for row in rows:
        key = f"{row['test'].lower().strip()}|{row.get('unit', '').lower().strip()}"
        if key not in seen:
            seen[key] = len(unique_rows)
            unique_rows.append(row)
        else:
            old_idx, existing = seen[key], unique_rows[seen[key]]
            if row["range"] and not existing["range"]: unique_rows[old_idx] = row
            elif row.get("flag") and not existing.get("flag"): unique_rows[old_idx]["flag"] = row["flag"]
    return unique_rows


# ============================================================================
# 🔥 EXTRACTION FUNCTIONS
# ============================================================================

def extract_with_camelot(file_path: str) -> list:
    rows = []
    try:
        tables = camelot.read_pdf(file_path, pages="all", flavor="lattice", suppress_stdout=True)
        if tables.n == 0: tables = camelot.read_pdf(file_path, pages="all", flavor="stream", suppress_stdout=True)
        if tables.n > 0:
            print(f"✓ Camelot: {tables.n} tables found")
            for table in tables:
                if table.df.shape[0] < 2: continue
                rows.extend(format_table(table.df, context="table"))
    except Exception as e: print(f"⚠️ Camelot error: {e}")
    return rows


def extract_with_pdfplumber(file_path: str) -> list:
    rows = []
    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_rows = []
                for strat_v in ["lines", "text", "explicit"]:
                    if len(page_rows) >= 3: break
                    tables = page.extract_tables({"vertical_strategy": strat_v, "horizontal_strategy": strat_v})
                    page_rows.extend(_process_pdfplumber_tables(tables, "table"))
                rows.extend(page_rows)
    except Exception as e: print(f"⚠️ pdfplumber error: {e}")
    return rows


def _process_pdfplumber_tables(tables, context="table") -> list:
    rows = []
    for table in tables:
        if not table: continue
        df = pd.DataFrame(table).dropna(how="all").fillna("")
        if df.shape[0] < 2: continue
        rows.extend(format_table(df, context=context))
    return rows


# ============================================================================
# 🔥 TEXT-BASED TEST EXTRACTION (Your WORKING version)
# ============================================================================

def extract_text_based_tests(file_path: str, is_ocr=False) -> list:
    import fitz

    text_rows = []
    validator = is_valid_in_ocr_context if is_ocr else is_valid_in_text_context
    full_text = ""

    try:
        doc = fitz.open(file_path)
        for page in doc: full_text += page.get_text() + "\n"
        doc.close()
    except Exception:
        pass

    if len(full_text.strip()) < 100 and is_ocr:
        print("   ⚠️ PyMuPDF found no text. Using MULTI-LINE SMART parser v3.0...")
        try:
            from .ocr import extract_bboxes_with_ocr
            ocr_bboxes = extract_bboxes_with_ocr(file_path)

            if ocr_bboxes:
                text_rows = smart_parse_ocr_results(ocr_bboxes)
            else:
                print("   ⚠️ No OCR results returned")

        except Exception as e:
            print(f"   ⚠️ OCR failed: {e}")
            import traceback
            traceback.print_exc()

        return text_rows

    if not full_text.strip():
        return text_rows

    lines = full_text.split("\n")
    for line in lines:
        line = line.strip()
        if not line or len(line) < 5 or is_metadata_text(line): continue
        if re.match(r'^(Sample|Method)\s*:', line, re.IGNORECASE): continue
        if len(line) > 120: continue
        
        line_lower = line.lower()
        
        ecg_narrative_patterns = [
            r'^ecg quality:', r'^ventricular rate:\s*(normal|bradycardia|tachycardia)',
            r'^pr interval:\s*(normal|prolonged)', r'^qrs duration:\s*(normal|wide)',
            r'^qt.*interval:\s*(normal|prolonged)', r'^cardiac axis:\s*(normal)',
            r'^sinus rhythm', r'^other rhythm:', r'^atrial pause',
            r'^av conduction:', r'.*morphology:', r'^st segment:',
            r'^p-wave', r'^t-wave', r'^q-wave', r'.*ectopics:',
            r'exhibits\s+a\s+cardiac', r'the\s+total\s+time\staken',
            r'the\s+qt.*interval\s+indicates', r'regular\s+p-waves',
            r'is\s+sinus\s+rhythm', r'no\s+displacement'
        ]
        
        is_ecg_narrative = any(re.search(p, line_lower) for p in ecg_narrative_patterns)
        if is_ecg_narrative:
            continue
        
        parts = re.split(r'\s{2,}|\t', line)
        if len(parts) >= 2:
            potential_value = parts[-1] if ':' not in parts[-2] else parts[-1]
            
            text_only_values = ['normal', 'abnormal', 'none', 'no', 'yes', 'not observed',
                            'present', 'absent', 'prolonged', 'within normal limits']
            if potential_value.lower().strip() in text_only_values:
                test_name_candidate = ' '.join(parts[:-1]).lower()
                is_sero_or_urine = any(kw in test_name_candidate for kw in 
                                    ['test', 'screen', 'pregnancy', 'hiv', 'urine'])
                if not is_sero_or_urine:
                    continue
                    
        parts = re.split(r'\s{2,}|\t', line)
        if len(parts) == 1: parts = line.split()
        if len(parts) >= 2:
            num_idx = -1
            for j, part in enumerate(parts):
                if j == 0: continue
                clean_part = part.replace("<", "").replace(">", "").replace("%", "").replace(",", "").rstrip(".,;: ")
                if re.match(r'^[-+]?\d+(\.\d+)?$', clean_part):
                    num_idx = j
                    break

            if num_idx > 0:
                try:
                    test_name = " ".join(parts[:num_idx]).strip()
                    value, flag = extract_flag_from_value(parts[num_idx].strip())
                    unit = parts[num_idx + 1].strip() if num_idx + 1 < len(parts) else ""
                    ref_range = " ".join(parts[num_idx + 2:].strip()) if num_idx + 2 < len(parts) else ""

                    if re.search(RANGE_PATTERN, unit) and not re.search(RANGE_PATTERN, ref_range):
                        unit, ref_range = ref_range, unit
                    if unit and unit.lower() in ["low", "high", "h", "l"]:
                        flag = "HIGH" if unit.lower() in ["high", "h"] else "LOW"
                        unit = ""
                        ref_range = " ".join(parts[num_idx + 2:]) if num_idx + 2 < len(parts) else ""

                    value_num = extract_first_number(value)
                    if value_num is None:
                        continue
                    final_value = str(value_num)

                    if len(test_name) >= 2 and not test_name.isnumeric():
                        row = {"test": test_name, "value": final_value, "unit": unit, "range": ref_range, "flag": flag}
                        if row not in text_rows and validator(row["test"], row["value"], row["unit"], row["range"]):
                            text_rows.append(row)
                except Exception:
                    pass

    return text_rows


# ============================================================================
# 🔥 SCANNED PDF DETECTION
# ============================================================================

def detect_if_scanned(file_path: str) -> bool:
    import fitz
    try:
        doc = fitz.open(file_path)
        text_length = sum(len(doc[i].get_text().strip()) for i in range(min(3, len(doc))))
        doc.close()
        return text_length < 100
    except Exception:
        return False


# ============================================================================
# 🔥 DOCUMENT TYPE DETECTION
# ============================================================================

def _detect_document_type(file_path: str) -> str:
    import fitz
    
    try:
        doc = fitz.open(file_path)
        
        full_text = ""
        page_texts = []
        for i in range(min(3, len(doc))):
            page_text = doc[i].get_text()
            page_texts.append(page_text)
            full_text += page_text + "\n"
        
        doc.close()
        
        text_lower = full_text.lower()
        
        # ECG indicators
        ecg_indicators = [
            '12-lead ecg', '12 lead ecg', 'ecg report', 'electrocardiogram',
            'physiologist\'s report', 'ecg quality', 'ecg on demand',
            'ventricular rate', 'pr interval', 'qrs duration',
            'qt interval', 'qtc interval', 'p-wave morphology',
            'st segment', 'cardiac axis', 'sinus rhythm present',
            'p wave morphology', 'qrs morphology', 't-wave morphology',
            'atrial ectopics', 'ventricular ectopics', 'av conduction',
            'technomed', 'ecg on-demand',
        ]
        
        ecg_count = sum(1 for ind in ecg_indicators if ind in text_lower)
        if any('ecg' in pt.lower() for pt in page_texts[:2]):
            ecg_count += 3
        
        if ecg_count >= 3:
            return 'ecg_report'
        
        # Radiology indicators
        radiology_indicators = [
            'x-ray', 'xray', 'radiograph', 'ct scan', 'mri', 'magnetic resonance',
            'ultrasound', 'sonography', 'chest x-ray', 'cxr', 'radiology report',
            'imaging study', 'radiologist', 'dicom', 'view series',
            'axial', 'coronal', 'sagittal',
        ]
        
        rad_count = sum(1 for ind in radiology_indicators if ind in text_lower)
        if rad_count >= 2:
            return 'radiology_image'
        
        # Lab report indicators
        lab_indicators = [
            'complete blood count', 'cbc', 'hemoglobin', 'haemoglobin', 'haematocrit',
            'hematocrit', 'wbc count', 'white blood cell', 'rbc count', 'red blood cell',
            'platelet count', 'platelets', 'blood glucose', 'fasting glucose', 'hba1c',
            'liver function test', 'lft', 'kidney function', 'renal function',
            'lipid profile', 'cholesterol', 'thyroid function', 'tsh', 't4', 't3',
            'urinalysis', 'metabolic panel', 'bmp', 'cmp',
            'reference range', 'normal range', 'abnormal', 'biochemistry',
            'hematology', 'serology', 'immunology',
        ]
        
        lab_count = sum(1 for ind in lab_indicators if ind in text_lower)
        lab_value_patterns = re.findall(r'(\d+\.?\d*)\s*(g/dl|g%dl|mg/dl|mmol/l|iu/l|iu/ml|%|fl|pg)', text_lower)
        
        if lab_count >= 3 or len(lab_value_patterns) >= 5:
            return 'lab_report'
        
        if len(full_text.strip()) < 300:
            return 'scanned_image'
        
        return 'unknown'
        
    except Exception as e:
        print(f"   ⚠️ Document type detection failed: {e}")
        return 'unknown'


# ============================================================================
# 🔥 MICROSCOPIC EXTRACTION (NEW - For multi-page PDFs)
# ============================================================================

def extract_microscopic_universal(file_path: str) -> list:
    """
    v5.0 FINAL: Handles multi-column tables split across lines.
    Pattern: Test name repeated 4x, then Sample: Urine, Value, Unit, Range
    """
    import fitz
    
    results = []
    seen_keys = set()
    
    print("\n" + "="*70)
    print("🔬 MICROSCOPIC EXTRACTION v5.0")
    print("="*70 + "\n")
    
    micro_tests = {
        'Pus Cells': {'unit': '/hpf', 'pattern': r'^pus\s*cells?$'},
        'Epithelial Cells': {'unit': '/hpf', 'pattern': r'^epithelial\s*cells?$'},
        'RBC (Microscopic)': {'unit': '/hpf', 'pattern': r'^rbc$'},
        'Casts': {'unit': '/lpf', 'pattern': r'^casts?$'},
        'Crystals': {'unit': '/hpf', 'pattern': r'^crystals?$'},
        'Bacteria': {'unit': '/hpf', 'pattern': r'^bacteria?$'},
        'Yeast': {'unit': '/hpf', 'pattern': r'^yeast$'},
        'Mucus': {'unit': '', 'pattern': r'^mucus$'},
    }
    
    def is_valid_value(text):
        if not text:
            return False
        
        text = str(text).strip()
        
        patterns = [
            r'^\d+\s*[-–—]\s*\d+$',
            r'^\d+$',
            r'^(not\s+)?detected$',
            r'^(none|nil|absent|present)$',
            r'^(scarce|occasional|few|many)$',
            r'^[1-4]\+$',
            r'^normal$',
        ]
        
        return any(re.match(p, text, re.IGNORECASE) for p in patterns)
    
    try:
        doc = fitz.open(file_path)
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            lines = [l.strip() for l in text.split('\n')]
            
            has_micro = any(
                kw in text.lower() 
                for kw in ['microscopic examination', '/hpf', '/lpf']
            )
            
            if not has_micro:
                continue
            
            print(f"📍 Page {page_num + 1}: Scanning...")
            
            i = 0
            while i < len(lines):
                line = lines[i]
                
                matched_test = None
                
                for test_name, info in micro_tests.items():
                    if re.match(info['pattern'], line, re.IGNORECASE):
                        matched_test = test_name
                        break
                
                if not matched_test:
                    i += 1
                    continue
                
                extracted_value = None
                extracted_unit = None
                extracted_range = None
                
                search_end = min(i + 10, len(lines))
                
                for j in range(i, search_end):
                    current_line = lines[j]
                    
                    if current_line.lower() == 'sample: urine':
                        continue
                    
                    if current_line.lower() in ['/hpf', '/lpf']:
                        if extracted_value and not extracted_unit:
                            extracted_unit = current_line
                            continue
                    
                    if is_valid_value(current_line):
                        if not extracted_value:
                            extracted_value = current_line
                        elif extracted_value and not extracted_range:
                            extracted_range = current_line
                
                if extracted_value:
                    if not extracted_unit:
                        extracted_unit = micro_tests[matched_test]['unit']
                    
                    dedup_key = f"{matched_test}|{extracted_value.lower()}"
                    
                    if dedup_key not in seen_keys:
                        seen_keys.add(dedup_key)
                        
                        results.append({
                            'test': matched_test,
                            'value': extracted_value.title(),
                            'unit': extracted_unit,
                            'range': extracted_range if extracted_range else '',
                            'flag': '',
                            '_source': f'p{page_num+1}'
                        })
                        
                        print(f"   ✅ {matched_test:<25} {extracted_value:<15} {extracted_unit}")
                
                i += 8
                continue
            
        doc.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"\n{'='*70}")
    print(f"🎉 COMPLETE: {len(results)} microscopic tests extracted")
    print(f"{'='*70}\n")
    
    if results:
        for r in results:
            print(f"  • {r['test']:<25} {r['value']:<15} {r['unit']:<6} [{r['_source']}]")
        print()
    
    return results


# ============================================================================
# 🔥🔥🔥 MAIN EXTRACTION FUNCTION v17.0 - UNIFIED HYBRID
# ============================================================================

def extract_tables(file_path: str) -> list:
    """
    ✅✅✅ COMPLETE v17.0: Universal extractor for ALL PDF types
    
    Handles:
    ✅ 1-page structured digital PDFs (Camelot + pdfplumber)
    ✅ Scanned/image-based PDFs (OCR + Smart Parser v3.0)
    ✅ ECG/Graphical PDFs (auto-detect + skip gracefully)
    ✅ Multi-page lab reports (7+ pages, with microscopic extraction)
    
    ALWAYS returns: list of dicts (never empty string or None)
    """
    all_table_rows = []
    extractor_stats = {}
    is_scanned = False
    doc_type = 'unknown'

    try:
        # ────────────────────────────────────────────────
        # PHASE 1: Document Detection
        # ────────────────────────────────────────────────
        
        is_scanned = detect_if_scanned(file_path)
        print(f"📄 Detected: {'SCANNED PDF' if is_scanned else 'DIGITAL PDF'}")

        doc_type = _detect_document_type(file_path)
        print(f"📋 Document type: {doc_type.upper()}")

        # ────────────────────────────────────────────────
        # PHASE 2: Route based on document type
        # ────────────────────────────────────────────────
        
        # Skip non-lab documents early
        if doc_type == 'ecg_report':
            print(f"\n{'='*60}")
            print(f"⏭️  SKIPPING (ECG Document)")
            print(f"{'='*60}\n")
            return []
            
        elif doc_type == 'radiology_image':
            print(f"\n{'='*60}")
            print(f"⏭️  SKIPPING (Radiology Image)")
            print(f"{'='*60}\n")
            return []

        # ────────────────────────────────────────────────
        # PHASE 3: Extraction
        # ────────────────────────────────────────
        
        print(f"\n   ✓ Proceeding with extraction...\n")

        # Method 1: Camelot (for digital PDFs)
        camelot_rows = [] if is_scanned else extract_with_camelot(file_path)
        
        # Method 2: pdfplumber (for digital PDFs)
        pdfplumber_rows = [] if is_scanned else extract_with_pdfplumber(file_path)
        
        # Method 3: Text-based (for all PDFs, especially scanned)
        text_based_rows = extract_text_based_tests(file_path, is_ocr=is_scanned)

        extractor_stats = {
            "camelot": len(camelot_rows),
            "pdfplumber": len(pdfplumber_rows),
            "text": len(text_based_rows),
        }

        # Merge all sources
        seen = {}
        for source_name, row_list in [
            ("camelot", camelot_rows),
            ("pdfplumber", pdfplumber_rows),
            ("text", text_based_rows),
        ]:
            for row in row_list:
                test_key = f"{row.get('test', '').lower().strip()}|{row.get('unit', '').lower().strip()}"
                if test_key:
                    if test_key not in seen:
                        seen[test_key] = len(all_table_rows)
                        all_table_rows.append(row)
                    else:
                        old_idx = seen[test_key]
                        existing = all_table_rows[old_idx]
                        if row.get("range") and not existing.get("range"):
                            all_table_rows[old_idx] = row
                        elif row.get("flag") and not existing.get("flag"):
                            all_table_rows[old_idx]["flag"] = row["flag"]

    except Exception as e:
        print(f"⚠️ Table extraction failed: {e}")
        import traceback
        traceback.print_exc()
        return []
    
    finally:
        gc.collect()

    # ────────────────────────────────────────────────
    # PHASE 4: Post-processing & Cleanup
    # ────────────────────────────────────────────────
    
    # Clean up garbage entries
    final_results = []
    final_seen = set()
    
    for r in all_table_rows:
        test_name = r.get('test', '')
        
        # Skip invalid entries
        if not test_name or len(test_name) > 100 or '\n' in test_name:
            continue
        if 'diagnosis' in test_name.lower() and len(test_name) > 50:
            continue
        
        key = f"{test_name.lower()}|{r.get('unit','').lower()}|{r.get('value','').lower()}"
        
        if key not in final_seen:
            final_seen.add(key)
            final_results.append(r)

    # Fix corrupted numbers (e.g., "8775" → "87.75")
    for r in final_results:
        val = r.get('value', '')
        if isinstance(val, str) and re.match(r'^\d{4,}$', val):
            # Try inserting decimal before last 2 digits
            fixed = val[:-2] + '.' + val[-2:]
            try:
                num = float(fixed)
                if 0 < num < 10000:
                    r['value'] = fixed
            except:
                pass

    # ────────────────────────────────────────────────
    # PHASE 5: Microscopic fallback (for multi-page PDFs)
    # ────────────────────────────────────────────────
    
    # Check if we need microscopic data
    has_micro = any(
        kw in str(r).lower() 
        for r in final_results
        for kw in ['pus cells', 'epithelial cells', 'casts', 'crystals', 'bacteria']
    )
    
    # Only run fallback if we have a multi-page document AND missing microscopic data
    # OR if we have very few total tests (might be missing data)
    if (len(final_results) < 15 and doc_type in ['lab_report', 'unknown']) or \
       (not has_micro and doc_type == 'lab_report'):
        
        print(f"\n{'='*70}")
        print(f"🔬 Running microscopic fallback extraction...")
        print(f"{'='*70}\n")
        
        try:
            micro_results = extract_microscopic_universal(file_path)
            
            if micro_results:
                micro_seen = {
                    f"{r['test'].lower()}|{r.get('unit','').lower()}"
                    for r in final_results
                }
                
                added = 0
                for mr in micro_results:
                    key = f"{mr['test'].lower()}|{mr.get('unit','').lower()}"
                    if key not in micro_seen:
                        final_results.append(mr)
                        micro_seen.add(key)
                        added += 1
                
                if added > 0:
                    print(f"   🎉 Added {added} microscopic tests!")
                    
        except Exception as micro_err:
            print(f"   ⚠️ Microscopic fallback error: {micro_err}")

    # ────────────────────────────────────────────────
    # SUMMARY
    # ────────────────────────────────────────────────
    
    print(f"\n{'=' * 70}")
    print(f"📊 EXTRACTION SUMMARY ({'SCANNED' if is_scanned else 'DIGITAL'})")
    print(f"{'=' * 70}")

    if not is_scanned:
        print(f"   Camelot:     {extractor_stats.get('camelot', 0):>4} rows")
        print(f"   pdfplumber:  {extractor_stats.get('pdfplumber', 0):>4} rows")
    print(f"   Text-based:  {extractor_stats.get('text', 0):>4} rows")
    print(f"   Microscopic: {sum(1 for r in final_results if any(kw in r['test'].lower() for kw in ['pus cells', 'epithelial', 'casts']))} tests")
    print(f"{'=' * 70}")
    print(f"   TOTAL: {len(final_results)} unique tests")

    flagged = [r for r in final_results if r.get("flag")]
    if flagged:
        print(f"\n   ⚠️  ABNORMAL: {len(flagged)} tests flagged")
        for r in flagged[:8]:
            print(f"      → {r['test']}: {r['value']} {r.get('unit','')} [{r['flag']}]")

    if not final_results:
        print("\n❌ No valid lab data extracted")
        return []

    return final_results


# ============================================================================
# 🔥 TEST / DEMO
# ============================================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        result = extract_tables(sys.argv[1])
        
        if isinstance(result, list) and result:
            print("\n📋 EXTRACTED DATA:")
            print(f"{'-'*90}")
            print(f"{'Test Name':<40} {'Value':<12} {'Unit':<10} {'Range':<18} {'Flag'}")
            print(f"{'-'*90}")
            
            for row in result:
                flag_str = f" [{row['flag']}]" if row.get('flag') else ""
                range_str = f" (Ref: {row['range']})" if row.get('range') else ""
                unit_str = f" {row['unit']}" if row.get('unit') else ""
                print(f"  • {row['test']:<38} {row['value']:<12}{unit_str:<10}{row.get('range', ''):<18}{row.get('flag', '')}")
            
            print(f"{'-'*90}")
            print(f"\nTotal: {len(result)} tests extracted")
            
            # Show microscopic specifically
            micro = [r for r in result if any(kw in r['test'].lower() for kw in 
                   ['pus cells', 'epithelial', 'casts', 'crystals', 'bacteria'])]
            if micro:
                print(f"\n🔬 MICROSCOPIC TESTS ({len(micro)}):")
                for m in micro:
                    print(f"  ★ {m['test']}: {m['value']} {m.get('unit','')}")
        
        elif isinstance(result, str):
            try:
                data = json.loads(result)
                print("\n📋 EXTRACTED DATA:")
                for row in data:
                    flag_str = f" [{row['flag']}]" if row.get('flag') else ""
                    range_str = f" (Ref: {row['range']})" if row.get('range') else ""
                    unit_str = f" {row['unit']}" if row.get('unit') else ""
                    print(f"  • {row['test']}: {row['value']}{unit_str}{range_str}{flag_str}")
            except:
                print(f"⚠️ Unexpected result: {type(result)}")
                print(f"   Preview: {str(result)[:500]}")
    else:
        print("Usage: python table_extractor.py <pdf_path>")
        print("\nUniversal medical lab report extractor.")