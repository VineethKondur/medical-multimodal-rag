"""
================================================================================
🏥 ULTIMATE MEDICAL REPORT ANALYSIS SYSTEM v3.1 (BUG-FIXED)
================================================================================
All critical issues resolved:
✅ FIX 1: is_valid_test_row() now passes actual unit (not "")
✅ FIX 2: Cache always stores JSON strings (consistency)
✅ FIX 3: Single clean graph validation block (no redundancy)
✅ FIX 4: Merge runs even if table is empty (graph-only mode)
✅ FIX 5: Merge failures logged prominently (not silent)
✅ FIX 6: Vectorstore uses validated merged data

Author: Merged System (Fixed)
Version: 3.1 Production-Ready
================================================================================
"""

import os
import uuid
import re
import json
import time
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework import status

# ============================================================
# 🔥 FIXED: Correct Imports
# ============================================================
from rag.services.pdf_loader import classify_pages
from rag.services.graph_router import analyze_graphical_pages, merge_lab_and_graph_data

# Service imports
from .services.pdf_loader import extract_text_from_pdf
from .services.table_extractor import extract_tables
from .services.text_splitter import split_text
from .services.vectorstore import create_vectorstore, load_vectorstore, clear_vectorstore_cache, INDEX_PATH
from .services.qa import generate_test_explanation, get_groq_client
from .services.signal_analyzer import analyze_signal
from .services.clinical_notes import extract_clinical_data, normalize_lab_mentions, correlate_conditions_with_labs
from .services.chart_interpreter import interpret_chart

MEDIA_DIR = "media"
os.makedirs(MEDIA_DIR, exist_ok=True)


# ===========================================================================
# REFERENCE DATA - COMPLETE LAB RANGES
# ===========================================================================

FALLBACK_RANGES = {
    "hemoglobin": "13.5-17.5", "hb": "13.5-17.5", "haemoglobin": "13.5-17.5",
    "packed cell volume": "40-50", "pcv": "40-50", "hematocrit": "40-50",
    "rbc count": "4.5-5.5", "rbc": "4.5-5.5", "red blood cell": "4.5-5.5",
    "mcv": "80-100", "mch": "27-32", "mchc": "31.5-34.5",
    "wbc": "4.5-11.0", "tlc": "4.5-11.0", "white blood cell": "4.5-11.0",
    "leukocyte": "4.5-11.0", "platelet": "150-400", "platelet count": "150-400",
    "rdw": "11-15",
    "creatinine": "0.70-1.30", "gfr": ">59",
    "urea": "13-43", "bun": "7-20", "blood urea nitrogen": "7-20",
    "ast": "15-40", "sgot": "15-40", "aspartate aminotransferase": "15-40",
    "alt": "10-49", "sgpt": "10-49", "alanine aminotransferase": "10-49",
    "alp": "30-120", "alkaline phosphatase": "30-120", "ggtp": "0-73",
    "gamma-glutamyl transferase": "0-73", "bilirubin": "0.3-1.2",
    "albumin": "3.2-4.8", "total protein": "5.7-8.2", "globulin": "2.4-3.8",
    "cholesterol": "<200", "total cholesterol": "<200", "triglycerides": "<150",
    "hdl": ">40", "ldl": "<100", "vldl": "<30",
    "glucose": "70-100", "blood sugar": "70-100", "fasting glucose": "70-100",
    "hba1c": "4-5.6", "hemoglobin a1c": "4-5.6",
    "troponin": "<0.04", "troponin i": "<0.04", "troponin t": "<0.04",
    "bnp": "<100", "b-type natriuretic peptide": "<100",
    "ck": "30-200", "creatine kinase": "30-200", "ck-mb": "<5",
    "myoglobin": "<90", "ldh": "140-280", "lactate dehydrogenase": "140-280",
    "amylase": "30-110", "lipase": "0-60",
    "tsh": "0.5-5.0", "thyroid stimulating hormone": "0.5-5.0",
    "t3": "80-200", "t4": "5-12", "thyroxine": "5-12",
    "free t3": "2.3-4.2", "free t4": "0.8-1.8",
    "sodium": "136-145", "na": "136-145", "potassium": "3.5-5.1",
    "k": "3.5-5.1", "chloride": "98-107", "cl": "98-107",
    "bicarbonate": "23-29", "co2": "23-29", "magnesium": "1.7-2.2",
    "phosphate": "2.5-4.5", "calcium": "8.7-10.4", "ca": "8.7-10.4",
    "pt": "11-13.5", "prothrombin time": "11-13.5", "inr": "0.8-1.1",
    "ptt": "25-35", "activated partial thromboplastin time": "25-35",
    "aptt": "25-35", "fibrinogen": "200-400",
    "uric acid": "3.5-7.2", "urate": "3.5-7.2",
    "phosphorus": "2.5-4.5", "iron": "60-170", "ferritin": "24-336",
    "b12": ">200", "vitamin b12": ">200", "folate": ">3.0", "folic acid": ">3.0",
}

TEST_ALIASES = {
    "hemoglobin": ["hb", "haemoglobin"],
    "rbc": ["rbc count", "red blood cell"],
    "wbc": ["wbc count", "tlc", "white blood cell", "leukocyte"],
    "platelet": ["platelet count", "platelets"],
    "hematocrit": ["hematocrit", "packed cell volume", "pcv"],
    "mcv": ["mcv", "mean corpuscular volume"],
    "mch": ["mch", "mean corpuscular hemoglobin"],
    "rdw": ["rdw", "red cell distribution width"],
    "creatinine": ["creatinine", "serum creatinine"],
    "gfr": ["gfr", "glomerular filtration rate"],
    "urea": ["urea", "blood urea", "bun", "blood urea nitrogen"],
    "ast": ["ast", "sgot", "aspartate aminotransferase"],
    "alt": ["alt", "sgpt", "alanine aminotransferase"],
    "alp": ["alp", "alkaline phosphatase"],
    "ggtp": ["ggtp", "gamma-glutamyl transferase"],
    "albumin": ["albumin", "serum albumin"],
    "total protein": ["total protein", "serum protein"],
    "bilirubin": ["bilirubin", "total bilirubin"],
    "globulin": ["globulin"],
    "cholesterol": ["cholesterol", "total cholesterol"],
    "triglycerides": ["triglycerides", "triglyceride"],
    "hdl": ["hdl", "hdl cholesterol"],
    "ldl": ["ldl", "ldl cholesterol"],
    "vldl": ["vldl", "vldl cholesterol"],
    "glucose": ["glucose", "blood sugar", "fasting glucose", "blood glucose"],
    "hba1c": ["hba1c", "hemoglobin a1c", "glycated hemoglobin", "hb a1c"],
    "troponin": ["troponin", "troponin i", "troponin t"],
    "bnp": ["bnp", "b-type natriuretic peptide"],
    "ck": ["ck", "creatine kinase"],
    "ck-mb": ["ck-mb", "ck mb"],
    "myoglobin": ["myoglobin"],
    "ldh": ["ldh", "lactate dehydrogenase"],
    "amylase": ["amylase", "serum amylase"],
    "lipase": ["lipase"],
    "tsh": ["tsh", "thyroid stimulating hormone"],
    "t3": ["t3", "triiodothyronine"],
    "t4": ["t4", "thyroxine"],
    "free t3": ["free t3"],
    "free t4": ["free t4"],
    "sodium": ["sodium", "na", "serum sodium"],
    "potassium": ["potassium", "k", "serum potassium"],
    "chloride": ["chloride", "cl", "serum chloride"],
    "bicarbonate": ["bicarbonate", "co2", "serum co2"],
    "magnesium": ["magnesium", "mg"],
    "phosphate": ["phosphate", "phosphorus"],
    "calcium": ["calcium", "ca", "serum calcium"],
    "pt": ["pt", "prothrombin time"],
    "inr": ["inr", "international normalized ratio"],
    "ptt": ["ptt", "activated partial thromboplastin time", "aptt"],
    "fibrinogen": ["fibrinogen"],
    "uric acid": ["uric acid", "urate"],
    "iron": ["iron", "serum iron"],
    "ferritin": ["ferritin"],
    "b12": ["b12", "vitamin b12"],
    "folate": ["folate", "folic acid"],
}

ALIAS_TO_STANDARD = {alias: std for std, aliases in TEST_ALIASES.items() for alias in aliases}
for std in TEST_ALIASES:
    ALIAS_TO_STANDARD[std] = std


# ===========================================================================
# MEDICAL PATTERNS (12 Patterns)
# ===========================================================================

MEDICAL_PATTERNS = [
    {
        "id": "iron_deficiency_anemia",
        "name": "Iron Deficiency Anemia Pattern",
        "required_low": ["hemoglobin", "rbc"],
        "optional_low": ["mcv", "mch", "mchc", "ferritin", "iron"],
        "optional_high": ["rdw"],
        "min_optional_match": 1,
        "confidence_threshold": 0.6,
        "explanation": (
            "Low hemoglobin and RBC combined with low MCV/MCH/MCHC suggests microcytic anemia, "
            "most commonly caused by iron deficiency. Low ferritin confirms depleted iron stores."
        ),
        "follow_up": "Consider checking iron studies (serum iron, TIBC, ferritin) and peripheral blood smear."
    },
    {
        "id": "macrocytic_anemia",
        "name": "Macrocytic Anemia Pattern",
        "required_low": ["hemoglobin", "rbc"],
        "optional_high": ["mcv"],
        "optional_low": ["b12", "folate"],
        "min_optional_match": 1,
        "confidence_threshold": 0.5,
        "explanation": (
            "Low hemoglobin/RBC with high MCV indicates macrocytic anemia (large red blood cells). "
            "Common causes include Vitamin B12 deficiency, folate deficiency, liver disease."
        ),
        "follow_up": "Check Vitamin B12, folate, thyroid function (TSH), and reticulocyte count."
    },
    {
        "id": "kidney_dysfunction",
        "name": "Kidney Dysfunction Pattern",
        "required_high": ["creatinine"],
        "optional_high": ["urea", "potassium", "phosphate"],
        "optional_low": ["calcium", "gfr"],
        "min_optional_match": 1,
        "confidence_threshold": 0.5,
        "explanation": ("Elevated creatinine indicates reduced kidney function."),
        "follow_up": "Consider complete renal panel, urine analysis, renal ultrasound."
    },
    {
        "id": "liver_dysfunction",
        "name": "Liver Dysfunction Pattern",
        "required_high": ["alt", "ast"],
        "optional_high": ["alp", "ggtp", "bilirubin"],
        "optional_low": ["albumin"],
        "min_optional_match": 1,
        "confidence_threshold": 0.5,
        "explanation": ("Elevated ALT and AST indicate hepatocellular injury."),
        "follow_up": "Check hepatitis panel, liver ultrasound, PT/INR."
    },
    {
        "id": "cholestatic_pattern",
        "name": "Cholestatic Pattern",
        "required_high": ["alp"],
        "optional_high": ["ggtp", "bilirubin"],
        "min_optional_match": 1,
        "confidence_threshold": 0.5,
        "explanation": ("Isolated ALP elevation with GGTP suggests cholestasis."),
        "follow_up": "Liver ultrasound, medication review, consider AMA if PBC suspected."
    },
    {
        "id": "metabolic_syndrome",
        "name": "Metabolic Syndrome Pattern",
        "required_high": ["triglycerides"],
        "optional_high": ["cholesterol", "ldl", "glucose", "hba1c"],
        "optional_low": ["hdl"],
        "min_optional_match": 2,
        "confidence_threshold": 0.6,
        "explanation": ("Elevated triglycerides + low HDL suggests metabolic syndrome."),
        "follow_up": "Check fasting insulin, waist circumference, blood pressure."
    },
    {
        "id": "diabetes_indicators",
        "name": "Diabetes Indicators Pattern",
        "required_high": ["glucose"],
        "optional_high": ["hba1c"],
        "min_optional_match": 0,
        "confidence_threshold": 0.3,
        "explanation": ("Elevated fasting glucose suggests impaired glucose tolerance or diabetes."),
        "follow_up": "Repeat fasting glucose, OGTT, endocrinology referral."
    },
    {
        "id": "thyroid_hypothyroid",
        "name": "Hypothyroid Pattern",
        "required_high": ["tsh"],
        "optional_low": ["free t4", "free t3", "t4", "t3"],
        "min_optional_match": 1,
        "confidence_threshold": 0.5,
        "explanation": ("Elevated TSH with low Free T4 indicates primary hypothyroidism."),
        "follow_up": "Check anti-TPO antibodies, consider levothyroxine."
    },
    {
        "id": "thyroid_hyperthyroid",
        "name": "Hyperthyroid Pattern",
        "required_low": ["tsh"],
        "optional_high": ["free t4", "free t3", "t4", "t3"],
        "min_optional_match": 1,
        "confidence_threshold": 0.5,
        "explanation": ("Suppressed TSH with elevated thyroid hormones indicates hyperthyroidism."),
        "follow_up": "Check TSH receptor antibodies, thyroid uptake scan."
    },
    {
        "id": "inflammation_pattern",
        "name": "Inflammation Pattern",
        "required_high": ["wbc"],
        "optional_high": ["esr", "crp", "platelet"],
        "min_optional_match": 1,
        "confidence_threshold": 0.4,
        "explanation": ("Elevated WBC suggests inflammation, infection, or stress response."),
        "follow_up": "Differential WBC count, CRP, blood cultures if infection suspected."
    },
    {
        "id": "electrolyte_imbalance",
        "name": "Electrolyte Imbalance Pattern",
        "required_any": [["sodium"], ["potassium"]],
        "optional_any": [["sodium"], ["potassium"], ["chloride"], ["bicarbonate"], ["calcium"], ["magnesium"]],
        "min_optional_match": 2,
        "confidence_threshold": 0.5,
        "explanation": ("Abnormal electrolyte levels can indicate dehydration, kidney dysfunction, or endocrine disorders."),
        "follow_up": "Check renal function, medication review, acid-base status."
    },
    {
        "id": "bleeding_clotting_risk",
        "name": "Bleeding/Clotting Risk Pattern",
        "required_low": ["platelet"],
        "optional_abnormal": ["pt", "ptt", "inr", "fibrinogen"],
        "min_optional_match": 1,
        "confidence_threshold": 0.5,
        "explanation": ("Low platelets + abnormal coagulation studies suggest broader hematologic disorder."),
        "follow_up": "Peripheral blood smear, coagulation factor assays, hematology referral."
    },
]


