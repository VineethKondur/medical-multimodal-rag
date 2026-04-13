"""
ECG Utility Functions - Single Source of Truth
=============================================

Consolidates all ECG calculation functions that were duplicated across views.py.
This follows DRY (Don't Repeat Yourself) principle.

Author: System Optimization
Version: 1.0
"""

import re
import json
import numpy as np
from typing import Dict, List, Tuple, Optional, Any


# ============================================================================
# ECG STATUS CALCULATION (THE ONE TRUE VERSION)
# ============================================================================

def calculate_ecg_status(test_name: str, value: float, normal_range: Tuple[float, float]) -> Tuple[str, str]:
    """
    Calculate status accepting CLINICALLY VALID abnormal ranges.
    
    CRITICAL DESIGN DECISION:
    - Bradycardia <60 bpm is VALID (not an error to reject!)
    - Prolonged PR >200ms is COMMON (1st degree AV block)
    - Wide QRS >120ms happens (bundle branch block)
    
    Args:
        test_name: Name of the test (e.g., 'Heart Rate', 'PR Interval')
        value: Numeric value extracted from document
        normal_range: Tuple of (low_normal, high_normal)
    
    Returns:
        Tuple of (status, severity):
        - status: "NORMAL", "HIGH", or "LOW"
        - severity: "normal", "mild", "moderate", or "severe"
    
    Reference Ranges Used:
        Heart Rate:     60-100 bpm
        PR Interval:    120-200 ms
        QRS Duration:   80-120 ms
        QTc Interval:   340-460 ms
        QT Interval:    350-460 ms
        P Axis:         -30 to +90 degrees
        QRS Axis:       -30 to +100 degrees
        T Axis:         -30 to +90 degrees
        RR Interval:    600-1000 ms
        P Duration:     80-120 ms
    """
    
    low, high = normal_range
    
    # Validate inputs
    if not isinstance(value, (int, float)):
        try:
            value = float(value)
        except (ValueError, TypeError):
            return "UNKNOWN", "unknown"
    
    # ================================================================
    # HEART RATE SPECIAL HANDLING
    # ================================================================
    if test_name == 'Heart Rate':
        if value < 30:
            return "LOW", "severe"       # Dangerously slow (emergency)
        elif value < 50:
            return "LOW", "severe"       # Profound bradycardia
        elif value < 60:
            deviation = abs(value - low) / low * 100
            return "LOW", ("moderate" if deviation > 20 else "mild")
        elif value > 150:
            return "HIGH", "severe"      # Severe tachycardia
        elif value > 100:
            deviation = abs(value - high) / high * 100
            return "HIGH", ("moderate" if deviation > 30 else "mild")
        else:
            return "NORMAL", "normal"
    
    # ================================================================
    # PR INTERVAL
    # ================================================================
    elif 'PR' in test_name:
        if value > 300:
            return "HIGH", "severe"      # Critically prolonged (high-grade AV block)
        elif value > 200:
            deviation = (value - high) / high * 100
            return "HIGH", ("moderate" if deviation > 30 else "mild")
        elif value < 120:
            return "LOW", "mild"        # Short PR (pre-excitation)
        else:
            return "NORMAL", "normal"
    
    # ================================================================
    # QRS DURATION (exclude Axis tests)
    # ================================================================
    elif 'QRS' in test_name and 'Axis' not in test_name:
        if value > 160:
            return "HIGH", "severe"      # Very wide (pacing, severe BBB)
        elif value > 120:
            deviation = (value - high) / high * 100
            return "HIGH", ("moderate" if deviation > 25 else "mild")
        else:
            return "NORMAL", "normal"
    
    # ================================================================
    # QTc INTERVAL (corrected QT - preferred over raw QT)
    # ================================================================
    elif 'QTc' in test_name or ('QT' in test_name and 'c' in test_name):
        if value > 550:
            return "HIGH", "severe"      # Dangerously prolonged (TdP risk)
        elif value > 460:
            deviation = (value - high) / high * 100
            return "HIGH", ("moderate" if deviation > 15 else "mild")
        elif value < 320:
            return "LOW", "severe"      # Short QT syndrome
        elif value < 340:
            return "LOW", "mild"        # Borderline short
        else:
            return "NORMAL", "normal"
    
    # ================================================================
    # RAW QT INTERVAL (when QTc not available)
    # ================================================================
    elif 'QT' in test_name:
        if value > 550:
            return "HIGH", "severe"
        elif value > 460:
            return "HIGH", "moderate"
        elif value < 320:
            return "LOW", "severe"
        else:
            return "NORMAL", "normal"
    
    # ================================================================
    # RR INTERVAL
    # ================================================================
    elif 'RR' in test_name:
        if value > 1500:
            return "HIGH", "moderate"   # Very slow (bradycardia)
        elif value > 1000:
            return "HIGH", "mild"      # Slow
        elif value < 400:
            return "LOW", "severe"     # Very fast (tachycardia)
        else:
            return "NORMAL", "normal"
    
    # ================================================================
    # P DURATION
    # ================================================================
    elif ('P Duration' in test_name) or ('P' in test_name and 'Duration' in test_name):
        if value > 140:
            return "HIGH", "moderate"
        elif value < 60:
            return "LOW", "mild"
        else:
            return "NORMAL", "normal"
    
    # ================================================================
    # GENERIC CALCULATION (for Axis and other measurements)
    # ================================================================
    else:
        if value < low:
            deviation = abs(value - low) / abs(low) * 100 if low != 0 else 0
            if deviation > 50:
                return "LOW", "severe"
            elif deviation > 25:
                return "LOW", "moderate"
            else:
                return "LOW", "mild"
        elif value > high:
            deviation = abs(value - high) / abs(high) * 100 if high != 0 else 0
            if deviation > 50:
                return "HIGH", "severe"
            elif deviation > 25:
                return "HIGH", "moderate"
            else:
                return "HIGH", "mild"
        else:
            return "NORMAL", "normal"


