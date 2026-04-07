import os
import uuid
import re
import json
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework import status
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
# REFERENCE DATA
# ===========================================================================

FALLBACK_RANGES = {
    "hemoglobin": "13.5-17.5", "hb": "13.5-17.5", "haemoglobin": "13.5-17.5",
    "packed cell volume": "40-50", "pcv": "40-50", "hematocrit": "40-50",
    "rbc count": "4.5-5.5", "rbc": "4.5-5.5", "red blood cell": "4.5-5.5",
    "mcv": "80-100", "mch": "27-32", "mchc": "31.5-34.5",
    "wbc": "4.5-11.0", "tlc": "4.5-11.0", "white blood cell": "4.5-11.0",
    "leukocyte": "4.5-11.0", "platelet": "150-400", "platelet count": "150-400",
    "rdw": "11-15", "creatinine": "0.70-1.30", "gfr": ">59",
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
# CROSS-TEST MEDICAL PATTERNS
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
            "most commonly caused by iron deficiency. Low ferritin confirms depleted iron stores. "
            "Elevated RDW indicates variation in red cell size, typical in iron deficiency."
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
            "Common causes include Vitamin B12 deficiency, folate deficiency, liver disease, or hypothyroidism. "
            "Low B12 or folate would confirm nutritional deficiency as the cause."
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
        "explanation": (
            "Elevated creatinine indicates reduced kidney function. Rising urea (BUN) and potassium "
            "are common accompaniments. Low GFR confirms decreased filtration. High phosphate and "
            "low calcium suggest secondary hyperparathyroidism from chronic kidney disease."
        ),
        "follow_up": "Consider complete renal panel, urine analysis, renal ultrasound, and nephrology referral if persistent."
    },
    {
        "id": "liver_dysfunction",
        "name": "Liver Dysfunction Pattern",
        "required_high": ["alt", "ast"],
        "optional_high": ["alp", "ggtp", "bilirubin"],
        "optional_low": ["albumin"],
        "min_optional_match": 1,
        "confidence_threshold": 0.5,
        "explanation": (
            "Elevated ALT and AST indicate hepatocellular injury (liver cell damage). "
            "If ALP and GGTP are also elevated, cholestatic pattern may be present. "
            "Low albumin suggests reduced synthetic function. High bilirubin indicates impaired conjugation or excretion."
        ),
        "follow_up": "Check hepatitis panel, liver ultrasound, PT/INR, and consider hepatology referral."
    },
    {
        "id": "cholestatic_pattern",
        "name": "Cholestatic Pattern",
        "required_high": ["alp"],
        "optional_high": ["ggtp", "bilirubin"],
        "min_optional_match": 1,
        "confidence_threshold": 0.5,
        "explanation": (
            "Isolated or predominant ALP elevation with GGTP suggests cholestasis (reduced bile flow). "
            "Causes include bile duct obstruction, drug-induced liver injury, or primary biliary cholangitis. "
            "GGTP elevation confirms the ALP is of hepatic origin rather than bone."
        ),
        "follow_up": "Liver ultrasound to check for biliary obstruction, medication review, and consider AMA if PBC suspected."
    },
    {
        "id": "metabolic_syndrome",
        "name": "Metabolic Syndrome Pattern",
        "required_high": ["triglycerides"],
        "optional_high": ["cholesterol", "ldl", "glucose", "hba1c"],
        "optional_low": ["hdl"],
        "min_optional_match": 2,
        "confidence_threshold": 0.6,
        "explanation": (
            "Elevated triglycerides combined with low HDL and/or high glucose suggests metabolic syndrome — "
            "a cluster of conditions increasing cardiovascular disease and diabetes risk. "
            "This pattern is often associated with abdominal obesity, insulin resistance, and sedentary lifestyle."
        ),
        "follow_up": "Check fasting insulin, waist circumference, blood pressure, and lifestyle counseling."
    },
    {
        "id": "diabetes_indicators",
        "name": "Diabetes Indicators Pattern",
        "required_high": ["glucose"],
        "optional_high": ["hba1c"],
        "min_optional_match": 0,
        "confidence_threshold": 0.3,
        "explanation": (
            "Elevated fasting glucose suggests impaired glucose tolerance or diabetes. "
            "HbA1c reflects average blood sugar over 2-3 months. Combined elevation confirms chronic hyperglycemia."
        ),
        "follow_up": "Repeat fasting glucose, oral glucose tolerance test, and endocrinology referral if persistently elevated."
    },
    {
        "id": "thyroid_hypothyroid",
        "name": "Hypothyroid Pattern",
        "required_high": ["tsh"],
        "optional_low": ["free t4", "free t3", "t4", "t3"],
        "min_optional_match": 1,
        "confidence_threshold": 0.5,
        "explanation": (
            "Elevated TSH with low Free T4 indicates primary hypothyroidism — the thyroid is underactive "
            "and the pituitary is compensating by producing more TSH. Common causes include Hashimoto's thyroiditis "
            "and iodine deficiency."
        ),
        "follow_up": "Check anti-TPO antibodies, repeat thyroid panel in 6-8 weeks, and consider levothyroxine if symptomatic."
    },
    {
        "id": "thyroid_hyperthyroid",
        "name": "Hyperthyroid Pattern",
        "required_low": ["tsh"],
        "optional_high": ["free t4", "free t3", "t4", "t3"],
        "min_optional_match": 1,
        "confidence_threshold": 0.5,
        "explanation": (
            "Suppressed TSH with elevated thyroid hormones indicates hyperthyroidism — the thyroid is overactive. "
            "Common causes include Graves' disease, toxic nodular goiter, and thyroiditis."
        ),
        "follow_up": "Check TSH receptor antibodies, thyroid uptake scan, and endocrinology referral."
    },
    {
        "id": "inflammation_pattern",
        "name": "Inflammation Pattern",
        "required_high": ["wbc"],
        "optional_high": ["esr", "crp", "platelet"],
        "min_optional_match": 1,
        "confidence_threshold": 0.4,
        "explanation": (
            "Elevated WBC (leukocytosis) suggests inflammation, infection, or stress response. "
            "Combined with elevated ESR/CRP, systemic inflammation is more likely. "
            "Reactive thrombocytosis (high platelets) can also accompany inflammation."
        ),
        "follow_up": "Differential WBC count, CRP, blood cultures if infection suspected, and clinical correlation."
    },
    {
        "id": "electrolyte_imbalance",
        "name": "Electrolyte Imbalance Pattern",
        "required_any": [["sodium"], ["potassium"]],
        "optional_any": [["sodium"], ["potassium"], ["chloride"], ["bicarbonate"], ["calcium"], ["magnesium"]],
        "min_optional_match": 2,
        "confidence_threshold": 0.5,
        "explanation": (
            "Abnormal electrolyte levels can indicate dehydration, kidney dysfunction, medication effects, "
            "or endocrine disorders. Multiple electrolyte abnormalities together suggest a systemic process "
            "rather than an isolated finding."
        ),
        "follow_up": "Check renal function, medication review, acid-base status, and consider endocrine workup if persistent."
    },
    {
        "id": "bleeding_clotting_risk",
        "name": "Bleeding/Clotting Risk Pattern",
        "required_low": ["platelet"],
        "optional_abnormal": ["pt", "ptt", "inr", "fibrinogen"],
        "min_optional_match": 1,
        "confidence_threshold": 0.5,
        "explanation": (
            "Low platelets (thrombocytopenia) combined with abnormal coagulation studies (PT/PTT/INR) "
            "suggests a broader hematologic or coagulation disorder. This increases bleeding risk."
        ),
        "follow_up": "Peripheral blood smear, coagulation factor assays, liver function tests, and hematology referral."
    },
]