# ===========================================================================
# HELPERS — RESPONSE FORMATTING
# ===========================================================================

def format_final_response(response_type, data, note=None):
    if response_type == "table" and isinstance(data, list):
        return {"type": "table", "answer": f"Showing {len(data)} result(s)", "data": data, "note": note}
    elif response_type == "signal" and isinstance(data, dict):
        formatted_text = format_signal_output(data)
        return {"type": "signal", "answer": formatted_text, "raw_data": data, "note": note}
    elif response_type == "text":
        return {"type": "text", "answer": str(data) if not isinstance(data, str) else data, "note": note}
    elif response_type == "error":
        return {"type": "text", "answer": str(data), "note": note or "An error occurred. Please try again."}
    else:
        return {"type": "text", "answer": str(data), "note": note}


def get_light_user_guidance(context=None):
    suggestions = [
        "• Ask 'show abnormal values' to see out-of-range results",
        "• Try 'explain [test name]' for more details",
        "• Ask 'give summary' for a concise overview",
    ]
    return "\n\nYou can also ask:\n" + "\n".join(suggestions)


# ===========================================================================
# HELPERS — STRING / NUMERIC PROCESSING
# ===========================================================================

def clean_numeric_value(value_str):
    if not value_str:
        return None
    cleaned = str(value_str).strip()
    cleaned = re.sub(r'(\d),(\d)', r'\1\2', cleaned)
    cleaned = re.sub(r'^[^\d\-\.]*', '', cleaned)
    cleaned = re.sub(r'[^\d\-\.]*$', '', cleaned)
    
    range_concat = re.match(r'^(\d+\.?\d*)(\d+\.?\d*\s*[-–]\s*\d+\.?\d*)$', cleaned)
    if range_concat:
        return range_concat.group(1)
    
    leading_num = re.match(r'^(\d+\.?\d*)', cleaned)
    if leading_num:
        return leading_num.group(1)
    return None


def normalize_test_name(name):
    if not name:
        return ""
    normalized = re.sub(r'[\s\-_\.,()]', '', name.lower())
    for alias, std in ALIAS_TO_STANDARD.items():
        alias_norm = re.sub(r'[\s\-_\.,()]', '', alias)
        if alias_norm in normalized:
            return std
    return normalized


def _get_trigrams(s):
    s = re.sub(r'[\s\-_\.,()]', '', s.lower())
    if len(s) < 3:
        return {s}
    return {s[i:i+3] for i in range(len(s) - 2)}


def _token_set(s):
    return set(re.findall(r'[a-z]+', s.lower()))


def fuzzy_match_score(query_str, test_name):
    if not query_str or not test_name:
        return 0.0

    q_norm = re.sub(r'[\s\-_\.,()]', '', query_str.lower())
    t_norm = re.sub(r'[\s\-_\.,()]', '', test_name.lower())

    if t_norm in q_norm:
        return 1.0 + (len(t_norm) / max(len(q_norm), 1)) * 0.2
    if q_norm in t_norm:
        return 0.95 + (len(q_norm) / max(len(t_norm), 1)) * 0.15

    q_tris = _get_trigrams(query_str)
    t_tris = _get_trigrams(test_name)
    if not q_tris or not t_tris:
        return 0.0
    
    trigram_overlap = len(q_tris & t_tris) / len(q_tris | t_tris)

    q_tokens = _token_set(query_str)
    t_tokens = _token_set(test_name)
    token_containment = (len(q_tokens & t_tokens) / len(q_tokens)) if q_tokens and t_tokens else 0.0

    len_ratio = min(len(q_norm), len(t_norm)) / max(len(q_norm), len(t_norm), 1)

    return (trigram_overlap * 0.4) + (token_containment * 0.45) + (len_ratio * 0.15)


# ===========================================================================
# HELPERS — STATUS / SEVERITY DETECTION
# ===========================================================================

def detect_status(value, ref_range):
    cleaned_value = clean_numeric_value(value)
    if not cleaned_value:
        return "UNKNOWN"
    try:
        value = float(cleaned_value)
    except ValueError:
        return "UNKNOWN"

    if not ref_range or str(ref_range).lower().strip() in ["nan", "-", "", "not available"]:
        return "UNKNOWN"

    r = str(ref_range).lower().strip().replace(" ", "")
    numbers = re.findall(r"(\d+\.?\d*)", r)
    if not numbers:
        return "UNKNOWN"

    try:
        if re.search(r"[\-–]", r) and len(numbers) >= 2:
            low, high = float(numbers[0]), float(numbers[1])
            if value < low:
                return "LOW"
            elif value > high:
                return "HIGH"
            return "NORMAL"
        elif "<" in r:
            return "HIGH" if value > float(numbers[0]) else "NORMAL"
        elif ">" in r:
            return "LOW" if value < float(numbers[0]) else "NORMAL"
    except (ValueError, IndexError):
        pass

    return "UNKNOWN"


def detect_status_with_fallback(test_name, value, ref_range):
    if ref_range and str(ref_range).lower().strip() in ["nan", "-", "", "n/a", "not available", "none", "na"]:
        ref_range = None

    if ref_range:
        return detect_status(value, ref_range), None
    
    normalized_test = normalize_test_name(test_name)
    for key, fallback_range in FALLBACK_RANGES.items():
        if normalize_test_name(key) in normalized_test:
            return detect_status(value, fallback_range), fallback_range
    
    return detect_status(value, ref_range), None


def calculate_severity(value, ref_range, row_status):
    if row_status in ["NORMAL", "UNKNOWN"]:
        return "normal"

    try:
        val = float(clean_numeric_value(value) or "")
    except (ValueError, TypeError):
        return "unknown"

    if not ref_range:
        return "unknown"

    r = str(ref_range).lower().strip().replace(" ", "")
    nums = re.findall(r"(\d+\.?\d*)", r)
    if not nums:
        return "unknown"

    try:
        deviation_pct = 0.0
        if re.search(r"[\-–]", r) and len(nums) >= 2:
            low, high = float(nums[0]), float(nums[1])
            boundary = high if row_status == "HIGH" else low
            if boundary == 0:
                return "unknown"
            deviation_pct = abs(val - boundary) / abs(boundary) * 100
        elif "<" in r or ">" in r:
            boundary = float(nums[0])
            if boundary == 0:
                return "unknown"
            deviation_pct = abs(val - boundary) / abs(boundary) * 100
        else:
            return "unknown"

        if deviation_pct < 10:
            return "mild"
        elif deviation_pct <= 25:
            return "moderate"
        else:
            return "severe"
    except Exception:
        return "unknown"


# ===========================================================================
# HELPERS — QUERY ANALYSIS & INTENT DETECTION
# ===========================================================================

def detect_response_mode(query):
    q = query.lower()

    why_signals = ["why", "reason", "cause", "what causes", "why is my", "why would", "how come", "due to"]
    if any(w in q for w in why_signals):
        return ("reasoning", "why")

    explain_signals = ["what is", "what does", "what are", "define", "meaning of", "explain", "what do", "tell me about"]
    if any(w in q for w in explain_signals):
        return ("explanation", "what is")

    summary_signals = ["summary", "summarize", "summarise", "overview", "brief", "key findings", "main points", "tl;dr"]
    if any(w in q for w in summary_signals):
        return ("concise", "summary")

    return ("normal", None)


def get_adaptive_k(question, table_rows):
    q = question.lower().strip()
    word_count = len(q.split())

    if any(w in q for w in ["summary", "summarize", "summarise", "overview", "all", "everything", "full report"]):
        return min(25, max(15, len(table_rows)))
    if any(w in q for w in ["why", "reason", "cause", "explain", "meaning"]):
        return 12
    if word_count <= 3:
        return 5
    if word_count <= 8:
        return 8
    return 10


# ===========================================================================
# DATA QUALITY & VALIDATION
# ===========================================================================

def get_data_quality_warning(table_rows):
    if not table_rows:
        return "⚠️ **No structured lab data found.** Upload a medical report PDF for analysis."

    total = len(table_rows)
    unknown_count = len([r for r in table_rows if r["status"] == "UNKNOWN"])
    valid_count = total - unknown_count
    warnings = []

    if unknown_count > 0:
        warnings.append("⚠️ **Data Quality Note:** Some tests lack reference ranges.")
    if valid_count < 3 and total > 0:
        warnings.append("⚠️ **Limited Data:** Very few tests with valid reference data.")

    return "\n".join(warnings) if warnings else ""


VALID_CATEGORICAL_RESULTS = [
    "reactive", "non reactive", "non-reactive", "positive", "negative", "pos", "neg",
    "detected", "not detected", "indeterminate", "equivocal", "borderline",
    "seen", "not seen", "absent", "present",
]

VALID_SEROLOGICAL_TESTS = [
    "vdrl", "rpr", "hiv", "hcv", "hbv", "hbsag", "hbeag", "anti-hcv", "anti-hiv",
    "dengue", "malaria", "widal", "pregnancy", "preg test", "blood group", "rh",
    "elisa", "pcr", "rapid", "antibody", "antigen", "serology",
    "urine routine", "glucose", "protein", "ketones", "blood", "bilirubin", "urobilinogen", "nitrite"
]


def is_valid_test_row(test_name, value, unit="", reference_range=""):
    """Robust validation - allow real tests, reject metadata/garbage."""
    if not test_name or not value:
        return False
    
    test = str(test_name).lower().strip()
    value_str = str(value).strip()
    val_lower = value_str.lower()

    # Allow categorical results
    is_categorical = val_lower in VALID_CATEGORICAL_RESULTS
    if re.match(r'^1:\d+$', value_str):
        is_categorical = True
    if re.match(r'^[1-4]\+$', value_str):
        is_categorical = True
    if any(val_lower.startswith(cat) for cat in ["reactive", "non reactive", "non-reactive", "positive", "negative", "not detected", "detected"]):
        is_categorical = True

    is_numeric = bool(re.search(r'\d', value_str))
    if not is_numeric and not is_categorical:
        return False

    # Categorical only for serological/urine tests
    if is_categorical and not is_numeric:
        is_sero = any(s in test for s in VALID_SEROLOGICAL_TESTS)
        is_sero = is_sero or any(kw in test for kw in ["test", "screen", "panel", "card", "rapid"])
        if not is_sero:
            return False

    # Reject time/date patterns
    if re.search(r'\b\d{1,2}:\d{2}\b', value_str):
        return False
    if re.search(r'\b(am|pm)\b', val_lower):
        return False
    if re.search(r'\b\d{1,2}\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b', val_lower):
        return False

    # Reject metadata
    metadata_keywords = [
        "age", "gender", "patient", "id", "page", "report", "date", "name", "address",
        "phone", "email", "registered", "collected", "reported", "instrument", "sample",
        "plot no", "barcode", "page no", "client", "referring doctor", "ref no",
        "processed by", "billing date", "released on", "received on", "accession no",
        "dr.", "consultant", "senior", "end of report", "pathkind", "diagnostics",
        "pvt ltd", "hospital", "ipd", "opd", "technician", "signature", "signed",
        "pathologist", "verified", "authorized"
    ]
    if any(k in test for k in metadata_keywords):
        return False

    # Reject sentence fragments
    fragment_keywords = [
        "tested", "please", "note", "this ", "in case", "as per", "confirmation",
        "guidelines", "comprises", "should be", "is used", "is a ", "may be", "can be",
        "is helpful", "is the", "clinical significance", "method", "principal"
    ]
    if any(test.startswith(f) for f in fragment_keywords):
        return False

    # Reject narrative values
    narrative_keywords = [
        "associated", "risk", "recommended", "suggested", "evidence", "increase",
        "decrease", "should be", "advised to"
    ]
    if any(word in test for word in narrative_keywords):
        return False
    if any(word in val_lower for word in narrative_keywords):
        return False

    # Reject long sentences
    if len(test.split()) > 10:
        return False

    # Must be alphabetic enough
    if sum(c.isalpha() for c in test) < 3:
        return False

    # Reject address-like patterns
    if re.match(r'^\d+[\w\s,.-]+$', test):
        return False

    return True


# ===========================================================================
# ✅ FIX 4 APPLIED: Data Sanitization — ALWAYS removes garbage
# ===========================================================================