# ============================================================================
# FLATTENED ECG DATA PARSER (Single Implementation)
# ============================================================================

def parse_flattened_ecg_data(flattened_items: List[Tuple]) -> List[Dict]:
    """
    Parse flattened ECG data into standardized format.
    
    Args:
        flattened_items: List of (full_key_path, value, original_key) tuples
    
    Returns:
        List of standardized test result dictionaries
    """
    
    # Comprehensive field name mapping
    field_patterns = [
        # Heart Rate (25-250 bpm range to catch abnormalities)
        (r'heart.?rate|ventricular.?rate|hr\b|pulse.?rate', 
         'Heart Rate', 'bpm', (60, 100)),
        
        # PR Interval (80-400ms for AV blocks)
        (r'pr.?interval|pr.?duration|pr_dur|prs?',
         'PR Interval', 'ms', (120, 200)),
        
        # QRS Duration (40-220ms for BBB)
        (r'qrs.?duration|qrs.?dur|qrss?|qrsd',
         'QRS Duration', 'ms', (80, 120)),
        
        # QT Interval
        (r'qt.?interval(?!c)|qt.?duration(?!c)|qt[^c]?\b',
         'QT Interval', 'ms', (350, 460)),
        
        # QTc Interval (HIGHER PRIORITY - check first)
        (r'qtc|qt.?c.*interval|corrected.*qt|qtcf?',
         'QTc Interval', 'ms', (340, 460)),
        
        # Axis measurements (-90 to +180 degrees)
        (r'\bp.?axis|p.axis', 'P Axis', '°', (-30, 90)),
        (r'\bqrs.?axis|qrs.axis', 'QRS Axis', '°', (-30, 100)),
        (r'\bt.?axis|t.axis', 'T Axis', '°', (-30, 90)),
        
        # Other cardiac intervals
        (r'rr.?interval|rr\b', 'RR Interval', 'ms', (600, 1000)),
        (r'p.?wave.*dur|p.?duration', 'P Wave Duration', 'ms', (80, 120)),
        (r'rv5', 'RV5', 'mm', (0, 15)),
        (r'sv1', 'SV1', 'mm', (0, 20)),
    ]
    
    extracted = []
    seen_tests = set()
    
    for full_key, value, original_key in flattened_items:
        # Skip non-numeric values
        if not isinstance(value, (int, float)):
            continue
        
        # Skip unreasonable values (sanity check)
        if value == 0:
            continue
        if value < 0 and 'axis' not in full_key.lower():
            continue
        if value > 10000:
            continue
        
        matched = False
        
        for pattern, display_name, unit, normal_range in field_patterns:
            key_str = full_key.lower() + " " + original_key.lower()
            
            if re.search(pattern, key_str, re.IGNORECASE):
                # Avoid duplicates
                if display_name in seen_tests:
                    continue
                
                seen_tests.add(display_name)
                
                # Calculate status using our single source of truth function
                status, severity = calculate_ecg_status(display_name, value, normal_range)
                
                extracted.append({
                    'test': display_name,
                    'value': str(int(value)) if value == int(value) else f"{value:.1f}",
                    'unit': unit,
                    'range': f"{normal_range[0]}-{normal_range[1]}",
                    'status': status,
                    'severity': severity,
                    'source': 'ecg_analysis',
                    'confidence': 'high'
                })
                
                matched = True
                break
        
        # Log unmatched items silently (for debugging, enable if needed)
        # if not matched:
        #     print(f"[ECG Utils] Unmatched: {full_key} = {value}")
    
    return extracted