# ===========================================================================
# HELPERS — RESPONSE FORMATTING (POLISH)
# ===========================================================================

def format_final_response(response_type, data, note=None):
    """
    Lightweight final formatter for consistent output across response types.
    Ensures: table → clean JSON, text → readable string, signal → formatted text,
    patterns → consistent markdown.
    
    Returns: dict with {'type', 'answer', 'note'} (and optional 'data')
    """
    if response_type == "table" and isinstance(data, list):
        # Table → structured JSON list
        return {
            "type": "table",
            "answer": f"Showing {len(data)} result(s)",
            "data": data,
            "note": note,
        }
    elif response_type == "signal" and isinstance(data, dict):
        # Signal → formatted text + raw data
        formatted_text = format_signal_output(data)
        return {
            "type": "signal",
            "answer": formatted_text,
            "raw_data": data,
            "note": note,
        }
    elif response_type == "text":
        # Text → readable string with optional note
        return {
            "type": "text",
            "answer": str(data) if not isinstance(data, str) else data,
            "note": note,
        }
    elif response_type == "error":
        # Error → standard format
        return {
            "type": "text",
            "answer": str(data),
            "note": note or "An error occurred. Please try again.",
        }
    else:
        # Fallback to text
        return {
            "type": "text",
            "answer": str(data),
            "note": note,
        }


def get_light_user_guidance(context=None):
    """
    Return light user guidance suggestions when fallback occurs or answer is weak.
    Keep it short and only show when relevant.
    """
    suggestions = [
        "• Ask 'show abnormal values' to see out-of-range results",
        "• Try 'explain [test name]' for more details",
        "• Ask 'give summary' for a concise overview",
    ]
    return "\n\nYou can also ask:\n" + "\n".join(suggestions)


# ===========================================================================
# HELPERS — STRING / NUMERIC
# ===========================================================================

def clean_numeric_value(value_str):
    """
    Extract clean numeric value from messy input.
    Handles: "12.513.5-17.5" -> "12.5", "150,000" -> "150000", "9.8 g/dL" -> "9.8"
    """
    if not value_str:
        return None

    cleaned = str(value_str).strip()

    # Remove thousand separators
    cleaned = re.sub(r'(\d),(\d)', r'\1\2', cleaned)

    # Remove non-numeric prefixes/suffixes
    cleaned = re.sub(r'^[^\d\-\.]*', '', cleaned)
    cleaned = re.sub(r'[^\d\-\.]*$', '', cleaned)

    # Handle range concatenated with value: "12.513.5-17.5"
    range_concat = re.match(r'^(\d+\.?\d*)(\d+\.?\d*\s*[-–]\s*\d+\.?\d*)$', cleaned)
    if range_concat:
        return range_concat.group(1)

    # Take leading number only
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
    """Extract character trigrams from a string."""
    s = re.sub(r'[\s\-_\.,()]', '', s.lower())
    if len(s) < 3:
        return {s}
    return {s[i:i+3] for i in range(len(s) - 2)}