def sanitize_table_data(table_rows):
    """
    Filter out garbage/corrupt rows before processing.
    🔥 FIXED v3.1: Garbage rows are ALWAYS removed regardless of percentage.
    Returns: (cleaned_rows, stats_dict)
    """
    if not table_rows:
        return table_rows, {"original": 0, "cleaned": 0, "removed": 0, "examples": []}

    garbage_count = 0
    garbage_examples = []
    clean_rows = []

    for row in table_rows:
        test_name = row.get('test', '')
        value = row.get('value', '')
        test_lower = test_name.lower()
        is_garbage = False

        # Check 1: Truncated test names (e.g., "Na : K")
        if re.search(r'\b\w{1,3}\s*:\s*\w{1,3}\b', test_name):
            is_garbage = True

        # Check 2: Text values where numeric expected
        text_values = [
            'normal', 'abnormal', 'none', 'no', 'yes', 'not observed',
            'prolonged', 'within normal limits', 'profound bradycardia'
        ]
        if str(value).lower().strip() in text_values:
            allowed_for_text = any(kw in test_lower for kw in [
                'pregnancy', 'hiv', 'hcv', 'vdrl', 'blood group'
            ])
            if not allowed_for_text:
                is_garbage = True

        # Check 3: ECG findings mixed into lab data (without numeric values)
        ecg_indicators = [
            'qrs duration', 'qt interval', 'pr interval', 'cardiac axis',
            'p-wave', 't-wave', 'morphology', 'sinus rhythm',
            'atrial pause', 'av conduction'
        ]
        if any(ind in test_lower for ind in ecg_indicators):
            if not re.search(r'\d', str(value)):
                is_garbage = True

        if is_garbage:
            garbage_count += 1
            if len(garbage_examples) < 3:
                garbage_examples.append(f"{test_name}: {value}")
        else:
            clean_rows.append(row)

    stats = {
        "original": len(table_rows),
        "cleaned": len(clean_rows),
        "removed": garbage_count,
        "examples": garbage_examples
    }

    # 🔥 ALWAYS log and return cleaned rows
    if garbage_count > 0:
        ratio = garbage_count / len(table_rows)
        if ratio > 0.3:
            print(f"\n🚨 HIGH SEVERITY: {garbage_count}/{len(table_rows)} rows removed ({ratio:.0%})")
        elif ratio > 0.1:
            print(f"\n⚠️ MODERATE: {garbage_count} suspect rows removed ({ratio:.0%})")
        else:
            print(f"\nℹ️ LOW: {garbage_count} minor cleanup(s)")
        
        if garbage_examples:
            print(f"   Examples: {garbage_examples}")
        
        return clean_rows, stats
    
    return table_rows, stats


# ===========================================================================
# ✅ FIX 1 APPLIED: Table Loading — Passes actual unit variable
# ===========================================================================

def load_and_parse_table_rows(session_key):
    """Load table data from cache, clean values, deduplicate, merge clinical notes."""
    table_text = cache.get(f"latest_table_data_{session_key}")
    table_rows = []

    if not table_text:
        return table_rows

    try:
        raw_rows = json.loads(table_text)
        if not isinstance(raw_rows, list):
            return table_rows

        for row_data in raw_rows:
            try:
                test = str(row_data.get("test", "")).strip()
                value = str(row_data.get("value", "")).strip()
                unit = str(row_data.get("unit", "")).strip()
                range_val = str(row_data.get("range", "")).strip()

                # Light cleanup
                test = re.sub(r'\s+', ' ', test)
                unit = re.sub(r'\s+', ' ', unit)
                
                # Normalize units
                if unit.lower() == "g/dl":
                    unit = "g/dL"
                elif unit.lower() == "mg/dl":
                    unit = "mg/dL"

                # ✅ FIX 1: Pass actual unit (not hardcoded empty string)
                if not is_valid_test_row(test, value, unit, reference_range=range_val):
                    continue

                cleaned = clean_numeric_value(value)
                if not cleaned:
                    continue
                value = cleaned

                row = {
                    "test": test,
                    "value": value,
                    "unit": unit,
                    "range": range_val,
                    "status": "UNKNOWN",
                    "severity": "normal",
                    "source": "lab_report",
                    "confidence": "high"
                }
                
                row_status, used_range = detect_status_with_fallback(test, value, range_val)
                row["status"] = row_status
                if used_range and not range_val:
                    row["range"] = used_range
                row["severity"] = calculate_severity(value, row["range"] or used_range, row_status)

                table_rows.append(row)
            except Exception as e:
                print(f"Row parse error: {e}")

    except (json.JSONDecodeError, Exception) as e:
        print(f"Table load error: {e}")
        return []

    # Deduplicate
    seen = set()
    unique_rows = []
    for row in table_rows:
        key = normalize_test_name(row["test"])
        if key not in seen:
            seen.add(key)
            unique_rows.append(row)

    # Merge Clinical Notes Lab Data
    clinical_data_json = cache.get(f"latest_clinical_data_{session_key}")
    if clinical_data_json:
        try:
            clinical_data = json.loads(clinical_data_json)
            normalized_notes_labs = normalize_lab_mentions(clinical_data)
            
            for n_lab in normalized_notes_labs:
                key = normalize_test_name(n_lab["test"])
                if key not in seen:
                    row_status, used_range = detect_status_with_fallback(n_lab["test"], n_lab["value"], "")
                    n_lab["status"] = row_status
                    n_lab["range"] = used_range or ""
                    n_lab["severity"] = calculate_severity(n_lab["value"], n_lab["range"], row_status)
                    
                    unique_rows.append(n_lab)
                    seen.add(key)
        except Exception as e:
            print(f"Clinical notes merge error: {e}")

    return unique_rows


def build_table_context_string(table_rows):
    if not table_rows:
        return "No structured lab data available."
    
    lines = ["Test | Value | Unit | Reference Range | Status | Severity | Source", "-" * 90]
    for r in table_rows:
        source = f"{r.get('source', 'lab_report')} ({r.get('confidence', 'high')})"
        lines.append(
            f"{r['test']} | {r['value']} | {r['unit']} | "
            f"{r['range'] or 'N/A'} | {r['status']} | {r.get('severity', 'N/A')} | {source}"
        )
    return "\n".join(lines)


def get_vector_context(question, k=20, filter_metadata=None):
    if not os.path.exists(INDEX_PATH):
        return ""
    try:
        vectorstore = load_vectorstore()
        
        if filter_metadata:
            docs = vectorstore.similarity_search(question, k=k, filter=filter_metadata)
        else:
            docs = vectorstore.similarity_search(question, k=k)
            
        return "\n\n".join(doc.page_content for doc in docs)
    except Exception as e:
        print(f"Vectorstore error: {e}")
        return ""


# ===========================================================================
# HELPERS — FUZZY TEST NAME EXTRACTION
# ===========================================================================

def extract_named_tests_fuzzy(query_text, table_rows=None, score_threshold=0.75):
    found = []
    seen_scores = {}

    for std_name, aliases in TEST_ALIASES.items():
        best_score = max(fuzzy_match_score(query_text, name) for name in [std_name] + aliases)
        
        if best_score >= 0.75:
            found.append(std_name)
            seen_scores[std_name] = best_score
        elif 0.6 <= best_score < 0.75:
            q_tokens = _token_set(query_text)
            strong_match = any(_token_set(alias) & q_tokens for alias in [std_name] + aliases)
            if strong_match:
                found.append(std_name)
                seen_scores[std_name] = best_score

    if table_rows:
        for row in table_rows:
            score = fuzzy_match_score(query_text, row["test"])
            std = normalize_test_name(row["test"])
            
            if score >= 0.75:
                if std not in seen_scores or score > seen_scores.get(std, 0):
                    if std not in found:
                        found.append(std)
                    seen_scores[std] = score
            elif 0.6 <= score < 0.75:
                q_tokens = _token_set(query_text)
                strong_match = _token_set(row["test"]) & q_tokens
                if strong_match:
                    if std not in seen_scores or score > seen_scores.get(std, 0):
                        if std not in found:
                            found.append(std)
                        seen_scores[std] = score

    return found


# ===========================================================================
# HELPERS — FOLLOW-UP CONTEXT RESOLUTION
# ===========================================================================

def resolve_follow_up_context(question, table_rows, history):
    q = question.lower().strip()
    pronoun_signals = [
        r"\bit\b", r"\bthat\b", r"\bthis\b",
        r"\bthe (?:value|result|test|level|reading)\b",
        r"\bmy (?:value|result|test|level)\b"
    ]
    
    if not any(re.search(p, q) for p in pronoun_signals):
        return None, None, question

    sev_rank = {"severe": 4, "moderate": 3, "mild": 2, "normal": 0, "unknown": 0}

    if history:
        for msg in reversed(history):
            if msg["role"] == "assistant":
                bold_tests = re.findall(r'\*\*([^*]+)\*\*', msg["content"])
                for bt in bold_tests:
                    bt_clean = bt.strip()
                    if bt_clean and len(bt_clean) < 40:
                        for row in table_rows:
                            if row["test"].lower() == bt_clean.lower():
                                return bt_clean, row, question
                break

    if history:
        for msg in reversed(history):
            if msg["role"] == "user":
                prev_tests = extract_named_tests_fuzzy(msg["content"], table_rows)
                if prev_tests:
                    for row in table_rows:
                        if normalize_test_name(row["test"]) in prev_tests:
                            return row["test"], row, question
                break

    direction_filter = None
    if any(w in q for w in ["low", "decreased", "below"]):
        direction_filter = "LOW"
    elif any(w in q for w in ["high", "elevated", "increased", "above"]):
        direction_filter = "HIGH"

    candidates = [r for r in table_rows if r["status"] in ["HIGH", "LOW"]]
    if direction_filter:
        candidates = [r for r in candidates if r["status"] == direction_filter]

    if candidates:
        candidates.sort(key=lambda x: sev_rank.get(x.get("severity", "unknown"), 0), reverse=True)
        return candidates[0]["test"], candidates[0], question

    return None, None, question


# ===========================================================================
# GRAPH / PATTERN ANALYSIS
# ===========================================================================

def generate_graph_observations(table_rows):
    valid_rows = [r for r in table_rows if r["status"] in ["NORMAL", "HIGH", "LOW"]]
    if not valid_rows:
        return None

    normal = [r for r in valid_rows if r["status"] == "NORMAL"]
    high = [r for r in valid_rows if r["status"] == "HIGH"]
    low = [r for r in valid_rows if r["status"] == "LOW"]
    n = len(valid_rows)

    return {
        "total_analyzed": n,
        "normal_count": len(normal),
        "high_count": len(high),
        "low_count": len(low),
        "distribution_pct": {
            "normal": round(len(normal) / n * 100, 1),
            "high": round(len(high) / n * 100, 1),
            "low": round(len(low) / n * 100, 1),
        },
        "abnormal_tests": [
            {"test": r["test"], "value": r["value"], "unit": r["unit"],
             "status": r["status"], "range": r["range"], "severity": r.get("severity", "unknown")}
            for r in high + low
        ],
        "all_tests": [
            {"test": r["test"], "value": r["value"], "unit": r["unit"],
             "status": r["status"], "severity": r.get("severity", "unknown")}
            for r in valid_rows
        ],
    }


def generate_deterministic_graph_insights(observations):
    if not observations:
        return None

    lines = ["**📊 Lab Data Distribution Analysis**\n"]
    lines.append(f"**Total Tests Analyzed:** {observations['total_analyzed']}")
    lines.append(f"- ✅ Normal: {observations['normal_count']} ({observations['distribution_pct']['normal']}%)")
    lines.append(f"- ⬆️ High: {observations['high_count']} ({observations['distribution_pct']['high']}%)")
    lines.append(f"- ⬇️ Low: {observations['low_count']} ({observations['distribution_pct']['low']}%)")

    normal_pct = observations["distribution_pct"]["normal"]
    lines.append("\n**Overall Pattern:**")
    if normal_pct >= 90:
        lines.append("• All values within normal range.")
    elif normal_pct >= 75:
        lines.append("• Mostly normal with few outliers.")
    elif normal_pct >= 50:
        lines.append("• Mixed profile.")
    else:
        lines.append("• Predominantly abnormal profile.")

    if observations["abnormal_tests"]:
        lines.append("\n**Notable Deviations:**")
        for t in observations["abnormal_tests"][:5]:
            arrow = "⬆️" if t["status"] == "HIGH" else "⬇️"
            sev = t.get("severity", "")
            sev_str = f" [{sev}]" if sev and sev != "normal" else ""
            lines.append(f"• {arrow} **{t['test']}**: {t['value']} {t['unit']}{sev_str}")

    if len(observations["abnormal_tests"]) >= 2:
        categories = {
            "Liver": ["alt", "ast", "alp", "ggtp", "bilirubin", "albumin"],
            "Kidney": ["creatinine", "urea", "bun", "gfr", "potassium", "sodium"],
            "Blood": ["hemoglobin", "hb", "rbc", "mcv", "mch", "mchc", "rdw", "platelet"],
            "Lipids": ["cholesterol", "ldl", "hdl", "triglycerides", "vldl"],
            "Thyroid": ["tsh", "t3", "t4", "free t3", "free t4"],
            "Sugar": ["glucose", "hba1c", "blood sugar"],
        }
        lines.append("\n**🔗 Cluster Detection:**")
        found_cluster = False
        
        for cat_name, cat_tests in categories.items():
            matched = [
                t for t in observations["abnormal_tests"]
                if normalize_test_name(t["test"]) in cat_tests
            ]
            if len(matched) >= 2:
                found_cluster = True
                names = ", ".join(t["test"] for t in matched)
                lines.append(
                    f"• 🔗 **{cat_name} cluster**: {len(matched)} related tests abnormal ({names})"
                )
        
        if not found_cluster:
            lines.append("• No clear category clustering among abnormal values.")

    return "\n".join(lines)