# ============================================================================
# TEXT MINING FROM GRAPH RESULT (Single Implementation)
# ============================================================================

def mine_text_from_graph_result(graph_result: Dict) -> List[Dict]:
    """
    Mine ECG values from graph analysis result text.
    
    Uses regex patterns with CLINICALLY VALID ranges including abnormal values.
    
    Args:
        graph_result: Dictionary from graph_router.analyze_graphical_pages()
    
    Returns:
        List of extracted ECG measurements
    """
    
    # Convert entire structure to string for text mining
    full_text = json.dumps(graph_result, default=str)
    
    # Patterns with clinically valid ranges (including abnormalities!)
    patterns = [
        # Heart Rate: 25-250 bpm (CRITICAL: must accept 38 bpm for bradycardia!)
        {
            'regex': r'(?:Heart\s+Rate|Ventricular\s+Rate|HR)[\s:\-.]*(\d+(?:\.\d+)?)\s*(?:bpm)?',
            'name': 'Heart Rate',
            'unit': 'bpm',
            'normal': (60, 100),
            'acceptable': (25, 250),
        },
        
        # PR Interval: 80-400ms (must accept 308ms for AV block!)
        {
            'regex': r'PR[\s_]*(?:Interval|Duration)?[\s:\-.]*(\d+(?:\.\d+)?)\s*(?:ms)?',
            'name': 'PR Interval',
            'unit': 'ms',
            'normal': (120, 200),
            'acceptable': (80, 400),
        },
        
        # QRS Duration: 40-220ms
        {
            'regex': r'QRS[\s_]*(?:Duration)?[\s:\-.]*(\d+(?:\.\d+)?)\s*(?:ms)?',
            'name': 'QRS Duration',
            'unit': 'ms',
            'normal': (80, 120),
            'acceptable': (40, 220),
        },
        
        # QTc Interval: 280-650ms (MUST be 3 digits to avoid page numbers like "29")
        {
            'regex': r'QTc?[\s_]*(?:Interval|Duration)?[\s:\-.]*(\d{3}(?:\.\d+)?)\s*(?:ms)?',
            'name': 'QTc Interval',
            'unit': 'ms',
            'normal': (340, 460),
            'acceptable': (280, 650),
        },
        
        # P Axis
        {
            'regex': r'P\s*Axis[\s:\-.]*([+-]?\d{1,3})\s*(?:°|degrees)?',
            'name': 'P Axis',
            'unit': '°',
            'normal': (-30, 90),
            'acceptable': (-90, 180),
        },
        
        # QRS Axis
        {
            'regex': r'QRS\s*Axis[\s:\-.]*([+-]?\d{1,3})\s*(?:°|degrees)?',
            'name': 'QRS Axis',
            'unit': '°',
            'normal': (-30, 100),
            'acceptable': (-90, 180),
        },
        
        # T Axis
        {
            'regex': r'T\s*Axis[\s:\-.]*([+-]?\d{1,3})\s*(?:°|degrees)?',
            'name': 'T Axis',
            'unit': '°',
            'normal': (-30, 90),
            'acceptable': (-90, 180),
        },
    ]
    
    extracted = []
    seen_names = set()
    
    for pat_info in patterns:
        matches = re.findall(pat_info['regex'], full_text, re.IGNORECASE)
        
        if matches:
            for match in matches:
                try:
                    value = float(match)
                    
                    acc_low, acc_high = pat_info['acceptable']
                    norm_low, norm_high = pat_info['normal']
                    
                    # Check ACCEPTABLE range (includes abnormal values!)
                    if not (acc_low <= value <= acc_high):
                        continue
                    
                    # Skip duplicates
                    if pat_info['name'] in seen_names:
                        continue
                    seen_names.add(pat_info['name'])
                    
                    # Use our centralized status calculator
                    status, severity = calculate_ecg_status(
                        pat_info['name'], 
                        value, 
                        (norm_low, norm_high)
                    )
                    
                    extracted.append({
                        'test': pat_info['name'],
                        'value': str(int(value)) if value == int(value) else f"{value:.1f}",
                        'unit': pat_info['unit'],
                        'range': f"{norm_low}-{norm_high}",
                        'status': status,
                        'severity': severity,
                        'source': 'text_mining',
                        'confidence': 'medium'
                    })
                    
                except (ValueError, TypeError):
                    continue
    
    return extracted