def _token_set(s):
    """Extract set of alphabetic tokens from a string."""
    return set(re.findall(r'[a-z]+', s.lower()))


def fuzzy_match_score(query_str, test_name):
    """
    Calculate fuzzy match score between query and test name (REFINED for polish).
    Returns float 0.0–1.0+. Higher = better match.
    Uses trigram overlap, token containment, and length ratio.
    
    POLISH: Improved reliability by weighting exact matches and token matches higher.
    """
    if not query_str or not test_name:
        return 0.0

    q_norm = re.sub(r'[\s\-_\.,()]', '', query_str.lower())
    t_norm = re.sub(r'[\s\-_\.,()]', '', test_name.lower())

    # Exact substring — strongest signal (increased weight for polish)
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
    token_containment = (
        len(q_tokens & t_tokens) / len(q_tokens) if q_tokens and t_tokens else 0.0
    )

    len_ratio = min(len(q_norm), len(t_norm)) / max(len(q_norm), len(t_norm), 1)

    # POLISH: Increased token_containment weight for better reliability
    return (trigram_overlap * 0.4) + (token_containment * 0.45) + (len_ratio * 0.15)


# ===========================================================================
# HELPERS — STATUS / SEVERITY
# ===========================================================================

def detect_status(value, ref_range):
    """Returns NORMAL / HIGH / LOW / UNKNOWN. Uses clean_numeric_value() first."""
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
    # Clean ref_range to properly catch placeholders
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
    """
    Calculate mild / moderate / severe deviation based on % distance from range boundary.
    Returns: "normal" | "mild" | "moderate" | "severe" | "unknown"
    """
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
# HELPERS — QUERY ANALYSIS
# ===========================================================================

def detect_response_mode(query):
    """
    Detect the intent/mode of the query to customize LLM instructions.
    Returns: (mode_str, keyword_str)
    """
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
    """Dynamically determine similarity_search k based on query complexity."""
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
# HELPERS — DATA QUALITY & WARNINGS
# ===========================================================================

def get_data_quality_warning(table_rows):
    """Return warning string if data quality is poor, else empty string."""
    if not table_rows:
        return "⚠️ **No structured lab data found.** Upload a medical report PDF for analysis."

    total = len(table_rows)
    unknown_count = len([r for r in table_rows if r["status"] == "UNKNOWN"])
    valid_count = total - unknown_count
    warnings = []

    if unknown_count > 0:
        warnings.append(
            "⚠️ **Data Quality Note:** Some tests lack reference ranges, so their status may be incomplete."
        )

    if valid_count < 3 and total > 0:
        warnings.append(
            "⚠️ **Limited Data:** Very few tests with valid reference data available. Analysis may be incomplete."
        )

    return "\n".join(warnings) if warnings else ""


# ===========================================================================
# HELPERS — TABLE LOADING & CONTEXT
# ===========================================================================

VALID_CATEGORICAL_RESULTS = [
    "reactive", "non reactive", "non-reactive",
    "positive", "negative", "pos", "neg",
    "detected", "not detected",
    "indeterminate", "equivocal", "borderline",
    "seen", "not seen", "absent", "present",
]

VALID_SEROLOGICAL_TESTS = [
    "vdrl", "rpr", "hiv", "hcv", "hbv", "hbsag", "hbeag",
    "anti-hcv", "anti-hiv", "dengue", "malaria", "widal",
    "pregnancy", "preg test", "blood group", "rh",
    "elisa", "pcr", "rapid", "antibody", "antigen", "serology",
    "urine routine", "glucose", "protein", "ketones", "blood", "bilirubin", "urobilinogen", "nitrite"
]