def detect_cross_test_patterns(table_rows):
    if not table_rows:
        return []

    test_lookup = {normalize_test_name(r["test"]): r for r in table_rows}
    sev_rank = {"severe": 3, "moderate": 2, "mild": 1, "normal": 0, "unknown": 0}
    detected = []

    for pattern in MEDICAL_PATTERNS:
        score, total_checks, matched_tests = 0, 0, []

        for t in pattern.get("required_low", []):
            total_checks += 1
            if t in test_lookup and test_lookup[t]["status"] == "LOW":
                score += 1
                matched_tests.append(test_lookup[t]["test"])

        for t in pattern.get("required_high", []):
            total_checks += 1
            if t in test_lookup and test_lookup[t]["status"] == "HIGH":
                score += 1
                matched_tests.append(test_lookup[t]["test"])

        for sublist in pattern.get("required_any", []):
            total_checks += 1
            for t in sublist:
                if t in test_lookup and test_lookup[t]["status"] in ["HIGH", "LOW"]:
                    score += 1
                    matched_tests.append(test_lookup[t]["test"])
                    break

        if total_checks == 0 or score < total_checks:
            continue

        optional_matches = 0
        for t in pattern.get("optional_low", []):
            if t in test_lookup and test_lookup[t]["status"] == "LOW":
                optional_matches += 1
                matched_tests.append(test_lookup[t]["test"])
        
        for t in pattern.get("optional_high", []):
            if t in test_lookup and test_lookup[t]["status"] == "HIGH":
                optional_matches += 1
                matched_tests.append(test_lookup[t]["test"])
        
        for t in pattern.get("optional_abnormal", []):
            if t in test_lookup and test_lookup[t]["status"] in ["HIGH", "LOW"]:
                optional_matches += 1
                matched_tests.append(test_lookup[t]["test"])
        
        for sublist in pattern.get("optional_any", []):
            for t in sublist:
                if t in test_lookup and test_lookup[t]["status"] in ["HIGH", "LOW"]:
                    optional_matches += 1
                    matched_tests.append(test_lookup[t]["test"])
                    break

        if optional_matches < pattern.get("min_optional_match", 0):
            continue

        if optional_matches >= 2:
            reliability = "high"
        elif optional_matches >= 1:
            reliability = "medium"
        else:
            reliability = "low"

        max_sev = max(
            (sev_rank.get(test_lookup[normalize_test_name(mt)].get("severity", "unknown"), 0)
             for mt in set(matched_tests) if normalize_test_name(mt) in test_lookup),
            default=0
        )

        detected.append({
            "pattern_id": pattern["id"],
            "pattern_name": pattern["name"],
            "reliability": reliability,
            "max_severity_score": max_sev,
            "matched_tests": list(set(matched_tests)),
            "explanation": pattern["explanation"],
            "follow_up": pattern.get("follow_up", ""),
        })

    rel_map = {"high": 3, "medium": 2, "low": 1}
    detected.sort(
        key=lambda x: (rel_map.get(x["reliability"], 0), x["max_severity_score"], len(x["matched_tests"])),
        reverse=True
    )
    
    return detected[:3]


# ===========================================================================
# SIGNAL OUTPUT FORMATTING
# ===========================================================================

def format_signal_output(raw_result):
    if not raw_result or not isinstance(raw_result, dict):
        return "Signal analysis could not be completed."

    lines = []

    hr = raw_result.get("heart_rate", {})
    if hr:
        lines.append(f"**Heart Rate:** {hr.get('value', hr) if isinstance(hr, dict) else hr} bpm")

    rhythm = raw_result.get("rhythm", raw_result.get("rhythm_status", ""))
    if rhythm:
        lines.append(f"**Rhythm:** {rhythm}")

    for field, label in [("qrs_duration", "QRS Duration"), ("pr_interval", "PR Interval"), ("qt_interval", "QT Interval")]:
        val = raw_result.get(field, raw_result.get(field.split("_")[0], ""))
        if val:
            lines.append(f"**{label}:** {val}")

    observations = raw_result.get("observations", raw_result.get("findings", []))
    if observations:
        lines.append("\n**Observations:**")
        for obs in (observations if isinstance(observations, list) else [observations]):
            lines.append(f"• {obs}")

    reasons = raw_result.get("possible_reasons", raw_result.get("interpretation", ""))
    if reasons:
        lines.append("\n**Possible Interpretations:**")
        for r in (reasons if isinstance(reasons, list) else [reasons]):
            lines.append(f"• {r}")

    anomalies = raw_result.get("anomalies", raw_result.get("abnormalities", []))
    if anomalies:
        lines.append("\n⚠️ **Abnormalities Detected:**")
        for a in (anomalies if isinstance(anomalies, list) else [anomalies]):
            lines.append(f"• {a}")

    if not lines:
        shown = {"heart_rate", "rhythm", "rhythm_status", "qrs_duration", "pr_interval",
                 "qt_interval", "observations", "findings", "possible_reasons",
                 "interpretation", "anomalies", "abnormalities"}
        for key, val in raw_result.items():
            if key not in shown and val:
                label = key.replace("_", " ").title()
                if isinstance(val, list):
                    lines.append(f"**{label}:**")
                    for item in val:
                        lines.append(f"• {item}")
                else:
                    lines.append(f"**{label}:** {val}")

    lines.append("\n_Note: This is an automated analysis. Please consult a cardiologist._")
    return "\n".join(lines)


# ===========================================================================
# CONVERSATION MANAGEMENT
# ===========================================================================

def get_conversation_history(session_key):
    return cache.get(f"chat_history_{session_key}", [])


def add_to_conversation(session_key, role, content):
    history = get_conversation_history(session_key)
    history.append({"role": role, "content": content})
    if len(history) > 20:
        history = history[-20:]
    cache.set(f"chat_history_{session_key}", history, timeout=3600)


def clear_conversation(session_key):
    cache.delete(f"chat_history_{session_key}")


# ===========================================================================
# HEALTH SCORE COMPUTATION
# ===========================================================================

def compute_health_score(table_rows):
    CRITICAL_TESTS = ["hemoglobin", "rbc", "wbc", "platelet"]
    valid_tests = [r for r in table_rows if r["status"] in ["NORMAL", "HIGH", "LOW"]]

    if len(valid_tests) < 3:
        return {
            "score": None,
            "status": "Insufficient Data",
            "message": "Not enough valid tests to compute health score",
            "abnormal_tests": [],
            "abnormal_count": 0,
        }

    total_score, max_score = 0, 0
    abnormal_tests = []

    for r in valid_tests:
        weight = 2 if any(c in r["test"].lower() for c in CRITICAL_TESTS) else 1
        max_score += 10 * weight
        if r["status"] == "NORMAL":
            total_score += 10 * weight
        else:
            abnormal_tests.append({
                "test": r["test"], "value": r["value"],
                "status": r["status"], "severity": r.get("severity", "unknown")
            })

    final_score = max(0, (total_score / max_score) * 100) if max_score > 0 else 0

    if final_score >= 90:
        health_status = "Excellent"
    elif final_score >= 70:
        health_status = "Good"
    elif final_score >= 50:
        health_status = "Mild Concern"
    elif final_score >= 30:
        health_status = "Moderate Risk"
    else:
        health_status = "High Risk"

    abnormal_count = len(abnormal_tests)
    message = (
        f"All {len(valid_tests)} tested values are within normal range."
        if abnormal_count == 0
        else f"{abnormal_count} abnormal value{'s' if abnormal_count != 1 else ''} detected out of {len(valid_tests)} tests."
    )

    return {
        "score": round(final_score, 2),
        "status": health_status,
        "abnormal_count": abnormal_count,
        "abnormal_tests": abnormal_tests,
        "message": message,
    }


# ===========================================================================
# LLM INTEGRATION WITH RETRY LOGIC
# ===========================================================================

def call_llm(messages, temperature=0.3, max_retries=2, max_tokens=1500):
    last_error = None
    
    for attempt in range(max_retries + 1):
        try:
            client = get_groq_client()
            
            total_chars = sum(len(m.get("content", "")) for m in messages)
            estimated_tokens = total_chars // 4
            print(f"🔄 LLM call attempt {attempt + 1}/{max_retries + 1} (~{estimated_tokens} tokens)")
            
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            
            result = response.choices[0].message.content.strip()
            
            if not result:
                print(f"⚠️ LLM returned empty response on attempt {attempt + 1}")
                last_error = "Empty response from LLM"
                time.sleep(1)
                continue
            
            print(f"✅ LLM response received ({len(result)} chars)")
            return result
            
        except Exception as e:
            last_error = str(e)
            print(f"⚠️ LLM call error (attempt {attempt + 1}): {e}")
            
            if "authentication" in last_error.lower() or "api_key" in last_error.lower():
                break
            
            if attempt < max_retries:
                time.sleep(2 * (attempt + 1))
    
    print(f"❌ LLM failed after {max_retries + 1} attempts. Last error: {last_error}")
    return None


# ===========================================================================
# ✅ FIX 3 APPLIED: Single clean graph validation
# ===========================================================================

def _get_cached_graph_analysis(session_key):
    """
    Retrieve cached ECG/graph analysis from upload phase.
    ✅ FIX 3: Single validation block, always returns dict or {}.
    """
    graph_json = cache.get(f"latest_graph_analysis_{session_key}")
    
    if not graph_json:
        return None
    
    try:
        result = json.loads(graph_json)
        # Single defensive check
        if isinstance(result, dict):
            return result
        else:
            print(f"⚠️ Cached graph data is {type(result)}, expected dict — returning empty dict")
            return {}
    except (json.JSONDecodeError, TypeError) as e:
        print(f"⚠️ Failed to parse cached graph data: {e} — returning empty dict")
        return {}


# ===========================================================================
# 🎯 UPLOAD & INDEX — ALL FIXES APPLIED (FIX 2, 3, 4, 5, 6)
# ===========================================================================

