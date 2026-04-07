import re
def normalize_test_name(name):
    import re
    if not name:
        return ""
    return re.sub(r'[\s\-_\.,()]', '', name.lower())

TEST_MAP = {
    "hb": "hemoglobin",
    "hemoglobin": "hemoglobin",
    "wbc": "wbc",
    "rbc": "rbc",
    "platelet": "platelet",
    "platelets": "platelet",
    "creatinine": "creatinine",
    "glucose": "glucose",
    "hba1c": "hba1c",
    "tsh": "tsh",
    "t3": "t3",
    "t4": "t4"
}
# Deterministic knowledge bases
SYMPTOMS = {
    "fatigue", "fever", "nausea", "dizziness", "headache", "pain", 
    "shortness of breath", "cough", "weakness", "sweating", "chills",
    "weight loss", "weight gain", "chest pain", "palpitations"
}

CONDITIONS = {
    "diabetes", "hypertension", "anemia", "asthma", "hypothyroidism", 
    "hyperthyroidism", "infection", "kidney disease", "liver disease",
    "ckd", "copd", "obesity", "hyperlipidemia"
}

# Regex for test mentions. E.g., "Hemoglobin 12.5", "Hb: 12.5", "Glucose = 100", "wbc is 5.5"
LAB_REGEX = re.compile(
    r"(?i)\b(hemoglobin|hb|wbc|rbc|platelets?|hematocrit|pcv|mcv|creatinine|urea|bun|ast|alt|alp|bilirubin|glucose|hba1c|tsh|t3|t4|sodium|potassium|calcium)\b[\s\:\=\-]*(?:is\s+)?([\d,\.]+)"
)

def extract_clinical_data(text: str) -> dict:
    """
    Extracts symptoms, conditions, and lab mentions from raw clinical text
    using deterministic keyword matching and regex.
    """
    if not text:
        return {
            "symptoms": [],
            "conditions": [],
            "lab_mentions": [],
            "source": "clinical_note",
            "confidence": "low"
        }
    
    text_lower = text.lower()
    
    # def keyword_match(text, keywords):
    #     return [
    #         k for k in keywords
    #         if re.search(rf"\b{k}\b", text)
    # ]
    def keyword_match(text, keywords):
        return [
            k for k in keywords
            if re.search(rf"\b{k}\b", text)
        ]

    found_symptoms = keyword_match(text_lower, SYMPTOMS)
    found_conditions = keyword_match(text_lower, CONDITIONS)
    
    lab_mentions = []
    for match in LAB_REGEX.finditer(text):
        test_name = match.group(1).strip().lower()
        test_name = TEST_MAP.get(test_name, test_name)
        try:
            raw_value = match.group(2).replace(",", "").rstrip(".")
            value = float(raw_value)
            lab_mentions.append({"test": test_name, "value": value})
        except ValueError:
            continue
            
    return {
        "symptoms": list(set(found_symptoms)),
        "conditions": list(set(found_conditions)),
        "lab_mentions": lab_mentions,
        "source": "clinical_note",
        "confidence": "low"
    }

def normalize_lab_mentions(extracted_data: dict) -> list:
    """
    Converts extracted labs into the system's structured schema.
    Missing units and ranges are left blank for fallback handling.
    """
    normalized = []
    for lab in extracted_data.get("lab_mentions", []):
        normalized.append({
            "test": lab["test"].title(),
            "value": float(lab["value"]),
            "unit": "",
            "range": "",
            "status": "UNKNOWN",
            "severity": "unknown",
            "source": extracted_data.get("source", "clinical_note"),
            "confidence": extracted_data.get("confidence", "low")
        })
    return normalized

def correlate_conditions_with_labs(clinical_data: dict, table_rows: list) -> dict:
    """
    Enhances condition confidence based on abnormal lab correlations.
    Flags inconsistencies if expected abnormal labs do not match.
    """
    if not clinical_data or not table_rows:
        return clinical_data

    abnormal_labs = {r["test"].lower(): r["status"] for r in table_rows if r.get("status") in ["HIGH", "LOW"] and r.get("source", "lab_report") == "lab_report"}
    
    condition_lab_map = {
        "anemia": {"hemoglobin": "LOW", "hb": "LOW", "rbc": "LOW", "hematocrit": "LOW", "pcv": "LOW"},
        "diabetes": {"glucose": "HIGH", "hba1c": "HIGH"},
        "kidney disease": {"creatinine": "HIGH", "bun": "HIGH", "urea": "HIGH"},
        "ckd": {"creatinine": "HIGH", "bun": "HIGH", "urea": "HIGH"},
        "infection": {"wbc": "HIGH"},
        "liver disease": {"ast": "HIGH", "alt": "HIGH", "alp": "HIGH", "bilirubin": "HIGH"},
        "hypothyroidism": {"tsh": "HIGH"},
        "hyperthyroidism": {"tsh": "LOW"},
        "hyperlipidemia": {"cholesterol": "HIGH", "ldl": "HIGH", "triglycerides": "HIGH"}
    }

    correlated_conditions = []
    for cond_name in clinical_data.get("conditions", []):
        if isinstance(cond_name, dict):
            cond_name = cond_name.get("name", "")
            
        cond_obj = {"name": cond_name, "confidence": "low", "flag": None}
        
        if cond_name in condition_lab_map:
            expected_labs = condition_lab_map[cond_name]
            matched = False
            mismatched = False
            
            # Check against abnormal labs
            for test, expected_status in expected_labs.items():
                for ab_test, ab_status in abnormal_labs.items():
                    if normalize_test_name(ab_test) == normalize_test_name(test):
                        if ab_status == expected_status:
                            matched = True
                        else:
                            mismatched = True
            
            if matched:
                cond_obj["confidence"] = "high"
                cond_obj["flag"] = "confirmed_by_lab"
            elif mismatched:
                cond_obj["confidence"] = "low"
                cond_obj["flag"] = "inconsistent_with_lab"
            else:
                cond_obj["confidence"] = "low"
                
        correlated_conditions.append(cond_obj)

    clinical_data["conditions"] = correlated_conditions
    return clinical_data