def is_valid_test_row(test_name, value, unit="", reference_range=""):
    """Robust validation: allow real tests, reject metadata, footers, and garbage."""
    if not test_name or not value:
        return False

    test = str(test_name).lower().strip()
    value_str = str(value).strip()
    val_lower = value_str.lower()

    # ============================================
    # ✅ ALLOW VALID CATEGORICAL LAB RESULTS
    # ============================================
    is_categorical = val_lower in VALID_CATEGORICAL_RESULTS
    if re.match(r'^1:\d+$', value_str):
        is_categorical = True
    if re.match(r'^[1-4]\+$', value_str):
        is_categorical = True
        
    # Check if it starts with a categorical prefix (e.g., "Reactive 1:64", "Not Detected")
    if any(val_lower.startswith(cat) for cat in ["reactive", "non reactive", "non-reactive", "positive", "negative", "not detected", "detected"]):
        is_categorical = True

    is_numeric = bool(re.search(r'\d', value_str))

    if not is_numeric and not is_categorical:
        return False

    # Categorical values only allowed for serological/urine tests
    if is_categorical and not is_numeric:
        is_sero = any(s in test for s in VALID_SEROLOGICAL_TESTS)
        is_sero = is_sero or any(kw in test for kw in ["test", "screen", "panel", "card", "rapid"])
        if not is_sero:
            return False

    # ============================================
    # ❌ REJECT TIME / DATE PATTERNS
    # ============================================
    if re.search(r'\b\d{1,2}:\d{2}\b', value_str):
        return False
    if re.search(r'\b(am|pm)\b', val_lower):
        return False
    if re.search(r'\b\d{1,2}\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b', val_lower):
        return False

    # ============================================
    # ❌ REJECT METADATA / HEADERS / FOOTERS (EXPANDED)
    # ============================================
    metadata_keywords = [
        "age", "gender", "patient", "id", "page", "report", "date",
        "name", "address", "phone", "email", "registered", "collected",
        "reported", "instrument", "sample",
        # 🔥 NEW: Footer / Lab info patterns
        "plot no", "barcode", "page no", "client", "referring doctor",
        "ref no", "processed by", "billing date", "released on",
        "received on", "accession no", "dr.", "consultant", "senior",
        "end of report", "pathkind", "diagnostics", "pvt ltd"
    ]
    if any(k in test for k in metadata_keywords):
        return False

    # ============================================
    # ❌ REJECT SENTENCE FRAGMENTS / CLINICAL NOTES
    # ============================================
    fragment_keywords = [
        "tested", "please", "note", "this ", "in case", "as per",
        "confirmation", "guidelines", "comprises", "should be",
        "is used", "is a ", "may be", "can be", "is helpful", "is the",
        "clinical significance", "method", "principal"
    ]
    if any(test.startswith(f) for f in fragment_keywords):
        return False

    # ============================================
    # ❌ REJECT NARRATIVE TEXT IN VALUE
    # ============================================
    narrative_keywords = [
        "associated", "risk", "recommended", "suggested", "evidence",
        "increase", "decrease", "should be", "advised to"
    ]
    if any(word in test for word in narrative_keywords):
        return False
    if any(word in val_lower for word in narrative_keywords):
        return False

    # ============================================
    # ❌ REJECT LONG SENTENCES
    # ============================================
    if len(test.split()) > 10:
        return False

    # ============================================
    # ❌ TEST NAME MUST BE ALPHABETIC ENOUGH
    # ============================================
    if sum(c.isalpha() for c in test) < 3:
        return False

    # ❌ Reject address-like pattern starting with number
    if re.match(r'^\d+[\w\s,.-]+$', test):
        return False

    return True

def load_and_parse_table_rows(session_key):
    """
    Load table data from cache, clean values, detect statuses + severity,
    deduplicate, and return clean list of row dicts.
    """
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

                # Light cleanup: strip extra spaces
                test = re.sub(r'\s+', ' ', test)
                unit = re.sub(r'\s+', ' ', unit)
                
                # Normalize common units
                if unit.lower() == "g/dl":
                    unit = "g/dL"
                elif unit.lower() == "mg/dl":
                    unit = "mg/dL"

                # Validate row before processing
                if not is_valid_test_row(test, value, range_val):
                    continue

                cleaned = clean_numeric_value(value)
                if not cleaned:
                    continue
                value = cleaned  # use cleaned value from here on

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

    # Deduplicate — keep only first occurrence of each test
    seen = set()
    unique_rows = []
    for row in table_rows:
        key = normalize_test_name(row["test"])
        if key not in seen:
            seen.add(key)
            unique_rows.append(row)

    # Merge Clinical Notes Lab Data (Low Priority)
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
    """Render table rows into plain-text for LLM prompts."""
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
    """
    Return semantic search context from vectorstore, with optional metadata filtering.
    
    Args:
        question: The query string
        k: Number of documents to retrieve
        filter_metadata: Optional dict for FAISS metadata filtering
                       Example: {"chunk_type": "lab_test", "flag": "HIGH"}
    """
    if not os.path.exists(INDEX_PATH):
        return ""
    try:
        vectorstore = load_vectorstore()
        
        if filter_metadata:
            # FAISS supports simple dict matching
            # Note: FAISS doesn't support $in, $or operators - exact match only
            docs = vectorstore.similarity_search(question, k=k, filter=filter_metadata)
        else:
            docs = vectorstore.similarity_search(question, k=k)
            
        return "\n\n".join(doc.page_content for doc in docs)
    except Exception as e:
        print(f"Vectorstore error: {e}")
        return ""

# ===========================================================================
# HELPERS — NAMED TEST EXTRACTION (FUZZY)
# ===========================================================================