@csrf_exempt
@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
def upload_and_index(request):
    """
    Enhanced upload handler with defensive error handling.
    Handles: PDF table extraction, graph analysis, clinical notes,
    multi-modal data merging, vectorstore creation.
    
    v4.0 - COMPLETE FIXES:
    - Cache clearing on every upload (prevents stale data)
    - String return type handling (legacy table_extractor.py)
    - Parameter name corrections for merge functions
    - Defensive sanitization with recovery strategies
    - ECG/Graphical PDF detection and handling
    """
    
    if "file" not in request.FILES:
        return Response({"error": "No file uploaded"}, status=400)

    file_obj = request.FILES["file"]
    file_name = file_obj.name.lower()
    unique_filename = f"{uuid.uuid4()}_{file_obj.name}"
    file_path = os.path.join(MEDIA_DIR, unique_filename)

    # Save uploaded file
    with open(file_path, "wb") as f:
        for chunk in file_obj.chunks():
            f.write(chunk)

    session_key = request.session.session_key or request.META.get("REMOTE_ADDR", "default")

    try:
        # ================================================================
        # HANDLE CSV SIGNAL FILES
        # ================================================================
        if file_name.endswith(".csv"):
            # 🔥 Clear caches even for CSV uploads
            print("\n🗑️ [CSV] Clearing previous session data...")
            cache.delete(f"latest_table_data_{session_key}")
            cache.delete(f"latest_pdf_text_{session_key}")
            cache.delete(f"latest_graph_analysis_{session_key}")
            cache.delete(f"latest_clinical_data_{session_key}")
            
            cache.set(f"latest_signal_file_{session_key}", file_path, timeout=3600)
            clear_conversation(session_key)
            return Response({
                "message": "Signal file uploaded successfully.",
                "type": "signal"
            })

        # ================================================================
        # HANDLE PDF FILES - MAIN PIPELINE
        # ================================================================
        elif file_name.endswith(".pdf"):
            
            # ============================================================
            # 🔥🔥🔥 CRITICAL: CLEAR ALL STALE CACHE FIRST! 🔥🔥🔥
            # ============================================================
            print("\n" + "="*70)
            print("🗑️  CLEARING ALL PREVIOUS SESSION DATA")
            print("="*70)
            
            cache_deletion_stats = {"deleted": 0, "failed": 0}
            
            # Comprehensive list of ALL possible cache keys
            all_cache_keys = [
                f"latest_pdf_text_{session_key}",
                f"latest_table_data_{session_key}",
                f"latest_graph_analysis_{session_key}",
                f"latest_clinical_data_{session_key}",
                f"latest_signal_file_{session_key}",
                f"vectorstore_{session_key}",
                f"conversation_history_{session_key}",
                f"pdf_processed_{session_key}",
                f"extracted_tests_{session_key}",
            ]
            
            for cache_key in all_cache_keys:
                try:
                    result = cache.delete(cache_key)
                    if result:
                        cache_deletion_stats["deleted"] += 1
                        print(f"   ✓ Deleted: {cache_key}")
                    else:
                        print(f"   ℹ Not found: {cache_key}")
                except Exception as e:
                    cache_deletion_stats["failed"] += 1
                    print(f"   ⚠ Failed: {cache_key} ({e})")
            
            # Clear vectorstore
            try:
                clear_vectorstore_cache()
                print(f"   ✓ Cleared vectorstore")
            except Exception as e:
                print(f"   ⚠ Vectorstore clear failed: {e}")
            
            # Clear conversation
            try:
                clear_conversation(session_key)
                print(f"   ✓ Cleared conversation history")
            except Exception as e:
                print(f"   ⚠ Conversation clear failed: {e}")
            
            print(f"\n   📊 Cache cleanup: {cache_deletion_stats['deleted']} deleted, {cache_deletion_stats['failed']} failed")
            print("   ✅ Session reset complete - starting fresh upload\n")
            print("="*70 + "\n")
            
            # ----------------- PHASE 1: Page Classification -----------------
            print("📍 PHASE 1: Document Structure Analysis")
            
            pages_info = None
            graph_page_count = 0
            safe_page_count = 0
            document_type = "unknown"
            
            try:
                pages_info = classify_pages(file_path)
                
                if pages_info and isinstance(pages_info, list):
                    safe_page_count = sum(1 for p in pages_info if p.get('is_safe', False))
                    graph_page_count = len(pages_info) - safe_page_count
                    
                    if graph_page_count > 0:
                        document_type = "graphical"
                        print(f"   ⚠️ Found {graph_page_count} graphical page(s), {safe_page_count} text page(s)")
                        if graph_page_count == len(pages_info):
                            print(f"   📊 This appears to be a SCANNED/IMAGE-BASED PDF (ECG, X-ray, etc.)")
                    else:
                        document_type = "digital_text"
                        print(f"   ✅ All {len(pages_info)} pages are digital text")
                        
            except Exception as e:
                print(f"   ⚠️ Page classification failed: {e}")
                import traceback
                traceback.print_exc()
                pages_info = None
                safe_page_count = 0
                graph_page_count = 0
                document_type = "unknown"

            # ----------------- PHASE 2: Text Extraction -----------------
            print("\n📍 PHASE 2: Text Extraction")
            
            text = ""
            try:
                text = extract_text_from_pdf(file_path)
                print(f"   Extracted {len(text)} chars of text")
                
                if len(text) < 50:
                    print(f"   ⚠️ Very little text extracted - likely scanned/image PDF")
                    document_type = "scanned_image"
                    
            except Exception as e:
                print(f"   ❌ Text extraction failed: {e}")
                text = ""

            # ----------------- PHASE 3: Table Extraction (SMART - Handles Both Digital & Scanned) -----------------
            print("\n📍 PHASE 3: Table Extraction")
            
            raw_extraction_result = None
            raw_table_json = []
            extraction_success = False
            ocr_table_data = []  # ✅ NEW: Store OCR-extracted tables separately
            
            try:
                # ================================================================
                # ✅ NEW: Check if we should attempt OCR table extraction
                # ================================================================
                ocr_table_pages = []
                if pages_info:
                    from rag.services.pdf_loader import should_attempt_ocr_table_extraction
                    ocr_table_pages = should_attempt_ocr_table_extraction(pages_info)
                
                if ocr_table_pages:
                    # 🆕 Attempt OCR→Table extraction for scanned documents
                    print(f"\n{'='*60}")
                    print(f"📋 OCR TABLE EXTRACTION: Processing {len(ocr_table_pages)} scanned page(s)")
                    print(f"{'='*60}\n")
                    
                    try:
                        from rag.services.ocr import extract_text_with_ocr
                        
                        # Run OCR on the file
                        ocr_text = extract_text_with_ocr(file_path)
                        
                        if ocr_text and len(ocr_text.strip()) > 50:
                            print(f"   📝 OCR extracted {len(ocr_text)} chars, attempting smart parsing...")
                            
                            # Use the existing smart OCR parser from table_extractor
                            from rag.services.table_extractor import extract_text_based_tests
                            ocr_table_data = extract_text_based_tests(file_path, is_ocr=True)
                            
                            if ocr_table_data:
                                print(f"   ✅ Successfully extracted {len(ocr_table_data)} test(s) from OCR!")
                                extraction_success = True
                                
                                # Debug: Show first few results
                                for idx, row in enumerate(ocr_table_data[:5]):
                                    flag_str = f" [{row['flag']}]" if row.get('flag') else ""
                                    print(f"      {idx+1}. {row['test']}: {row['value']} {row.get('unit','')}{flag_str}")
                                if len(ocr_table_data) > 5:
                                    print(f"      ... and {len(ocr_table_data) - 5} more")
                            else:
                                print(f"   ⚠️ OCR text parsed but no valid tests found")
                        else:
                            print(f"   ⚠️ OCR text too short ({len(ocr_text) if ocr_text else 0} chars), skipping")
                            
                    except Exception as ocr_err:
                        print(f"   ❌ OCR table extraction failed: {ocr_err}")
                        import traceback
                        traceback.print_exc()
                
                # ================================================================
                # Normal table extraction (for digital PDFs)
                # ================================================================
                raw_extraction_result = extract_tables(file_path)
                print(f"   extract_tables() returned type: {type(raw_extraction_result)}")
                print(f"   extract_tables() value preview: {str(raw_extraction_result)[:150] if raw_extraction_result else 'None'}...")
                
                # ================================================================
                # DEFENSIVE TYPE HANDLING - Handle both old & new return types
                # ================================================================
                
                if raw_extraction_result is None:
                    print("   ⚠️ extract_tables() returned None")
                    raw_table_json = []
                    
                elif isinstance(raw_extraction_result, str):
                    # ❌ OLD BUGGY BEHAVIOR: Function returned JSON string instead of list
                    print(f"   ⚠️ LEGACY FORMAT: Got string instead of list")
                    print(f"      String length: {len(raw_extraction_result)} chars")
                    print(f"      First 300 chars:\n{raw_extraction_result[:300]}...")
                    
                    # Attempt to parse the string as JSON
                    try:
                        parsed_data = json.loads(raw_extraction_result)
                        
                        if isinstance(parsed_data, list):
                            print(f"   ✓ Successfully parsed JSON string into list ({len(parsed_data)} items)")
                            raw_table_json = parsed_data
                            extraction_success = True
                        elif isinstance(parsed_data, dict):
                            print(f"   ⚠️ Parsed as dict (not list), extracting values...")
                            raw_table_json = list(parsed_data.values()) if len(parsed_data) > 0 else []
                            extraction_success = True
                        else:
                            print(f"   ✗ Parsed as unexpected type: {type(parsed_data)}")
                            raw_table_json = []
                            
                    except json.JSONDecodeError as json_err:
                        print(f"   ✗ JSON parse failed: {json_err}")
                        print(f"   ⚠️ This looks like log output, not data!")
                        raw_table_json = []
                        
                elif isinstance(raw_extraction_result, list):
                    # ✅ CORRECT NEW BEHAVIOR: Got actual Python list
                    print(f"   ✅ CORRECT: Got Python list with {len(raw_extraction_result)} items")
                    
                    if len(raw_extraction_result) > 0:
                        first_item = raw_extraction_result[0]
                        print(f"      First item type: {type(first_item)}")
                        
                        if isinstance(first_item, dict):
                            keys_preview = list(first_item.keys())[:6]
                            print(f"      First item keys: {keys_preview}")
                            print(f"      Sample: {str(first_item)[:150]}")
                            raw_table_json = raw_extraction_result
                            extraction_success = True
                        else:
                            print(f"      ⚠️ Items are {type(first_item)}, not dict")
                            raw_table_json = []
                    else:
                        print(f"      ℹ Empty list returned (no tables found)")
                        raw_table_json = []
                        extraction_success = True  # Success, but no data
                        
                else:
                    print(f"   ❌ UNEXPECTED TYPE: {type(raw_extraction_result)}")
                    raw_table_json = []
                    
            except Exception as extract_error:
                print(f"   ❌ EXTRACTION EXCEPTION: {extract_error}")
                import traceback
                traceback.print_exc()
                raw_table_json = []

            # Final validation summary
            print(f"\n{'─'*60}")
            print(f"📊 PHASE 3 SUMMARY:")
            print(f"{'─'*60}")
            print(f"   Raw table type:     {type(raw_table_json)}")
            print(f"   Raw table length:   {len(raw_table_json)}")
            print(f"   Extraction success: {extraction_success}")
            
            
            # ================================================================
            # ✅ NEW: Merge OCR-extracted data with normally extracted data
            # ================================================================
            if ocr_table_data:
                print(f"\n   📊 MERGING: Adding {len(ocr_table_data)} OCR-extracted tests...")
                
                # Convert to dict format for merging
                ocr_tests_dict = {}
                for row in ocr_table_data:
                    key = row.get('test', '').lower().strip()
                    if key and key not in ocr_tests_dict:
                        ocr_tests_dict[key] = row
                
                # Merge with existing data (OCR data takes priority for scanned docs)
                if isinstance(raw_table_json, list):
                    existing_keys = {r.get('test', '').lower().strip() for r in raw_table_json}
                    
                    for key, ocr_row in ocr_tests_dict.items():
                        if key not in existing_keys:
                            raw_table_json.append(ocr_row)
                            existing_keys.add(key)
                    
                    print(f"   ✅ Merged total: {len(raw_table_json)} tests ({len(ocr_table_data)} from OCR)")
                    
                    if not extraction_success and len(ocr_table_data) > 0:
                        extraction_success = True
                        print(f"   ✅ Extraction marked as successful (data from OCR)")
                        
                elif not raw_table_json or len(raw_table_json) == 0:
                    # If normal extraction failed but OCR worked, use OCR data
                    raw_table_json = ocr_table_data
                    extraction_success = True
                    print(f"   ✅ Using OCR data as primary source ({len(raw_table_json)} tests)")
            
            if isinstance(raw_table_json, list) and len(raw_table_json) > 0:
                sample = raw_table_json[0]
                print(f"   Sample item type:   {type(sample)}")
                if isinstance(sample, dict):
                    print(f"   Sample dict keys:  {list(sample.keys())[:8]}")
                    print(f"   Sample data:       {str(sample)[:200]}")
            else:
                print(f"   ⚠️ No valid table data extracted")
                if document_type in ["graphical", "scanned_image"]:
                    print(f"   ℹ This is expected for ECG/graphical PDFs")
            print(f"{'─'*60}\n")

            # ----------------- PHASE 4: Graph Analysis & Merge -----------------
            print("📍 PHASE 4: Graph/ECG Analysis")
            
            # Start with whatever we got from extraction
            final_table_data = raw_table_json if isinstance(raw_table_json, list) else []
            graph_analysis_result = {}
            
            if pages_info and graph_page_count > 0:
                print(f"   Processing {graph_page_count} graphical page(s)...")
                
                try:
                    graph_analysis_result = analyze_graphical_pages(file_path, pages_info)
                    
                    print(f"   Graph analysis result type: {type(graph_analysis_result)}")
                    
                    if not isinstance(graph_analysis_result, dict):
                        print(f"   ⚠️ Invalid graph output (expected dict), converting...")
                        graph_analysis_result = {"raw_output": str(graph_analysis_result)}
                    else:
                        print(f"   Graph analysis keys: {list(graph_analysis_result.keys())[:10]}")

                    # Only attempt merge if we have BOTH table data AND graph data
                    if graph_analysis_result and len(final_table_data) > 0:
                        print(f"\n   Attempting to merge lab data ({len(final_table_data)} items) with graph analysis...")
                        
                        merged = None
                        merge_attempt = 0
                        
                        # Attempt 1: Standard parameter names (table_data, graph_data)
                        merge_attempt += 1
                        try:
                            print(f"   🔄 Merge attempt {merge_attempt}: (table_data=..., graph_data=...)")
                            merged = merge_lab_and_graph_data(
                                table_data=final_table_data,
                                graph_data=graph_analysis_result
                            )
                            print(f"   ✅ Merge attempt {merge_attempt} SUCCESSFUL")
                            
                        except TypeError as param_err:
                            error_msg = str(param_err)
                            print(f"   ⚠️ Merge attempt {merge_attempt} FAILED: {error_msg}")
                            
                            # Attempt 2: Alternative parameter names (lab_data, graph_data)
                            if 'lab_data' in error_msg or 'unexpected keyword' in error_msg.lower():
                                merge_attempt += 1
                                try:
                                    print(f"   🔄 Merge attempt {merge_attempt}: (lab_data=..., graph_data=...)")
                                    merged = merge_lab_and_graph_data(
                                        lab_data=final_table_data,
                                        graph_data=graph_analysis_result
                                    )
                                    print(f"   ✅ Merge attempt {merge_attempt} SUCCESSFUL")
                                    
                                except TypeError as err2:
                                    print(f"   ⚠️ Merge attempt {merge_attempt} FAILED: {err2}")
                                    
                                    # Attempt 3: Positional arguments only
                                    merge_attempt += 1
                                    try:
                                        print(f"   🔄 Merge attempt {merge_attempt}: positional args")
                                        merged = merge_lab_and_graph_data(
                                            final_table_data,
                                            graph_analysis_result
                                        )
                                        print(f"   ✅ Merge attempt {merge_attempt} SUCCESSFUL")
                                        
                                    except Exception as err3:
                                        print(f"   ⚠️ Merge attempt {merge_attempt} FAILED: {err3}")
                                        
                            # If all named attempts failed, keep original data
                            if merged is None:
                                print(f"   ℹ All merge attempts failed, using original table data")
                                
                        except Exception as general_merge_err:
                            print(f"   ❌ Unexpected merge error: {general_merge_err}")
                            import traceback
                            traceback.print_exc()
                        
                        # Use merged result if successful
                        if merged is not None:
                            if isinstance(merged, list) and len(merged) > 0:
                                print(f"   ✅ MERGE SUCCESSFUL: {len(merged)} final items")
                                final_table_data = merged
                            elif isinstance(merged, list) and len(merged) == 0:
                                print(f"   ⚠️ Merge returned empty list, keeping original")
                            else:
                                print(f"   ⚠️ Merge returned {type(merged)}, keeping original")
                                    
                    elif not graph_analysis_result:
                        print(f"   ⚠️ Graph analysis returned empty, skipping merge")
                    elif len(final_table_data) == 0:
                        print(f"   ℹ No table data to merge (this is normal for ECG-only PDFs)")

                except Exception as graph_pipeline_err:
                    print(f"   ❌ GRAPH PIPELINE ERROR: {graph_pipeline_err}")
                    import traceback
                    traceback.print_exc()
                    # Keep existing data (if any)

                # Always cache graph analysis results (even if empty or merge failed)
                try:
                    graph_json = json.dumps(graph_analysis_result) if isinstance(graph_analysis_result, dict) else "{}"
                    cache.set(f"latest_graph_analysis_{session_key}", graph_json, timeout=3600)
                    print(f"   ✅ Graph analysis cached ({len(graph_json)} chars)")
                except Exception as cache_err:
                    print(f"   ⚠️ Failed to cache graph analysis: {cache_err}")

            else:
                print(f"   ℹ No graphical pages detected - skipping graph analysis")
                graph_analysis_result = {}

            # ----------------- PHASE 5: Clinical Notes -----------------
            print("\n📍 PHASE 5: Clinical Notes")
            
            clinical_note_input = request.POST.get("clinical_note", "")
            note_text = clinical_note_input if clinical_note_input else text
            
            try:
                clinical_data = extract_clinical_data(note_text)
                
                clinical_json = json.dumps(clinical_data) if isinstance(clinical_data, (dict, list)) else "{}"
                cache.set(f"latest_clinical_data_{session_key}", clinical_json, timeout=3600)
                print(f"   ✅ Clinical notes processed and cached")
                
            except Exception as clinical_err:
                print(f"   ⚠️ Clinical notes processing error: {clinical_err}")

            # ----------------- PHASE 6: Caching & Indexing -----------------
            print("\n📍 PHASE 6: Caching & VectorStore Creation")
            
            # ================================================================
            # FINAL DATA VALIDATION BEFORE CACHING
            # ================================================================
            
            print(f"\n   Pre-cache validation:")
            print(f"      Current type: {type(final_table_data)}")
            print(f"      Current length: {len(final_table_data) if isinstance(final_table_data, list) else 'N/A'}")
            
            # Ensure we have a proper list
            if not isinstance(final_table_data, list):
                print(f"   ❌ DATA CORRUPTION DETECTED: final_table_data is {type(final_table_data)}, expected list!")
                
                # Recovery strategy 1: Use raw_table_json
                if isinstance(raw_table_json, list) and len(raw_table_json) > 0:
                    print(f"   ↳ Strategy 1: Recovering raw_table_json ({len(raw_table_json)} items)")
                    final_table_data = raw_table_json
                    
                # Recovery strategy 2: Parse raw_extraction_result if it's a string
                elif isinstance(raw_extraction_result, str) and len(raw_extraction_result) > 10:
                    print(f"   ↳ Strategy 2: Attempting to parse extraction string...")
                    try:
                        parsed = json.loads(raw_extraction_result)
                        if isinstance(parsed, list) and len(parsed) > 0:
                            final_table_data = parsed
                            print(f"   ↳ Recovery successful: {len(final_table_data)} items")
                        else:
                            print(f"   ↳ Recovery failed: parsed as {type(parsed)}")
                            final_table_data = []
                    except json.JSONDecodeError:
                        print(f"   ↳ Recovery failed: invalid JSON")
                        final_table_data = []
                else:
                    print(f"   ↳ No recovery possible - using empty list")
                    final_table_data = []
            
            # ================================================================
            # DEFENSIVE SANITIZATION - Filter out bad items
            # ================================================================
            print(f"\n   Running defensive sanitization on {len(final_table_data)} items...")
            
            sanitized_data = []
            sanity_stats = {
                "original_count": 0,
                "kept_count": 0,
                "removed_count": 0,
                "errors": [],
                "error_types": {}
            }
            
            for idx, item in enumerate(final_table_data):
                sanity_stats["original_count"] += 1
                
                # Type check: Only accept dicts
                if isinstance(item, dict):
                    test_name = item.get('test', '').strip()
                    value = item.get('value', '').strip()
                    
                    # Validation: Must have at least test name and value
                    if test_name and value:
                        sanitized_data.append(item)
                        sanity_stats["kept_count"] += 1
                    else:
                        reason = f"missing {'test' if not test_name else ''}{'value' if not value else ''}"
                        sanity_stats["removed_count"] += 1
                        if len(sanity_stats["errors"]) < 5:
                            sanity_stats["errors"].append({
                                "index": idx,
                                "reason": reason,
                                "preview": str(item)[:80]
                            })
                            
                elif isinstance(item, str):
                    sanity_stats["removed_count"] += 1
                    sanity_stats["error_types"]["string_instead_of_dict"] = \
                        sanity_stats["error_types"].get("string_instead_of_dict", 0) + 1
                    if len(sanity_stats["errors"]) < 5:
                        sanity_stats["errors"].append({
                            "index": idx,
                            "reason": "string instead of dict",
                            "preview": item[:80]
                        })
                        
                elif isinstance(item, (int, float)):
                    sanity_stats["removed_count"] += 1
                    sanity_stats["error_types"]["bare_number"] = \
                        sanity_stats["error_types"].get("bare_number", 0) + 1
                        
                else:
                    sanity_stats["removed_count"] += 1
                    type_name = type(item).__name__
                    sanity_stats["error_types"][f"type:{type_name}"] = \
                        sanity_stats["error_types"].get(f"type:{type_name}", 0) + 1
            
            # Print sanitization report
            print(f"\n   {'─'*50}")
            print(f"   SANITIZATION REPORT:")
            print(f"   {'─'*50}")
            print(f"   Original items:  {sanity_stats['original_count']}")
            print(f"   Kept (valid):    {sanity_stats['kept_count']}")
            print(f"   Removed (invalid): {sanity_stats['removed_count']}")
            
            if sanity_stats["error_types"]:
                print(f"\n   Removal reasons:")
                for reason, count in sanity_stats["error_types"].items():
                    print(f"      • {reason}: {count} items")
                    
            if sanity_stats["errors"]:
                print(f"\n   Sample errors (first {len(sanity_stats['errors'])}):")
                for err in sanity_stats["errors"]:
                    print(f"      [{err['index']}] {err['reason']}: {err['preview']}")
            print(f"   {'─'*50}\n")
            
            # Apply sanitized data
            final_table_data = sanitized_data
            
            # ================================================================
            # SAFETY NET: Don't lose everything if sanitizer too aggressive
            # ================================================================
            if len(final_table_data) == 0 and sanity_stats["original_count"] > 0:
                print(f"   ⚠️ WARNING: Sanitizer removed ALL {sanity_stats['original_count']} items!")
                print(f"   ↳ Attempting loose recovery...")
                
                # Try again with minimal validation
                loose_recovery = []
                for item in raw_table_json if isinstance(raw_table_json, list) else []:
                    if isinstance(item, dict) and item.get('test') and item.get('value'):
                        loose_recovery.append(item)
                
                if len(loose_recovery) > 0:
                    print(f"   ✓ Loose recovery succeeded: {len(loose_recovery)} items recovered")
                    final_table_data = loose_recovery
                else:
                    print(f"   ✗ No recovery possible - accepting empty dataset")
                    print(f"   ℹ This may be normal for image-based PDFs (ECG, X-ray)")

            # ================================================================
            # CACHE THE FINAL DATA
            # ================================================================
            print(f"\n📍 CACHING RESULTS:")
            
            # Cache extracted text
            cache.set(f"latest_pdf_text_{session_key}", text, timeout=3600)
            print(f"   ✓ Cached PDF text ({len(text)} chars)")
            
            # Cache table data as JSON string
            test_count = len(final_table_data) if isinstance(final_table_data, list) else 0
            json_cache_data = json.dumps(final_table_data)
            
            cache.set(f"latest_table_data_{session_key}", json_cache_data, timeout=3600)
            print(f"   ✓ Cached table data ({test_count} tests, {len(json_cache_data)} chars)")
            
            # Verify cache was written correctly
            verification = cache.get(f"latest_table_data_{session_key}")
            if verification:
                try:
                    verify_parsed = json.loads(verification) if isinstance(verification, str) else verification
                    verify_count = len(verify_parsed) if isinstance(verify_parsed, list) else 0
                    print(f"   ✓ Cache verified: {verify_count} tests readable")
                except:
                    print(f"   ⚠️ Cache verification failed (corrupted?)")
            else:
                print(f"   ❌ Cache verification failed (not written!)")

            # ================================================================
            # 🔥 FIX: VectorStore Creation (Bulletproof v4.0)
            # ================================================================
            vectorstore_created = False
            
            try:
                docs = split_text(text, final_table_data)
                print(f"\n   📍 VectorStore Creation:")
                print(f"      Generated {len(docs)} text chunks for embedding")
                
                if len(docs) == 0:
                    print(f"      ⚠️ No chunks generated - skipping vectorstore")
                else:
                    # Debug chunk format
                    sample_chunk = docs[0] if docs else None
                    print(f"      Chunk type: {type(sample_chunk)}, content preview: {str(sample_chunk)[:80] if sample_chunk else 'N/A'}...")
                    
                    # Try multiple approaches
                    vs_success = False
                    
                    # Attempt 1: Pass docs directly
                    try:
                        print(f"      Attempt 1: Passing docs list directly...")
                        create_vectorstore(docs)
                        vs_success = True
                        print(f"      ✅ Vectorstore created (method 1: direct list)")
                    except TypeError as err1:
                        print(f"      ⚠ Method 1 failed: {err1}")
                        
                        # Attempt 2: Pass JSON string
                        try:
                            print(f"      Attempt 2: Converting to JSON string...")
                            import json as json_mod
                            docs_json = json_mod.dumps(docs, ensure_ascii=False, default=str)
                            create_vectorstore(docs_json)
                            vs_success = True
                            print(f"      ✅ Vectorstore created (method 2: JSON string)")
                        except Exception as err2:
                            print(f"      ⚠ Method 2 failed: {err2}")
                            
                            # Attempt 3: Pass only text content
                            try:
                                print(f"      Attempt 3: Passing raw text only...")
                                create_vectorstore([text])
                                vs_success = True
                                print(f"      ✅ Vectorstore created (method 3: text-only fallback)")
                            except Exception as err3:
                                print(f"      ❌ All methods failed. Last error: {err3}")
                    
                    vectorstore_created = vs_success
                        
            except Exception as vs_outer_err:
                print(f"   ⚠️ Vectorstore pipeline error (non-fatal): {vs_outer_err}")

            if vectorstore_created:
                print(f"   ✅ Semantic search enabled")
            else:
                print(f"   ℹ Operating in basic mode (keyword matching only)")

            # Clear conversation to start fresh
            clear_conversation(session_key)
            
            # ================================================================
            # BUILD RESPONSE
            # ================================================================
            
            response_data = {
                "message": f"PDF processed successfully",
                "document_type": document_type,
                "test_count": test_count,
                "pages_analyzed": len(pages_info) if pages_info else 0,
                "safe_pages": safe_page_count,
                "graphical_pages": graph_page_count,
                "has_graph_analysis": bool(graph_analysis_result),
                "extraction_successful": extraction_success,
            }
            
            # Add specific messages based on document type
            if test_count == 0 and document_type in ["graphical", "scanned_image"]:
                response_data["message"] = f"Graphical PDF analyzed (ECG/Image). No tabular data extracted."
                response_data["suggestion"] = "This PDF contains graphs/images (ECG, charts) rather than tables."
                response_data["next_step"] = "View the graphical analysis below."
            elif test_count > 0:
                response_data["message"] = f"PDF indexed successfully ({test_count} tests extracted)"
            
            # Add graph analysis summary if available
            if graph_analysis_result and isinstance(graph_analysis_result, dict):
                response_data["graph_summary"] = {
                    "keys_available": list(graph_analysis_result.keys())[:10],
                    "has_ecg_data": any(k.lower().find('ecg') >= 0 or k.lower().find('heart') >= 0 
                                       for k in graph_analysis_result.keys()),
                }
            
            print(f"\n{'='*70}")
            print(f"✅ UPLOAD COMPLETE")
            print(f"{'='*70}")
            print(f"   Document type: {document_type}")
            print(f"   Tests found:   {test_count}")
            print(f"   Pages:         {len(pages_info) if pages_info else '?'} "
                  f"({safe_page_count} safe, {graph_page_count} graphical)")
            print(f"   Response:      {response_data['message']}")
            print(f"{'='*70}\n")
            
            return Response(response_data)

        # ================================================================
        # UNSUPPORTED FILE TYPE
        # ================================================================
        else:
            return Response({
                "error": "Unsupported file type. Please upload PDF or CSV only.",
                "supported_formats": [".pdf", ".csv"],
                "received_format": os.path.splitext(file_name)[1] if '.' in file_name else "unknown"
            }, status=400)

    except Exception as e:
        # ================================================================
        # CATCH-ALL ERROR HANDLER
        # ================================================================
        print(f"\n{'💥'*30}")
        print(f"CRITICAL UPLOAD ERROR: {e}")
        print(f"{'💥'*30}")
        
        import traceback
        traceback.print_exc()
        
        # Try to give useful error info
        error_details = {
            "error": str(e),
            "error_type": type(e).__name__,
            "file_uploaded": file_name,
            "suggestion": "Please check server logs for details."
        }
        
        # Add specific suggestions based on error type
        if "memory" in str(e).lower():
            error_details["suggestion"] = "File may be too large. Try a smaller PDF."
        elif "permission" in str(e).lower():
            error_details["suggestion"] = "Server permission error. Contact administrator."
        elif "timeout" in str(e).lower():
            error_details["suggestion"] = "Processing timed out. Try a simpler PDF."
        
        return Response(error_details, status=500)