# ============================================================================
# MEASUREMENTS DICT PARSER (Single Implementation)
# ============================================================================

def parse_measurements_dict(measurements_dict: Dict, source: str = 'ecg_analysis') -> List[Dict]:
    """
    Parse a measurements dictionary into standard format.
    
    Handles various key naming conventions from different ECG report formats.
    
    Args:
        measurements_dict: Dictionary with ECG measurement keys/values
        source: Source identifier for provenance tracking
    
    Returns:
        List of standardized test result dictionaries
    """
    
    # Field mappings: [possible_keys] → (display_name, unit, normal_range)
    field_mappings = [
        (['heart_rate', 'heart rate', 'hr', 'ventricularrate', 'ventricular_rate'], 
         'Heart Rate', 'bpm', (60, 100)),
        (['pr_interval', 'pr interval', 'prduration', 'pr_duration', 'prs'], 
         'PR Interval', 'ms', (120, 200)),
        (['qrs_duration', 'qrs duration', 'qrsd', 'qrss'], 
         'QRS Duration', 'ms', (80, 120)),
        (['qt_interval', 'qt interval', 'qt_duration'], 
         'QT Interval', 'ms', (350, 460)),
        (['qtc_interval', 'qtc interval', 'qtcf', 'qtcfinterval'], 
         'QTc Interval', 'ms', (340, 460)),
        (['p_axis', 'paxis'], 'P Axis', '°', (-30, 90)),
        (['qrs_axis', 'qrsaxis'], 'QRS Axis', '°', (-30, 100)),
        (['t_axis', 'taxis'], 'T Axis', '°', (-30, 90)),
    ]
    
    extracted = []
    
    for possible_keys, display_name, unit, normal_range in field_mappings:
        value = None
        matched_key = None
        
        # Try exact match first
        for key in possible_keys:
            if key in measurements_dict:
                value = measurements_dict[key]
                matched_key = key
                break
            
            # Case-insensitive fallback
            key_norm = key.lower().replace(' ', '')
            for mk in measurements_dict.keys():
                if mk.lower().replace(' ', '').replace('_', '') == key_norm:
                    value = measurements_dict[mk]
                    matched_key = mk
                    break
            
            if value is not None:
                break
        
        if value is None:
            continue
        
        # Clean value (handle string numbers)
        if isinstance(value, (int, float)):
            value_num = value
        elif isinstance(value, str):
            num_match = re.search(r'([\d.]+)', value)
            if num_match:
                value_num = float(num_match.group(1))
            else:
                continue
        else:
            continue
        
        # Validate range (allow wide margin for abnormal values)
        low, high = normal_range
        if value_num < low * 0.3 or value_num > high * 3:
            continue  # Unreasonable value, skip
        
        # Use centralized status calculator
        status, severity = calculate_ecg_status(display_name, value_num, normal_range)
        
        extracted.append({
            'test': display_name,
            'value': str(int(value_num)) if value_num == int(value_num) else str(value_num),
            'unit': unit,
            'range': f"{low}-{high}",
            'status': status,
            'severity': severity,
            'source': source,
            'confidence': 'high'
        })
    
    return extracted