def extract_named_tests_fuzzy(query_text, table_rows=None, score_threshold=0.75):
    """
    Fuzzy-match test names from query against known aliases and report rows.
    Returns list of standard test names matched above threshold.
    
    POLISH: Refined thresholds for safer matching:
    - >= 0.75: Accept strong matches
    - 0.6–0.75: Accept only if strong alias match or exact token match
    - < 0.6: Reject (too risky)
    """
    found = []
    seen_scores = {}

    for std_name, aliases in TEST_ALIASES.items():
        best_score = max(fuzzy_match_score(query_text, name) for name in [std_name] + aliases)
        
        # POLISH: Apply refined threshold logic
        if best_score >= 0.75:
            # Strong match — accept unconditionally
            found.append(std_name)
            seen_scores[std_name] = best_score
        elif 0.6 <= best_score < 0.75:
            # Conditional zone — check for strong alias match or exact token match
            q_tokens = _token_set(query_text)
            strong_match = any(
                _token_set(alias) & q_tokens for alias in [std_name] + aliases
            )
            if strong_match:
                found.append(std_name)
                seen_scores[std_name] = best_score

    if table_rows:
        for row in table_rows:
            score = fuzzy_match_score(query_text, row["test"])
            std = normalize_test_name(row["test"])
            
            # Apply same refined threshold logic
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
    """
    Resolve pronouns like 'it', 'that', 'the value' in follow-up questions.
    Priority: last discussed test > last user query tests > most severe abnormal.
    Returns: (resolved_test_name | None, resolved_row | None, original_question)
    """
    q = question.lower().strip()
    pronoun_signals = [
        r"\bit\b", r"\bthat\b", r"\bthis\b",
        r"\bthe (?:value|result|test|level|reading)\b",
        r"\bmy (?:value|result|test|level)\b"
    ]
    if not any(re.search(p, q) for p in pronoun_signals):
        return None, None, question

    sev_rank = {"severe": 4, "moderate": 3, "mild": 2, "normal": 0, "unknown": 0}

    # Priority 1: Last assistant message — extract bold-marked test names
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

    # Priority 2: Previous user message — fuzzy match test names
    if history:
        for msg in reversed(history):
            if msg["role"] == "user":
                prev_tests = extract_named_tests_fuzzy(msg["content"], table_rows)
                if prev_tests:
                    for row in table_rows:
                        if normalize_test_name(row["test"]) in prev_tests:
                            return row["test"], row, question
                break

    # Priority 3: Most severe abnormal test, optionally filtered by direction
    direction_filter = None
    if any(w in q for w in ["low", "decreased", "below"]):
        direction_filter = "LOW"
    elif any(w in q for w in ["high", "elevated", "increased", "above"]):
        direction_filter = "HIGH"

    candidates = [r for r in table_rows if r["status"] in ["HIGH", "LOW"]]
    if direction_filter:
        candidates = [r for r in candidates if r["status"] == direction_filter]

    if candidates:
        candidates.sort(
            key=lambda x: sev_rank.get(x.get("severity", "unknown"), 0),
            reverse=True
        )
        return candidates[0]["test"], candidates[0], question

    return None, None, question


# ===========================================================================
# HELPERS — GRAPH / PATTERN ANALYSIS
# ===========================================================================

def generate_graph_observations(table_rows):
    """Build structured observation dict from table rows for graph analysis."""
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
    """Generate graph analysis text deterministically — no LLM needed."""
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
        lines.append("• All values within normal range — graph would show tight clustering in the healthy zone.")
    elif normal_pct >= 75:
        lines.append("• Mostly normal with a few outliers — graph would show most points near center with 1–2 deviations.")
    elif normal_pct >= 50:
        lines.append("• Mixed profile — roughly half normal, half abnormal. Notable spread in the distribution.")
    else:
        lines.append("• Predominantly abnormal profile — significant deviation from reference ranges across tests.")

    if observations["abnormal_tests"]:
        lines.append("\n**Notable Deviations:**")
        for t in observations["abnormal_tests"][:5]:
            arrow = "⬆️" if t["status"] == "HIGH" else "⬇️"
            sev = t.get("severity", "")
            sev_str = f" [{sev}]" if sev and sev != "normal" else ""
            range_str = f" (ref: {t['range']})" if t["range"] else ""
            lines.append(f"• {arrow} **{t['test']}**: {t['value']} {t['unit']}{range_str}{sev_str}")

    # Category cluster detection
    if len(observations["abnormal_tests"]) >= 2:
        categories = {
            "Liver": ["alt", "ast", "alp", "ggtp", "bilirubin", "albumin"],
            "Kidney": ["creatinine", "urea", "bun", "gfr", "potassium", "sodium"],
            "Blood": ["hemoglobin", "hb", "rbc", "mcv", "mch", "mchc", "rdw", "platelet"],
            "Lipids": ["cholesterol", "ldl", "hdl", "triglycerides", "vldl"],
            "Thyroid": ["tsh", "t3", "t4", "free t3", "free t4"],
            "Sugar": ["glucose", "hba1c", "blood sugar"],
        }
        lines.append("\n**Cluster Detection:**")
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
                    f"• 🔗 **{cat_name} cluster**: {len(matched)} related tests abnormal ({names}) "
                    f"— suggests possible {cat_name.lower()} involvement."
                )
        if not found_cluster:
            lines.append("• No clear category clustering among abnormal values.")

    return "\n".join(lines)


def detect_cross_test_patterns(table_rows):
    """
    Scan table data for known multi-test medical patterns.
    Returns list of detected patterns sorted by reliability then severity.
    """
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

        # Reliability based on optional evidence depth
        if optional_matches >= 2:
            reliability = "high"
        elif optional_matches >= 1:
            reliability = "medium"
        else:
            reliability = "low"

        # Max severity score across matched tests
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

    # Sort: reliability → severity score → match count
    rel_map = {"high": 3, "medium": 2, "low": 1}
    detected.sort(
        key=lambda x: (rel_map.get(x["reliability"], 0), x["max_severity_score"], len(x["matched_tests"])),
        reverse=True
    )
    return detected[:3]