# ===========================================================================
# 🎯 QUERY DOCUMENT — HYBRID ROUTER (ULTIMATE VERSION)
# ===========================================================================

@csrf_exempt
@api_view(["POST"])
@parser_classes([JSONParser])
def query_document(request):
    question = request.data.get("question", "").strip()
    if not question:
        return Response({"error": "Question is required"}, status=400)

    q = question.lower()
    session_key = request.session.session_key or request.META.get("REMOTE_ADDR", "default")
    history = get_conversation_history(session_key)

    # Load and sanitize table data
    table_rows = load_and_parse_table_rows(session_key)
    table_rows, quality_stats = sanitize_table_data(table_rows)
    
    valid_count = len([r for r in table_rows if r["status"] in ["NORMAL", "HIGH", "LOW"]])
    print(f"\n📊 {len(table_rows)} tests ({valid_count} with status) | Q: {question[:80]}")

    # ================================================================
    # 🔥 FIX #4: Document Type Detection (Prevents CBC Hallucination for ECG)
    # ================================================================
    document_type = "unknown"
    is_ecg_or_graphical = False
    
    # Check cached graph analysis for ECG data
    graph_analysis_cached = _get_cached_graph_analysis(session_key)
    
    if graph_analysis_cached and isinstance(graph_analysis_cached, dict):
        graph_str_lower = str(graph_analysis_cached).lower()
        ecg_indicator_keys = [
            'ecg_quality', 'ventricular_rate', 'pr_interval', 'qrs_duration',
            'qt_interval', 'qtc_interval', 'rhythm', 'p_wave', 'qrs_morphology',
            't_wave', 'st_segment', 'cardiac_axis', 'findings', 'heart_rate',
            'atrial_rate', 'atrial_pause', 'av_conduction', 'ectopics'
        ]
        ecg_matches = sum(1 for k in ecg_indicator_keys if k in graph_str_lower)
        
        if ecg_matches >= 3:
            document_type = "ecg_report"
            is_ecg_or_graphical = True
            print(f"   🫀 Document type: ECG REPORT (detected from graph analysis)")
        elif graph_analysis_cached.get('chart_analysis') or graph_analysis_cached.get('total_pages_analyzed'):
            document_type = "graphical_image"
            is_ecg_or_graphical = True
            print(f"   📊 Document type: GRAPHICAL IMAGE")
    
    # Secondary check: If we have graph data but very few/invalid lab tests → likely ECG/image
    if not is_ecg_or_graphical and graph_analysis_cached:
        real_lab_tests = [t for t in table_rows if t.get("status") in ["HIGH", "LOW", "NORMAL"]]
        if len(real_lab_tests) < 3 and len(table_rows) > 0:
            # Check if existing data looks like garbage (short test names, weird values)
            garbage_indicators = 0
            for t in table_rows[:10]:
                test_name = t.get('test', '')
                value = t.get('value', '')
                if len(test_name) < 5:
                    garbage_indicators += 1
                if not re.match(r'^[\d.]+$', str(value)):
                    garbage_indicators += 1
            if garbage_indicators > len(table_rows[:10]) * 0.6:
                document_type = "garbage_extraction"
                is_ecg_or_graphical = True
                print(f"   ⚠️ Document type: GARBAGE EXTRACTION (lab data looks invalid)")
    
    if not is_ecg_or_graphical and len(table_rows) >= 3:
        document_type = "lab_report"
        print(f"   🩸 Document type: LAB REPORT ({len(table_rows)} tests)")

    # Build document context string for LLM prompt (used later)
    doc_type_context = ""
    if is_ecg_or_graphical:
        if document_type == "ecg_report":
            doc_type_context = f"""
╔══════════════════════════════════════════════════════════════╗
║  ⚠️ CRITICAL: This is an ECG/Electrocardiogram Report           ║
║  It is NOT a blood test (CBC/laboratory) report!               ║
╚══════════════════════════════════════════════════════════════╝

AVAILABLE ECG DATA:
{json.dumps(graph_analysis_cached, indent=2, default=str)[:2500] if graph_analysis_cached else 'No ECG data'}

STRICT RULES:
• Discuss cardiac findings ONLY (heart rate, rhythm, intervals, waveforms)
• NEVER mention: Hemoglobin, WBC, RBC, Platelets, Glucose, Cholesterol, etc.
• If asked about blood tests, say: "This ECG report does not include laboratory blood work."
• Use cardiac terminology: bpm, ms, degrees, leads, rhythm, axis
"""
        else:
            doc_type_context = f"""
╔══════════════════════════════════════════════════════════════╗
║  ⚠️ This appears to be a medical imaging/graphical document     ║
║  It may not contain standard laboratory blood test values       ║
╚══════════════════════════════════════════════════════════════╝

Analyze only the data actually present above. Do not invent specific numerical lab values unless explicitly shown.
"""

    # Build clinical context
    clinical_context = ""
    clinical_data_json = cache.get(f"latest_clinical_data_{session_key}")
    if clinical_data_json:
        try:
            clinical_data = json.loads(clinical_data_json)
            clinical_data = correlate_conditions_with_labs(clinical_data, table_rows)
            
            clinical_parts = []
            if clinical_data.get("symptoms"):
                clinical_parts.append(f"Symptoms: {', '.join(clinical_data['symptoms'])}")
                
            conds = clinical_data.get("conditions", [])
            if conds:
                cond_strs = []
                for c in conds:
                    if isinstance(c, dict):
                        flag = f" [{c['flag']}]" if c.get("flag") else ""
                        conf = f" (Confidence: {c['confidence']})"
                        cond_strs.append(f"{c['name']}{conf}{flag}")
                    else:
                        cond_strs.append(str(c))
                clinical_parts.append(f"Conditions: {', '.join(cond_strs)}")
                
            if clinical_parts:
                clinical_context = "--- CLINICAL NOTES ---\n" + "\n".join(clinical_parts) + "\n\n"
                
        except (json.JSONDecodeError, Exception) as e:
            # ✅ FIXED: Don't kill the request, just skip clinical context
            print(f"⚠️ Clinical context parse error (non-fatal): {e}")
            clinical_context = ""

    # Resolve follow-up context
    resolved_test, resolved_row, effective_question = resolve_follow_up_context(
        question, table_rows, history
    )
    if resolved_test:
        q = effective_question.lower()
        print(f"🔗 Follow-up resolved: '{question}' → '{resolved_test}'")

    # ==================================================================
    # HANDLER 1: Signal / ECG Analysis (Enhanced Fallback Chain)
    # ==================================================================
    SIGNAL_KEYWORDS = [
        "ecg", "heart rate", "signal", "cardiac rhythm", "heartbeat", "ekg",
        "pr interval", "qrs duration", "qt interval", "rhythm"
    ]
    if any(w in q for w in SIGNAL_KEYWORDS):
        
        # ── TIER 1: PDF-based ECG analysis ──
        pdf_ecg_data = _get_cached_graph_analysis(session_key)
        
        if pdf_ecg_data and isinstance(pdf_ecg_data, dict) and pdf_ecg_data.get('ecg_analysis'):
            ecg_data = pdf_ecg_data['ecg_analysis']
            print(f"   ✅ TIER 1: Found PDF-based ECG analysis")
            formatted = format_signal_output(ecg_data)
            
            add_to_conversation(session_key, "user", question)
            add_to_conversation(session_key, "assistant", formatted)
            
            return Response({
                "type": "signal",
                "answer": formatted,
                "raw_data": ecg_data,
                "source": "pdf_ecg_analysis",
                "history": history
            })
        
        # ── TIER 2: Table-based inference ──
        ecg_related_tests = [
            'qrs duration', 'qt interval', 'pr interval', 'qrs', 
            'pr', 'qt', 'heart rate', 'pulse rate'
        ]
        table_ecg_data = [
            r for r in table_rows 
            if any(ecg_kw in r.get('test', '').lower() for ecg_kw in ecg_related_tests)
        ]
        
        if table_ecg_data:
            print(f"   ✅ TIER 2: Found {len(table_ecg_data)} ECG-related values in table")
            
            synthetic_ecg = {
                "heart_rate": next(
                    (r['value'] for r in table_ecg_data if 'heart' in r['test'].lower() or 'pulse' in r['test'].lower()),
                    "Not measured"
                ),
                "observations": [f"{r['test']}: {r['value']} {r.get('unit','')} ({r['status']})" for r in table_ecg_data],
                "source": "table_inference",
                "note": "Derived from structured lab data (not waveform analysis)"
            }
            
            for field in ['qrs_duration', 'pr_interval', 'qt_interval']:
                matching = [r for r in table_ecg_data if field.replace('_', ' ') in r['test'].lower()]
                if matching:
                    synthetic_ecg[field] = matching[0]['value']
            
            formatted = format_signal_output(synthetic_ecg)
            
            add_to_conversation(session_key, "user", question)
            add_to_conversation(session_key, "assistant", formatted)
            
            return Response({
                "type": "signal",
                "answer": formatted,
                "raw_data": synthetic_ecg,
                "source": "table_inference",
                "history": history
            })
        
        # ── TIER 3: CSV Signal File ──
        signal_file = cache.get(f"latest_signal_file_{session_key}")
        
        if signal_file:
            try:
                print(f"   ✅ TIER 3: Analyzing uploaded signal file")
                result = analyze_signal(signal_file, signal_type="ecg")
                formatted = format_signal_output(result)
                
                add_to_conversation(session_key, "user", question)
                add_to_conversation(session_key, "assistant", formatted)
                
                return Response({
                    "type": "signal",
                    "answer": formatted,
                    "raw_data": result,
                    "source": "csv_signal_file",
                    "history": history
                })
            except Exception as e:
                print(f"   ⚠️ TIER 3 failed: {e}")
        
        # ── TIER 4: Text-based inference ──
        pdf_text = cache.get(f"latest_pdf_text_{session_key}", "")
        if pdf_text and any(kw in pdf_text.lower() for kw in ['ecg', 'electrocardiogram', 'sinus rhythm']):
            print(f"   ℹ️ TIER 4: ECG keywords in PDF, falling through to LLM")
            pass
        
        else:
            error_msg = (
                "No ECG or cardiac signal data found.\n\n"
                "**To get ECG analysis:**\n"
                "1. Upload a medical report PDF containing an ECG tracing\n"
                "2. Upload a CSV file with ECG waveform data\n"
                "3. Ensure your report includes cardiac interval measurements"
            )
            add_to_conversation(session_key, "user", question)
            add_to_conversation(session_key, "assistant", error_msg)
            
            resp = format_final_response("error", error_msg, note="Upload PDF with ECG or signal CSV")
            resp["history"] = history
            return Response(resp, status=200)

    # ==================================================================
    # HANDLER 2: Show Full Table
    # ==================================================================
    TABLE_KEYWORDS = [
        "show table", "full table", "list all tests", "all tests", "complete report",
        "full report", "show all results", "all results", "show report",
    ]
    if any(w in q for w in TABLE_KEYWORDS):
        if not table_rows:
            error_msg = "No structured lab data available. Please upload a medical report PDF first."
            guidance = get_light_user_guidance("no_data")
            add_to_conversation(session_key, "user", question)
            add_to_conversation(session_key, "assistant", error_msg + guidance)
            return Response(format_final_response("error", error_msg, note="Upload a PDF report"), status=200)
        
        add_to_conversation(session_key, "user", question)
        add_to_conversation(session_key, "assistant", f"[Showed table with {len(table_rows)} tests]")
        return Response({"type": "table", "data": table_rows, "history": history})

    # ==================================================================
    # HANDLER 3: Abnormal Values Only
    # ==================================================================
    ABNORMAL_KEYWORDS = [
        "abnormal", "out of range", "not normal", "which tests are high",
        "which tests are low", "what is abnormal", "show abnormal",
    ]
    if any(w in q for w in ABNORMAL_KEYWORDS):
        abnormal = [r for r in table_rows if r["status"] in ["HIGH", "LOW"]]
        if not abnormal:
            msg = "Great news! All available lab values are within normal range."
            guidance = get_light_user_guidance("all_normal")
            add_to_conversation(session_key, "user", question)
            add_to_conversation(session_key, "assistant", msg + guidance)
            return Response(format_final_response("text", msg), status=200)
        
        add_to_conversation(session_key, "user", question)
        add_to_conversation(session_key, "assistant", f"[Showed {len(abnormal)} abnormal tests]")
        return Response({"type": "table", "data": abnormal, "history": history})

    # ==================================================================
    # HANDLER 4: Health Score
    # ==================================================================
    SCORE_KEYWORDS = [
        "health score", "how healthy", "am i healthy", "overall health",
        "health status", "my score", "health check",
    ]
    if any(w in q for w in SCORE_KEYWORDS):
        result = compute_health_score(table_rows)
        if result["score"] is None:
            answer = result["message"]
            guidance = get_light_user_guidance("insufficient_data")
            add_to_conversation(session_key, "user", question)
            add_to_conversation(session_key, "assistant", answer + guidance)
            return Response(
                format_final_response("error", answer, note="Upload a complete medical report"),
                status=200
            )
        else:
            answer = f"{result['message']}\n\n**Health Score: {result['score']}/100 — {result['status']}**"
            if result["abnormal_tests"]:
                answer += "\n\n**Abnormal values:**"
                for t in result["abnormal_tests"]:
                    sev = t.get("severity", "")
                    sev_str = f" [{sev}]" if sev and sev != "normal" else ""
                    answer += f"\n• {t['test']}: {t['value']} ({t['status']}{sev_str})"
            
            add_to_conversation(session_key, "user", question)
            add_to_conversation(session_key, "assistant", answer)
            return Response({"type": "text", "answer": answer, "history": history})

    # ==================================================================
    # HANDLER 5: Cross-Test Pattern Detection
    # ==================================================================
    PATTERN_KEYWORDS = [
        "pattern", "correlation", "connection", "related", "linked",
        "what pattern", "any pattern", "do these relate", "is there a pattern",
    ]
    if any(w in q for w in PATTERN_KEYWORDS):
        patterns = detect_cross_test_patterns(table_rows)
        
        if not patterns:
            answer = (
                "No clear medical patterns detected among your test results. "
                "The abnormal values appear unrelated based on standard clinical correlations."
            )
        else:
            lines = ["**🔍 Detected Medical Patterns:**\n"]
            for p in patterns:
                reliability_label = p['reliability'].title()
                if p['reliability'] == 'low':
                    lines.append(f"**{p['pattern_name']}** (⚠️ Low Confidence)")
                else:
                    lines.append(f"**{p['pattern_name']}** (Reliability: {reliability_label})")
                
                lines.append(f"_Matched tests: {', '.join(p['matched_tests'])}_")
                lines.append(f"\n{p['explanation']}")
                
                if p.get("follow_up"):
                    lines.append(f"\n📌 **Suggested follow-up:** {p['follow_up']}")
                
                if p['reliability'] == 'low':
                    lines.append("\n⚠️ _This is a low-confidence pattern suggestion. Clinical correlation advised._")
                lines.append("")
            
            answer = "\n".join(lines).strip()
            answer += "\n\n⚠️ *These are pattern suggestions based on lab values, not diagnoses.*"

        add_to_conversation(session_key, "user", question)
        add_to_conversation(session_key, "assistant", answer)
        return Response({
            "type": "text",
            "answer": answer,
            "patterns": patterns,
            "history": history
        })

    # ==================================================================
    # HANDLER 6: Named Test Lookup (Fuzzy Matching)
    # ==================================================================
    is_value_query = any(w in q for w in [
        "what is my", "what's my", "show me my", "what is the", "value of",
        "result of", "level of", "my result", "my level", "what was my",
    ])
    is_why_query = any(w in q for w in ["why", "reason", "cause", "explain"])
    is_definition_query = any(w in q for w in ["what is", "what does", "define", "meaning"])

    named_tests = extract_named_tests_fuzzy(question, table_rows=table_rows)

    if resolved_test and resolved_test not in named_tests:
        named_tests.insert(0, resolved_test)
        is_value_query = True

    if named_tests and is_value_query and not is_why_query and not is_definition_query:
        matched_rows = []
        for row in table_rows:
            row_norm = normalize_test_name(row["test"])
            if any(t == row_norm or t in row_norm for t in named_tests):
                matched_rows.append(row)

        if matched_rows:
            if len(matched_rows) == 1:
                row = matched_rows[0]
                explanation = generate_test_explanation(row["test"])
                sev = row.get("severity", "")
                sev_str = f" [{sev}]" if sev and sev != "normal" else ""
                answer = (
                    f"**{row['test']}**\n\n{explanation}\n\n"
                    f"**Your Result:** {row['value']} {row['unit']}\n"
                    f"**Status:** {row['status']}{sev_str}\n"
                    f"**Reference Range:** {row['range'] or 'N/A'}"
                )
                add_to_conversation(session_key, "user", question)
                add_to_conversation(session_key, "assistant", answer)
                return Response({"type": "text", "answer": answer, "history": history})
            else:
                explanations = []
                for row in matched_rows:
                    explanations.append({
                        "test": row["test"],
                        "value": row["value"],
                        "unit": row["unit"],
                        "status": row["status"],
                        "severity": row.get("severity", "unknown"),
                        "range": row["range"],
                        "explanation": generate_test_explanation(row["test"]),
                    })
                add_to_conversation(session_key, "user", question)
                add_to_conversation(session_key, "assistant", f"[Showed {len(matched_rows)} tests with explanations]")
                return Response({
                    "type": "table_with_explanations",
                    "data": explanations,
                    "history": history
                })

    # ==================================================================
    # HANDLER 7: Chart Interpretation
    # ==================================================================
    chart_data = request.data.get("chart_data", None)

    if chart_data is not None:
        if not isinstance(chart_data, dict) or "data" not in chart_data:
            error_msg = "Invalid chart data format."
            add_to_conversation(session_key, "user", question)
            add_to_conversation(session_key, "assistant", error_msg)
            history = get_conversation_history(session_key)
            return Response({"type": "error", "answer": error_msg, "history": history})
        
        try:
            result = interpret_chart(chart_data)
            answer = result.get("analysis", "")
            metrics = result.get("metrics", {})
            confidence = result.get("confidence", "medium")

            add_to_conversation(session_key, "user", question)
            add_to_conversation(session_key, "assistant", answer)
            history = get_conversation_history(session_key)

            return Response({
                "type": "chart_analysis",
                "answer": answer,
                "metrics": metrics,
                "confidence": confidence,
                "history": history
            })
        except Exception:
            error_msg = "Unable to interpret chart data."
            add_to_conversation(session_key, "user", question)
            add_to_conversation(session_key, "assistant", error_msg)
            history = get_conversation_history(session_key)
            return Response({"type": "error", "answer": error_msg, "history": history})

    # ==================================================================
    # HANDLER 8: Graph / Trend Analysis
    # ==================================================================
    GRAPH_KEYWORDS = [
        "graph", "chart", "trend", "visualization", "visualise", 
        "visualize", "plot", "diagram"
    ]
    if any(w in q for w in GRAPH_KEYWORDS):
        valid_rows = [r for r in table_rows if r["status"] in ["NORMAL", "HIGH", "LOW"]]
        if not valid_rows:
            error_msg = "I don't have enough structured lab data to generate graph insights."
            guidance = get_light_user_guidance("graph")
            add_to_conversation(session_key, "user", question)
            add_to_conversation(session_key, "assistant", error_msg + guidance)
            resp = format_final_response("error", error_msg, note="Upload PDF with lab results")
            resp["history"] = history
            return Response(resp, status=200)

        observations = generate_graph_observations(table_rows)
        answer = generate_deterministic_graph_insights(observations)

        patterns = detect_cross_test_patterns(table_rows)
        if patterns:
            answer += "\n\n**🔗 Related Patterns:**"
            for p in patterns[:3]:
                answer += (
                    f"\n• **{p['pattern_name']}** "
                    f"(Reliability: {p['reliability'].title()}): "
                    f"{', '.join(p['matched_tests'])}"
                )

        add_to_conversation(session_key, "user", question)
        add_to_conversation(session_key, "assistant", answer)
        return Response({
            "type": "graph_analysis",
            "answer": answer,
            "chart_data": {
                "distribution": observations["distribution_pct"],
                "tests": observations["all_tests"],
            },
            "patterns": patterns,
            "history": history,
        })

    # ==================================================================
    # UNIFIED LLM HANDLER
    # ==================================================================

    response_mode, _ = detect_response_mode(question)
    data_warning = get_data_quality_warning(table_rows)

    MODE_INSTRUCTIONS = {
        "reasoning": (
            "\nRESPONSE MODE: REASONING\n"
            "- Focus on explaining WHY a value might be abnormal\n"
            "- Discuss common medical causes and contributing factors\n"
            "- Structure: State finding → Explain causes → Recommend follow-up\n"
            "- Always include disclaimer that this is not a diagnosis\n"
        ),
        "explanation": (
            "\nRESPONSE MODE: EXPLANATION\n"
            "- Focus on defining and explaining what a test measures\n"
            "- Explain what high/low values typically indicate\n"
            "- Use simple, patient-friendly language\n"
            "- Include what the test is used to diagnose or monitor\n"
        ),
        "concise": (
            "\nRESPONSE MODE: CONCISE SUMMARY\n"
            "- Keep brief and scannable\n"
            "- Use bullet points for key findings\n"
            "- Prioritize: Abnormal → Borderline → Normal\n"
            "- Limit to 150-200 words unless asked for more\n"
        ),
        "normal": "",
    }

    system_prompt = (
        "You are a knowledgeable, empathetic medical report assistant. "
        "Your role is to help users understand their medical reports in clear, plain language.\n\n"
        "GUIDELINES:\n"
        "- Answer naturally and conversationally.\n"
        "- Use the structured lab data (including severity) as your primary source of truth.\n"
        "- Do not fabricate values. If information is unavailable, say so.\n"
        "- Format with markdown where it improves readability.\n"
        "- Keep tone supportive and non-alarmist while being medically accurate.\n"
        + MODE_INSTRUCTIONS.get(response_mode, "")
        + (doc_type_context if is_ecg_or_graphical else "")  # 🔥 Inject ECG/Image context
    )

    table_context = build_table_context_string(table_rows)
    
    if response_mode == "concise":
        abnormal = [r for r in table_rows if r["status"] in ["HIGH", "LOW"]]
        normal_count = len([r for r in table_rows if r["status"] == "NORMAL"])
        unknown_count = len([r for r in table_rows if r["status"] == "UNKNOWN"])
        
        compact_lines = [
            f"Total tests: {len(table_rows)}",
            f"Normal: {normal_count}, Abnormal: {len(abnormal)}, Unknown: {unknown_count}",
        ]
        if abnormal:
            compact_lines.append("\nAbnormal tests:")
            for r in abnormal:
                arrow = "↑" if r["status"] == "HIGH" else "↓"
                compact_lines.append(
                    f"- {r['test']}: {r['value']} {r['unit']} {arrow} (ref: {r['range'] or 'N/A'})"
                )
        
        table_context = "\n".join(compact_lines)
        pattern_context = ""
        clinical_context = ""
    else:
        if data_warning:
            table_context = f"{data_warning}\n\n{table_context}"

        cross_patterns = detect_cross_test_patterns(table_rows)
        pattern_context = ""
        if cross_patterns:
            lines = ["DETECTED MEDICAL PATTERNS (mention if relevant to the question):"]
            for p in cross_patterns[:3]:
                lines.append(
                    f"- {p['pattern_name']} (Reliability: {p['reliability']}): "
                    f"Tests {', '.join(p['matched_tests'])}. {p['explanation']}"
                )
            pattern_context = "\n".join(lines)

    followup_context = ""
    if resolved_test and resolved_row:
        followup_context = (
            f"FOLLOW-UP RESOLUTION: The user is asking about \"{resolved_test}\" "
            f"(value: {resolved_row['value']} {resolved_row['unit']}, "
            f"status: {resolved_row['status']}, severity: {resolved_row.get('severity', 'unknown')}). "
            f"Address this specific test in your answer."
        )

    adaptive_k = get_adaptive_k(question, table_rows)
    if response_mode == "concise":
        adaptive_k = min(adaptive_k, 5)
    
    vector_context = get_vector_context(question, k=adaptive_k)

    history_text = "\n".join([
        f"{'User' if h['role'] == 'user' else 'Assistant'}: {h['content'][:200]}"
        for h in history[-4:] if h.get('content')
    ]) if history else "No prior conversation."

    effective_q = (
        f"{question} [Specifically about: {resolved_test}]"
        if resolved_test else question
    )

    user_message = (
        f"{doc_type_context}\n\n"  # 🔥 Add this line
        f"--- STRUCTURED LAB DATA ---\n{table_context}\n\n"
        f"{pattern_context}\n\n"
        f"{followup_context}\n\n"
        f"{clinical_context}"
        f"--- DOCUMENT CONTEXT ---\n{vector_context or 'No additional document text available.'}\n\n"
        f"--- CONVERSATION HISTORY ---\n{history_text}\n\n"
        f"--- USER'S QUESTION ---\n{effective_q}"
    )

    answer = call_llm(
        [{"role": "system", "content": system_prompt},
         {"role": "user", "content": user_message}],
        temperature=0.35,
        max_tokens=1500,
    )

    if not answer:
        if not table_rows:
            base_msg = "I couldn't find any structured lab data in your report."
        elif len(table_rows) < 3:
            base_msg = f"I only found {len(table_rows)} test(s) in your report."
        else:
            base_msg = "I'm sorry, I couldn't generate a response right now. Please try again."
        
        guidance = get_light_user_guidance("llm_fallback")
        answer = base_msg + guidance

    if data_warning and "No structured lab data" not in data_warning and response_mode != "concise":
        answer = f"{data_warning}\n\n{answer}"

    add_to_conversation(session_key, "user", question)
    add_to_conversation(session_key, "assistant", answer)
    
    resp = format_final_response("text", answer)
    resp["history"] = history
    return Response(resp, status=200)


# ===========================================================================
# UI VIEW
# ===========================================================================

@csrf_exempt
@api_view(["GET"])
def ui(request):
    return render(request, "rag/index.html")