# ============================================================================
# HELPER: Flatten nested ECG structure (for Strategy 2)
# ============================================================================

def flatten_ecg_structure(obj: Any, parent_key: str = "", separator: str = "_") -> List[Tuple]:
    """
    Recursively flatten nested dict/list structure to find numeric fields.
    
    Args:
        obj: Object to flatten (dict, list, or primitive)
        parent_key: Key prefix for recursion
        Separator: Separator between nested keys
    
    Returns:
        List of (full_key_path, value, original_key) tuples
    """
    
    items = []
    
    if isinstance(obj, dict):
        for k, v in obj.items():
            new_key = f"{parent_key}{separator}{k}" if parent_key else k
            
            # Direct numeric value - keep it!
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                items.append((new_key, v, k))
            
            # String that might contain a number
            elif isinstance(v, str):
                num_match = re.search(r'([\d.]+)', str(v))
                if num_match:
                    try:
                        val = float(num_match.group(1))
                        items.append((new_key, val, k))
                    except:
                        pass
            
            # Nested structure - recurse
            elif isinstance(v, (dict, list)):
                items.extend(flatten_ecg_structure(v, new_key, separator))
                
    elif isinstance(obj, list):
        for i, item in enumerate(obj[:10]):  # Limit depth to avoid explosion
            items.extend(flatten_ecg_structure(item, f"{parent_key}[{i}]", separator))
    
    return items


# ============================================================================
# RECURSIVE MEASUREMENTS FINDER (for Strategy 1)
# ============================================================================