# ===========================================================================
# HELPERS — SIGNAL OUTPUT
# ===========================================================================

def format_signal_output(raw_result):
    """Convert raw signal analysis dict to readable formatted markdown."""
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
        lines.append("\n**⚠️ Abnormalities Detected:**")
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

    lines.append(
        "\n_Note: This is an automated analysis. "
        "Please consult a cardiologist for clinical interpretation._"
    )
    return "\n".join(lines)


# ===========================================================================
# HELPERS — CONVERSATION
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
# HELPERS — HEALTH SCORE & LLM
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

    if final_score >= 90:   health_status = "Excellent"
    elif final_score >= 70: health_status = "Good"
    elif final_score >= 50: health_status = "Mild Concern"
    elif final_score >= 30: health_status = "Moderate Risk"
    else:                   health_status = "High Risk"

    abnormal_count = len(abnormal_tests)
    message = (
        f"All {len(valid_tests)} tested values are within the normal range."
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


def call_llm(messages, temperature=0.3, max_retries=2):
    """Call Groq LLM with retry logic and proper error logging."""
    import time
    
    last_error = None
    
    for attempt in range(max_retries + 1):
        try:
            client = get_groq_client()
            
            # Log token estimate for debugging
            total_chars = sum(len(m.get("content", "")) for m in messages)
            estimated_tokens = total_chars // 4  # Rough estimate
            print(f"🔄 LLM call attempt {attempt + 1}/{max_retries + 1} (~{estimated_tokens} tokens)")
            
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=messages,
                temperature=temperature,
                max_tokens=1500,
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
            
            # Don't retry on auth errors
            if "authentication" in last_error.lower() or "api_key" in last_error.lower():
                break
            
            if attempt < max_retries:
                time.sleep(2 * (attempt + 1))  # Exponential backoff
    
    print(f"❌ LLM failed after {max_retries + 1} attempts. Last error: {last_error}")
    return None


# ===========================================================================
# UPLOAD & INDEX
# ===========================================================================

@csrf_exempt
@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
def upload_and_index(request):
    if "file" not in request.FILES:
        return Response({"error": "No file uploaded"}, status=400)

    file_obj = request.FILES["file"]
    file_name = file_obj.name.lower()
    unique_filename = f"{uuid.uuid4()}_{file_obj.name}"
    file_path = os.path.join(MEDIA_DIR, unique_filename)

    with open(file_path, "wb") as f:
        for chunk in file_obj.chunks():
            f.write(chunk)

    session_key = request.session.session_key or request.META.get("REMOTE_ADDR", "default")

    try:
        if file_name.endswith(".csv"):
            cache.set(f"latest_signal_file_{session_key}", file_path, timeout=3600)
            clear_conversation(session_key)
            return Response({"message": "Signal file uploaded successfully. Ask about ECG or heart rate for analysis."})

        elif file_name.endswith(".pdf"):
            clear_vectorstore_cache()
            text = extract_text_from_pdf(file_path)
            table_json = extract_tables(file_path)  # This is JSON string

            clinical_note_input = request.POST.get("clinical_note", "")
            note_text = clinical_note_input if clinical_note_input else text
            clinical_data = extract_clinical_data(note_text)
            print(f"[Clinical Extracted]: {clinical_data}")
            cache.set(f"latest_clinical_data_{session_key}", json.dumps(clinical_data), timeout=3600)

            cache.set(f"latest_pdf_text_{session_key}", text, timeout=3600)
            cache.set(f"latest_table_data_{session_key}", table_json, timeout=3600)

            # ✅ FIX: Pass text and table_json SEPARATELY
            docs = split_text(text, table_json)
            create_vectorstore(docs)
            clear_conversation(session_key)

            print("PDF INDEXED SUCCESSFULLY")
            return Response({"message": "PDF indexed successfully"})

        else:
            return Response({"error": "Unsupported file type. Please upload PDF or CSV."}, status=400)

    except Exception as e:
        print("UPLOAD ERROR:", e)
        return Response({"error": str(e)}, status=500)


# ===========================================================================
# QUERY DOCUMENT — Hybrid Router
# ===========================================================================
#
#  PRE-PROCESSING
#    └─ resolve_follow_up_context()  (pronoun resolution)
#
#  DETERMINISTIC HANDLERS (ordered, fast, no LLM)
#    1. Signal / ECG
#    2. Show full table
#    3. Abnormal values only
#    4. Health score
#    5. Cross-test pattern detection
#    6. Named test lookup  (fuzzy, value queries)
#    7. Graph / chart / trend
#
#  UNIFIED LLM HANDLER  (catches everything else)
#    • Full table context (with severity) + vector context
#    • Pattern context injected as LLM hint
#    • Follow-up resolution context
#    • Response mode instruction (why / explain / summary)
#    • Data quality warning appended when needed
#
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

    # Load structured table data once — shared by all handlers
    table_rows = load_and_parse_table_rows(session_key)
    valid_count = len([r for r in table_rows if r["status"] in ["NORMAL", "HIGH", "LOW"]])
    print(f"\n📊 {len(table_rows)} tests ({valid_count} with status) | Q: {question[:80]}")

    # Correlate Conditions & Build Clinical Context
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
                clinical_context = "--- CLINICAL NOTES (LOW CONFIDENCE) ---\n" + "\n".join(clinical_parts) + "\n\n"
        except Exception as e:
            print(f"Clinical context error: {e}")

    # ------------------------------------------------------------------
    # PRE-PROCESS: Resolve follow-up context ("why is it low?")
    # ------------------------------------------------------------------
    resolved_test, resolved_row, effective_question = resolve_follow_up_context(
        question, table_rows, history
    )
    if resolved_test:
        q = effective_question.lower()
        print(f"🔗 Follow-up resolved: '{question}' → '{resolved_test}'")

    # ------------------------------------------------------------------
    # HANDLER 1: Signal / ECG
    # ------------------------------------------------------------------
    SIGNAL_KEYWORDS = ["ecg", "heart rate", "signal", "cardiac rhythm", "heartbeat", "ekg"]
    if any(w in q for w in SIGNAL_KEYWORDS):
        signal_file = cache.get(f"latest_signal_file_{session_key}")
        if not signal_file:
            error_msg = "No ECG or signal data found. Please upload a signal CSV file first."
            add_to_conversation(session_key, "user", question)
            add_to_conversation(session_key, "assistant", error_msg)
            resp = format_final_response("error", error_msg, note="Upload a CSV file with ECG/signal data")
            resp["history"] = history
            return Response(resp, status=200)
        try:
            result = analyze_signal(signal_file, signal_type="ecg")
            formatted = format_signal_output(result)
            add_to_conversation(session_key, "user", question)
            add_to_conversation(session_key, "assistant", formatted)
            return Response({"type": "signal", "answer": formatted, "raw_data": result, "history": history})
        except Exception as e:
            print(f"Signal error: {e}")
            error_msg = "Could not analyze the signal file. Ensure it is a valid CSV with signal data."
            add_to_conversation(session_key, "user", question)
            add_to_conversation(session_key, "assistant", error_msg)
            resp = format_final_response("error", error_msg)
            resp["history"] = history
            return Response(resp, status=200)

    # ------------------------------------------------------------------
    # HANDLER 2: Show full table
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # HANDLER 3: Abnormal values only
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # HANDLER 4: Health score
    # ------------------------------------------------------------------
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
            return Response(format_final_response("error", answer, note="Upload a complete medical report"), status=200)
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

    # ------------------------------------------------------------------
    # HANDLER 5: Cross-test pattern detection
    # ------------------------------------------------------------------
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
            answer += "\n\n⚠️ *These are pattern suggestions based on lab values, not diagnoses. Consult your doctor for clinical correlation.*"

        add_to_conversation(session_key, "user", question)
        add_to_conversation(session_key, "assistant", answer)
        return Response({"type": "text", "answer": answer, "patterns": patterns, "history": history})

    # ------------------------------------------------------------------
    # HANDLER 6: Named test lookup (fuzzy)
    # ------------------------------------------------------------------
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
                return Response({"type": "table_with_explanations", "data": explanations, "history": history})

    # ------------------------------------------------------------------
    # HANDLER 8: Structured Chart Interpreter
    # ------------------------------------------------------------------
    chart_data = request.data.get("chart_data", None)

    if chart_data is not None:
        if not isinstance(chart_data, dict) or "data" not in chart_data:
            error_msg = "Invalid chart data format."
            add_to_conversation(session_key, "user", question)
            add_to_conversation(session_key, "assistant", error_msg)
            history = get_conversation_history(session_key)
            return Response({
                "type": "error",
                "answer": error_msg,
                "history": history
            })
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

            return Response({
                "type": "error",
                "answer": error_msg,
                "history": history
            })

    # ------------------------------------------------------------------
    # HANDLER 7: Graph / chart / trend
    # ------------------------------------------------------------------
    GRAPH_KEYWORDS = ["graph", "chart", "trend", "visualization", "visualise", "visualize", "plot", "diagram"]
    if any(w in q for w in GRAPH_KEYWORDS):
        valid_rows = [r for r in table_rows if r["status"] in ["NORMAL", "HIGH", "LOW"]]
        if not valid_rows:
            error_msg = "I don't have enough structured lab data to generate graph insights. Please upload a medical report with test results first."
            guidance = get_light_user_guidance("graph")
            add_to_conversation(session_key, "user", question)
            add_to_conversation(session_key, "assistant", error_msg + guidance)
            resp = format_final_response("error", error_msg, note="Upload a PDF medical report with test results")
            resp["history"] = history
            return Response(resp, status=200)

        observations = generate_graph_observations(table_rows)
        answer = generate_deterministic_graph_insights(observations)

        patterns = detect_cross_test_patterns(table_rows)
        if patterns:
            answer += "\n\n**🔗 Related Patterns:**"
            for p in patterns[:3]:
                answer += f"\n• **{p['pattern_name']}** (Reliability: {p['reliability'].title()}): {', '.join(p['matched_tests'])}"

        add_to_conversation(session_key, "user", question)
        add_to_conversation(session_key, "assistant", answer)
        return Response({
            "type": "graph_analysis",
            "answer": answer,
            "chart_data": {
                "distribution": observations["distribution_pct"],
                "tests": observations["all_tests"],
            },
            "history": history,
        })

    # ------------------------------------------------------------------
    # UNIFIED LLM HANDLER (IMPROVED - FIX #2)
    # ------------------------------------------------------------------

    response_mode, _ = detect_response_mode(question)
    data_warning = get_data_quality_warning(table_rows)

    MODE_INSTRUCTIONS = {
        "reasoning": (
            "\nRESPONSE MODE: REASONING\n"
            "- Focus on explaining WHY a value might be abnormal\n"
            "- Discuss common medical causes and contributing factors\n"
            "- Structure: State the finding → Explain possible causes → Recommend follow-up\n"
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
            "- Keep the response brief and scannable\n"
            "- Use bullet points for key findings\n"
            "- Prioritize: Abnormal values → Borderline values → Normal summary\n"
            "- Limit to 150-200 words unless user asks for more detail\n"
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
    )

    # Build table context
    table_context = build_table_context_string(table_rows)
    
    # 🔥 FIX: For summaries, use a COMPACT context to avoid token limits
    if response_mode == "concise":
        abnormal = [r for r in table_rows if r["status"] in ["HIGH", "LOW"]]
        normal_count = len([r for r in table_rows if r["status"] == "NORMAL"])
        unknown_count = len([r for r in table_rows if r["status"] == "UNKNOWN"])
        
        compact_lines = [
            f"Total tests: {len(table_rows)}",
            f"Normal: {normal_count}, Abnormal: {len(abnormal)}, Unknown status: {unknown_count}",
        ]
        if abnormal:
            compact_lines.append("\nAbnormal tests:")
            for r in abnormal:
                arrow = "↑" if r["status"] == "HIGH" else "↓"
                compact_lines.append(
                    f"- {r['test']}: {r['value']} {r['unit']} {arrow} (ref: {r['range'] or 'N/A'})"
                )
        
        table_context = "\n".join(compact_lines)
        # Skip patterns and clinical context for summaries (reduces size by 60%+)
        pattern_context = ""
        clinical_context = ""
    else:
        # Full context for other query types
        if data_warning:
            table_context = f"{data_warning}\n\n{table_context}"

        cross_patterns = detect_cross_test_patterns(table_rows)
        pattern_context = ""
        if cross_patterns:
            lines = ["DETECTED MEDICAL PATTERNS (mention if relevant to the question):"]
            for p in cross_patterns[:3]:
                lines.append(
                    f"- {p['pattern_name']} (Reliability: {p['reliability']}): "
                    f"Tests {p['matched_tests']}. {p['explanation']}"
                )
            pattern_context = "\n".join(lines)

    # Follow-up resolution hint
    followup_context = ""
    if resolved_test and resolved_row:
        followup_context = (
            f"FOLLOW-UP RESOLUTION: The user is asking about \"{resolved_test}\" "
            f"(value: {resolved_row['value']} {resolved_row['unit']}, "
            f"status: {resolved_row['status']}, severity: {resolved_row.get('severity', 'unknown')}). "
            f"Address this specific test in your answer."
        )

    # 🔥 FIX: Reduce vector context size
    adaptive_k = get_adaptive_k(question, table_rows)
    if response_mode == "concise":
        adaptive_k = min(adaptive_k, 5)  # Less vector context for summaries
    
    vector_context = get_vector_context(question, k=adaptive_k)

    # 🔥 FIX: Reduce history size
    history_text = "\n".join([
        f"{'User' if h['role'] == 'user' else 'Assistant'}: {h['content'][:200]}"  # Truncate long messages
        for h in history[-4:]  # Only last 4 messages instead of 6
    ]) if history else "No prior conversation."

    effective_q = (
        f"{question} [Specifically about: {resolved_test}]"
        if resolved_test else question
    )

    user_message = (
        f"--- STRUCTURED LAB DATA ---\n{table_context}\n\n"
        f"{pattern_context}\n\n"
        f"{followup_context}\n\n"
        f"{clinical_context}"
        f"--- DOCUMENT CONTEXT ---\n{vector_context or 'No additional document text available.'}\n\n"
        f"--- CONVERSATION HISTORY ---\n{history_text}\n\n"
        f"--- USER'S QUESTION ---\n{effective_q}"
    )

    answer = call_llm(
        [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}],
        temperature=0.35,
    )

    if not answer:
        # 🔥 FIX: Give specific error based on data availability
        if not table_rows:
            base_msg = "I couldn't find any structured lab data in your report. Please upload a medical report PDF with test results."
        elif len(table_rows) < 3:
            base_msg = f"I only found {len(table_rows)} test(s) in your report, which isn't enough to generate a meaningful summary. Please upload a complete lab report."
        else:
            base_msg = "I'm sorry, I couldn't generate a response right now. This might be due to a temporary issue. Please try again."
        
        guidance = get_light_user_guidance("llm_fallback")
        answer = base_msg + guidance

    # Prepend data warning only for non-summary responses
    if data_warning and "No structured lab data" not in data_warning and response_mode != "concise":
        answer = f"{data_warning}\n\n{answer}"

    add_to_conversation(session_key, "user", question)
    add_to_conversation(session_key, "assistant", answer)
    resp = format_final_response("text", answer)
    resp["history"] = history
    return Response(resp, status=200)
# ===========================================================================
# UI
# ===========================================================================

def ui(request):
    return render(request, "rag/index.html")