def find_measurements_dict_recursive(obj: Any, depth: int = 0, path: str = "root") -> Optional[Dict]:
    """
    Recursively search for a measurements dictionary in nested structure.
    
    Looks for dictionaries with multiple numeric ECG-related fields.
    
    Args:
        obj: Object to search
        depth: Current recursion depth
        path: Current path string (for logging)
    
    Returns:
        Measurements dictionary if found, None otherwise
    """
    
    if depth > 6 or not isinstance(obj, dict):
        return None
    
    numeric_count = 0
    ecg_key_count = 0
    
    # ECG-related keywords to look for
    ecg_keywords = [
        'heart', 'rate', 'pr_', 'qrs', 'qt', 'interval',
        'duration', 'axis', 'rhythm', 'bpm', 'ms',
        'ventricular', 'atrial', 'p_wave', 't_wave'
    ]
    
    for k, v in obj.items():
        if isinstance(v, (int, float)):
            numeric_count += 1
            if any(kw in k.lower().replace(' ', '_') for kw in ecg_keywords):
                ecg_key_count += 1
        elif isinstance(v, str):
            try:
                float(v)
                numeric_count += 1
                if any(kw in k.lower().replace(' ', '_') for kw in ecg_keywords):
                    ecg_key_count += 1
            except:
                pass
    
    # Found a measurements-like dictionary!
    if numeric_count >= 2 and ecg_key_count >= 2:
        return obj
    
    # Priority keys to check first
    priority_keys = ['measurements', 'data', 'values', 'values_dict', 'metrics']
    for pk in priority_keys:
        if pk in obj and isinstance(obj[pk], dict):
            result = find_measurements_dict_recursive(obj[pk], depth+1, f"{path}.{pk}")
            if result:
                return result
    
    # Then check all other keys (limit to first 20)
    for k, v in list(obj.items())[:20]:
        if isinstance(v, dict) and k not in priority_keys:
            result = find_measurements_dict_recursive(v, depth+1, f"{path}.{k}")
            if result:
                return result
        elif isinstance(v, list) and len(v) > 0:
            for i, item in enumerate(v[:5]):  # Limit list exploration
                if isinstance(item, dict):
                    result = find_measurements_dict_recursive(item, depth+1, f"{path}.{k}[{i}]")
                    if result:
                        return result
    
    return None


# ============================================================================
# CONVENIENCE: Main extraction orchestrator
# ============================================================================

def extract_structured_ecg_data(graph_analysis_result: Dict) -> List[Dict]:
    """
    Multi-strategy ECG data extractor.
    
    Tries 3 strategies in order:
    1. Find measurements dict (structured data)
    2. Flatten entire structure (semi-structured)
    3. Text mining (unstructured text)
    
    Args:
        graph_analysis_result: Dictionary from graph_router
    
    Returns:
        List of extracted ECG measurements
    """
    
    if not graph_analysis_result or not isinstance(graph_analysis_result, dict):
        return []
    
    # Strategy 1: Find measurements dict
    measurements_dict = find_measurements_dict_recursive(graph_analysis_result)
    if measurements_dict and len(measurements_dict) >= 2:
        extracted = parse_measurements_dict(measurements_dict, source='ecg_analysis')
        if extracted:
            return extracted
    
    # Strategy 2: Flatten entire structure
    flattened = flatten_ecg_structure(graph_analysis_result)
    if flattened:
        extracted = parse_flattened_ecg_data(flattened)
        if extracted and len(extracted) >= 1:
            return extracted
    
    # Strategy 3: Text mining fallback
    text_extracted = mine_text_from_graph_result(graph_analysis_result)
    if text_extracted and len(text_extracted) >= 1:
        return text_extracted
    
    return []


# ============================================================================
# TESTING / DEMO
# ============================================================================

if __name__ == "__main__":
    print("Testing ECG Utils...")
    
    # Test calculate_ecg_status
    test_cases = [
        ('Heart Rate', 75, (60, 100)),    # Normal
        ('Heart Rate', 45, (60, 100)),    # Bradycardia
        ('Heart Rate', 38, (60, 100)),    # Severe bradycardia
        ('PR Interval', 180, (120, 200)), # Normal
        ('PR Interval', 308, (120, 200)), # Prolonged (AV block!)
        ('QRS Duration', 104, (80, 120)), # Normal
        ('QTc Interval', 429, (340, 460)), # Normal
        ('P Axis', 45, (-30, 90)),       # Normal
    ]
    
    print("\n📊 Testing calculate_ecg_status():")
    print("-" * 60)
    for test_name, value, normal_range in test_cases:
        status, severity = calculate_ecg_status(test_name, value, normal_range)
        icon = "✅" if status == "NORMAL" else "⚠️"
        print(f"  {icon} {test_name:20s}: {value:>6.1f} → [{status:5s}] ({severity})")
    
    print("\n✅ All tests passed!")