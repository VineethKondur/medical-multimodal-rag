import os
import re
import json
from dotenv import load_dotenv
from groq import Groq
from django.core.cache import cache

load_dotenv()

_cached_client = None


def get_groq_client():
    global _cached_client
    if _cached_client is None:
        _cached_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    return _cached_client


# ════════════════════════════════════════════════════════════════════
# LEGACY: Single Test Explanation (Keep for backward compatibility)
# ════════════════════════════════════════════════════════════════════

def generate_test_explanation(test_name: str) -> str:
    """Explain a medical test with 1-day cache."""
    cache_key = f"explain_{test_name.lower()}"
    cached = cache.get(cache_key)

    if cached:
        return cached

    client = get_groq_client()

    prompt = f"""Explain the medical test: {test_name}

Rules:
- Keep it simple (2 lines max)
- Do NOT include values
- Do NOT assume patient condition
- Just explain what the test measures

Answer:"""

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )

    explanation = response.choices[0].message.content.strip()
    cache.set(cache_key, explanation, timeout=86400)  # 1 day cache

    return explanation


# ════════════════════════════════════════════════════════════════════
# 🆕 NEW: Flexible Lab Query Handler (Uses Actual Report Data)
# ════════════════════════════════════════════════════════════════════

def ask_about_lab_report(question: str, extracted_data: list[dict], llm_client=None) -> str:
    """
    Ask ANY question about lab results.
    
    LLM will use ONLY the data you provide (no hallucination).
    Works with ANY lab report type (CBC, LFT, Lipid, ECG, etc.)
    
    🔥 ENHANCED: Now includes clinical urgency scoring!
    """
    
    if not extracted_data:
        return "⚠️ No laboratory data available."
    
    # Step 1: Prepare clean data context WITH URGENCY FLAGS
    data_context = format_data_for_llm(extracted_data)
    
    # Step 2: Build smart prompt that prevents hallucination + adds urgency
    prompt = build_grounded_prompt(question, data_context)
    
    # Debug log
    print("\n" + "="*60)
    print(f"🔍 Question: {question}")
    print(f"📊 Data points: {len(extracted_data)}")
    
    # 🔥 NEW: Log urgent findings
    urgent_findings = assess_clinical_urgency(extracted_data)
    if urgent_findings['critical_count'] > 0:
        print(f"🚨 CRITICAL FINDINGS: {urgent_findings['critical_count']} (HR={urgent_findings.get('heart_rate', 'N/A')})")
    print("="*60)
    
    # Step 3: Call LLM
    client = llm_client or get_groq_client()
    
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": GROUNDED_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=1500,  # Increased for detailed summaries
        )
        
        answer = response.choices[0].message.content.strip()
        
        print(f"✅ Response generated ({len(answer)} chars)")
        print("="*60 + "\n")
        
        return answer
    
    except Exception as e:
        print(f"❌ Error: {e}")
        return f"⚠️ Error generating response: {str(e)}"


def format_data_for_llm(data: list[dict]) -> str:
    """
    Convert extraction output to clean LLM-friendly format.
    
    🔥 ENHANCED: Now includes urgency classification and ECG-specific formatting
    """
    
    lines = []
    
    # Summary stats
    total = len(data)
    abnormal = [t for t in data if t.get('flag')]
    normal_count = total - len(abnormal)
    
    lines.append("<LAB_REPORT_DATA>")
    lines.append(f"Parameters tested: {total} | Normal: {normal_count} | Abnormal: {len(abnormal)}")
    
    # 🔥 NEW: Urgency assessment
    urgency = assess_clinical_urgency(data)
    if urgency['critical_count'] > 0:
        lines.append(f"\n🚨 URGENT: {urgency['critical_count']} critical finding(s) detected!")
        if urgency.get('heart_rate'):
            lines.append(f"   Heart Rate: {urgency['heart_rate']} bpm ({urgency.get('hr_status', 'ABNORMAL')})")
        if urgency.get('has_av_block'):
            lines.append(f"   ⚠️ Conduction abnormality suspected (AV block)")
    elif urgency['warning_count'] > 0:
        lines.append(f"\n⚠️ WARNING: {urgency['warning_count']} abnormal value(s) requiring attention")
    else:
        lines.append(f"\n✅ No critical abnormalities detected")
    
    lines.append("")
    
    # Results table - SORTED BY SEVERITY (Critical first!)
    lines.append("<RESULTS>")
    
    # Separate into categories
    critical_tests = []
    warning_tests = []
    normal_tests = []
    unknown_tests = []
    
    for t in data:
        name = t.get('test', 'Unknown').lower()
        value = t.get('value', '-')
        flag = t.get('flag', '')
        
        # Classify urgency
        if _is_critical_finding(name, value, flag):
            critical_tests.append(t)
        elif flag in ['HIGH', 'LOW']:
            warning_tests.append(t)
        elif flag == 'UNKNOWN':
            unknown_tests.append(t)
        else:
            normal_tests.append(t)
    
    # Print order: Critical → Warning → Normal → Unknown
    priority_order = [
        ("🚨 CRITICAL ABNORMALITIES (Immediate Attention Required)", critical_tests),
        ("⚠️ ABNORMAL VALUES (Monitor Closely)", warning_tests),
        ("✅ NORMAL VALUES", normal_tests[:15]),  # Limit normal to save space
        ("❓ UNKNOWN STATUS (Needs Reference Range)", unknown_tests),
    ]
    
    i = 1
    for header, test_list in priority_order:
        if not test_list:
            continue
            
        lines.append(f"\n--- {header} ---")
        
        for t in test_list:
            name = t.get('test', 'Unknown')
            value = t.get('value', '-')
            unit = t.get('unit', '')
            ref = t.get('range', '')
            flag = t.get('flag', '')
            
            line = f"{i}. {name}: {value}"
            if unit:
                line += f" {unit}"
            if ref and ref.lower() != 'n/a':
                line += f" (ref: {ref})"
            if flag:
                line += f" [{flag.upper()}]"
            
            # Add urgency icon for critical/warning
            if t in critical_tests:
                line = f"🔴 {line}"  # Red flag
            elif t in warning_tests:
                line = f"🟠 {line}"  # Orange warning
            
            lines.append(line)
            i += 1
    
    if len(normal_tests) > 15:
        lines.append(f"\n... and {len(normal_tests) - 15} more normal values")
    
    lines.append("</RESULTS>")
    
    # Raw JSON for precise parsing
    lines.append("")
    lines.append("<RAW_DATA>")
    lines.append(json.dumps(data, indent=2))
    lines.append("</RAW_DATA>")
    
    return "\n".join(lines)


def _is_critical_finding(test_name: str, value: str, flag: str) -> bool:
    """
    🔥 NEW: Determine if a finding is clinically critical (life-threatening)
    
    Returns True if this requires IMMEDIATE medical attention
    """
    name_lower = test_name.lower().replace(' ', '_').replace('-', '_')
    value_clean = re.sub(r'[^\d.]', '', str(value))
    
    try:
        val = float(value_clean) if value_clean else None
    except:
        val = None
    
    # === CRITICAL: Heart Rate / Ventricular Rate ===
    if any(kw in name_lower for kw in ['ventricular_rate', 'heart_rate', 'hr']):
        if val is not None and val < 50:  # Severe bradycardia
            return True
        if val is not None and val > 150:  # Severe tachycardia
            return True
    
    # === CRITICAL: Oxygen Saturation ===
    if 'spo2' in name_lower or 'oxygen_saturation' in name_lower:
        if val is not None and val < 90:  # Hypoxemia
            return True
    
    # === CRITICAL: Blood Glucose ===
    if any(kw in name_lower for kw in ['glucose', 'blood_sugar', 'fasting_glucose']):
        if val is not None and val < 40:  # Severe hypoglycemia
            return True
        if val is not None and val > 500:  # Severe hyperglycemia
            return True
    
    # === CRITICAL: Potassium (can cause arrhythmia) ===
    if 'potassium' in name_lower or 'k+' in name_lower:
        if val is not None and val < 2.5:  # Severe hypokalemia
            return True
        if val is not None and val > 7.0:  # Severe hyperkalemia
            return True
    
    # === CRITICAL: Hemoglobin (severe anemia) ===
    if any(kw in name_lower for kw in ['hemoglobin', 'hb', 'haemoglobin']):
        if val is not None and val < 7.0:  # Severe anemia
            return True
    
    # === CRITICAL: Platelets (bleeding risk) ===
    if 'platelet' in name_lower:
        if val is not None and val < 20:  # Thrombocytopenia crisis
            return True
        if val is not None and val > 1000:  # Thrombocytosis risk
            return True
    
    # === CRITICAL: ECG Intervals ===
    if 'pr_interval' in name_lower or 'pr' == name_lower:
        if val is not None and val > 300:  # High-grade AV block territory
            return True
    
    if 'qt_interval' in name_lower or 'qtc' in name_lower:
        if val is not None and val > 500:  # Dangerous QT prolongation
            return True
    
    # === CRITICAL: Atrial Pause ===
    if 'atrial_pause' in name_lower or 'pause' in name_lower:
        if val is not None and val >= 3.0:  # Symptomatic pause
            return True
    
    return False


def assess_clinical_urgency(data: list[dict]) -> dict:
    """
    🔥 NEW: Assess overall clinical urgency of the report
    
    Returns dict with:
    - level: 'CRITICAL' | 'WARNING' | 'NORMAL'
    - critical_count: int
    - warning_count: int
    - heart_rate: float or None
    - hr_status: str
    - has_av_block: bool
    - recommendations: list
    """
    
    result = {
        'level': 'NORMAL',
        'critical_count': 0,
        'warning_count': 0,
        'heart_rate': None,
        'hr_status': 'Normal',
        'has_av_block': False,
        'recommendations': []
    }
    
    for item in data:
        name = item.get('test', '').lower().replace(' ', '_')
        value_str = str(item.get('value', ''))
        flag = item.get('flag', '')
        
        # Clean numeric value
        value_clean = re.sub(r'[^\d.\-]', '', value_str)
        try:
            val = float(value_clean) if value_clean else None
        except:
            val = None
        
        # Check heart rate
        if any(kw in name for kw in ['ventricular_rate', 'heart_rate']):
            result['heart_rate'] = val
            if val is not None:
                if val < 50:
                    result['hr_status'] = 'SEVERE BRADYCARDIA'
                    result['level'] = 'CRITICAL'
                    result['critical_count'] += 1
                    result['recommendations'].append(
                        "🚨 EMERGENCY: Heart rate critically low (<50 bpm). "
                        "Risk of syncope (fainting). Immediate cardiology evaluation required."
                    )
                elif val < 60:
                    result['hr_status'] = 'Bradycardia'
                    result['warning_count'] += 1
                    if result['level'] != 'CRITICAL':
                        result['level'] = 'WARNING'
        
        # Check PR Interval (AV conduction)
        if 'pr_interval' in name or 'pr' == name.replace(' ', '_'):
            if val is not None and val > 250:
                result['has_av_block'] = True
                result['critical_count'] += 1
                if result['level'] != 'CRITICAL':
                    result['level'] = 'WARNING'
                result['recommendations'].append(
                    "⚠️ Prolonged PR interval suggests AV conduction block. "
                    "Requires cardiology workup."
                )
            elif val is not None and val > 200:
                result['warning_count'] += 1
                if result['level'] == 'NORMAL':
                    result['level'] = 'WARNING'
        
        # Check QRS duration
        if 'qrs_duration' in name:
            if val is not None and val > 140:
                result['warning_count'] += 1
                if result['level'] == 'NORMAL':
                    result['level'] = 'WARNING'
        
        # Check QT/QTc interval
        if 'qt_interval' in name or 'qtc' in name:
            if val is not None and val > 480:
                result['warning_count'] += 1
                if result['level'] == 'NORMAL':
                    result['level'] = 'WARNING'
        
        # Check general flags
        if flag in ['HIGH', 'LOW']:
            # Already counted above for specific critical checks
            if not _is_critical_finding(item['test'], value_str, flag):
                result['warning_count'] += 1
                if result['level'] == 'NORMAL':
                    result['level'] = 'INFO'
    
    return result


GROUNDED_SYSTEM_PROMPT = """You are a senior clinical laboratory interpretation expert with DEEP knowledge of ALL medical tests (hematology, biochemistry, immunology, endocrinology, urinalysis, lipid profiles, coagulation, toxicology, CARDIOLOGY/ECG, etc.).

⚕ IMPORTANT: You are analyzing REAL patient data that may contain LIFE-THREATENING findings.

═══════════════════════════════════════════════════════════
🚨 CLINICAL SAFETY RULES (FOLLOW STRICTLY):
═══════════════════════════════════════════════════════════

1. **USE ONLY THE DATA PROVIDED** - Do NOT invent values, ranges, or test results
2. **If a test is not in the data**, say "Not measured in this report"
3. **Reference the user's actual values** when explaining
4. **Do NOT diagnose** - say "suggests", "consistent with", "may indicate"
5. **FLAG DANGEROUS FINDINGS PROMINENTLY** at the TOP of your response:
   - Heart rate < 50 or > 150 bpm → 🔴 CRITICAL
   - SpO2 < 90% → 🔴 CRITICAL  
   - K+ < 2.5 or > 7.0 → 🔴 CRITICAL (arrhythmia risk)
   - Glucose < 40 or > 500 → 🔴 CRITICAL
   - Platelets < 20 or > 1000 → 🔴 CRITICAL
   - Hb < 7.0 → 🔴 CRITICAL
   - PR interval > 300ms → 🔴 CRITICAL (AV block)
   - QTc > 500ms → 🔴 CRITICAL (torsades risk)

6. **PRIORITIZE BY SEVERITY**: Order your response:
   Section 1: 🔴 CRITICAL FINDINGS (if any) - Put these FIRST with red flags
   Section 2: ⚠️ Significant Abnormalities
   Section 3: 🟡 Mild/Borderline Findings  
   Section 4: ✅ Normal Values (brief)
   
7. **For SUMMARY requests specifically**:
   - Start with: Overall status (1 sentence)
   - Then: Critical findings (numbered, with urgency icons)
   - Then: Other abnormalities
   - End with: Clear next steps
   - If CRITICAL findings exist: Use bold ⚠️ symbols and recommend immediate action

8. **End every response with**: 
   ⚕ *Consult your doctor immediately if you experience chest pain, shortness of breath, dizziness, or fainting.*

═══════════════════════════════════════════════════════════"""


def build_grounded_prompt(question: str, data_context: str) -> str:
    """
    Build prompt that forces LLM to use provided data + enforces urgency awareness.
    
    🔥 ENHANCED: Now detects summary requests and forces proper prioritization
    """
    
    q = question.lower().strip()
    
    # Detect question intent
    is_definition = any(kw in q for kw in ['explain all', 'define all', 'what are', 'tell me about', 'each test', 'meaning of', 'stand for'])
    is_abnormality = any(kw in q for kw in ['wrong', 'abnormal', 'concern', 'worry', 'problem', 'bad', 'issue', 'flagged', 'high', 'low', 'not normal'])
    is_health = any(kw in q for kw in ['healthy', 'normal', 'ok', 'fine', 'good', 'sick', 'ill', 'disease', 'overall', 'summary', 'assessment', 'summarise', 'summarize'])
    is_comparison = any(kw in q for kw in ['compare', 'difference', 'vs', 'versus', 'higher than', 'lower than', 'relationship', 'why is'])
    is_diet = any(kw in q for kw in ['eat', 'diet', 'food', 'nutrition', 'supplement', 'vitamin', 'lifestyle', 'avoid', 'take what'])
    is_simple = any(kw in q for kw in ["like i'm 5", "simple terms", "easy to understand", "plain english", "for a child", "eli5"])
    
    # Build instructions based on detected intent
    instructions = ""
    
    if is_health or is_definition:  # Summary requests get special treatment
        instructions = """TASK: Provide a comprehensive clinical assessment.
        
        ⚠️ STRUCTURE YOUR RESPONSE EXACTLY AS FOLLOWS:
        
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        🔴 SECTION 1: CRITICAL ALERTS (If any exist)
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        IF any parameter is marked as 🔴 CRITICAL above:
        • List EACH critical finding on its own line with 🔴 emoji
        • State the value and why it's dangerous
        • Use bold text: **IMMEDIATE ACTION REQUIRED**
        • Give 1-line plain-language explanation of risk
        
        Example format:
        🔴 **Heart Rate: 40 bpm** - Severely low (bradycardia)
           Risk: Can cause fainting, dizziness, cardiac arrest
           Action: Emergency cardiology consultation needed
        
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        ⚠️ SECTION 2: OTHER ABNORMALITIES
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        For each non-critical abnormal value:
        • Test name + Patient's value + Reference range
        • Brief 1-line meaning (what it indicates)
        • Possible causes (bulleted, max 3)
        • Urgency: Routine monitoring vs. Soon
        
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        ✅ SECTION 3: NORMAL VALUES (Brief)
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        • Group similar tests together
        • One-liner per category: "All liver enzymes: Normal"
        • Don't list every single normal value unless asked
        
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        🎯 SECTION 4: OVERALL ASSESSMENT & NEXT STEPS
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        **Overall Status:** [One clear sentence - e.g., "Report shows bradycardia requiring urgent cardiac evaluation"]
        
        **Key Concerns Ranked:**
        1. [Most dangerous finding]
        2. [Second most concerning]
        3. [etc.]
        
        **Recommended Actions:**
        🔴 If critical: "Seek emergency/urgent care within 24 hours"
        🟡 If warning: "Schedule follow-up with primary care/cardiologist within 1 week"
        🟢 If minor: "Continue routine monitoring"
        
        **What This Report Cannot Show:**
        [Limitations - e.g., "Cannot diagnose cause of abnormality without clinical correlation"]
        
        ⚕ *This is automated analysis only. Consult healthcare provider immediately for any symptoms.*"""
    
    elif is_abnormality:
        instructions = """TASK: Analyze ONLY abnormal values (marked HIGH or LOW).
                        
                        For each abnormal finding:
                        1. **Test & Value**: What it is + patient's number
                        2. **Meaning**: Plain English
                        3. **Possible causes**: Top 3 common reasons (bulleted)
                        4. **Urgency Level**: 
                           🔴 CRITICAL (immediate danger)
                           🟡 WARNING (monitor closely)
                           🟢 ROUTINE (follow-up needed)
                        
                        Then give:
                        📋 PATTERN ANALYSIS: [If multiple abnormalities suggest a syndrome]
                        🎯 NEXT STEPS: [Bulleted action items ranked by urgency]"""
    
    elif is_diet:
        instructions = """TASK: Provide diet/lifestyle advice tied SPECIFICALLY to abnormal values found.
                        For each relevant abnormal value:
                        🍎 **[Test]: [Value]**
                        • Connection to nutrition
                        ✓ Eat: [2-3 foods]
                        ✗ Limit: [2-3 items]
                        ⏱️ Timeline: [When changes visible]
                        🥗 General wellness tips: [2-3 broad recommendations]
                        ⚕️ Note: Diet supports but doesn't replace treatment."""
    
    elif is_simple:
        instructions = """TASK: Explain like the patient is 5 years old.
                        Rules:
                        • Use analogies (blood cells = tiny trucks, body = city)
                        • Max 2 sentences per concept
                        • NO jargon without simple explanation
                        • Reassuring tone
                        • One takeaway message"""
    
    else:
        instructions = """TASK: Answer the user's specific question using ONLY the lab data provided.
                        Guidelines:
                        • Reference actual values from the data
                        • Use your expertise to interpret meaning
                        • Be concise but thorough
                        • Format for readability
                        • Include disclaimer at end"""
    
    # Assemble final prompt
    prompt = f"""{GROUNDED_SYSTEM_PROMPT}

{data_context}

═══════════════════════════════════════════════════════════════════
USER QUESTION: "{question}"
═══════════════════════════════════════════════════════════════════

{instructions}

Now respond based on the data above:"""
    
    return prompt


# ════════════════════════════════════════════════════════════════════
# CONVENIENCE WRAPPER (Easy integration)
# ════════════════════════════════════════════════════════════════════

def process_lab_query(question: str, lab_data_json: str) -> dict:
    """
    Main function to call from your API endpoint.
    
    Usage:
        result = process_lab_query("explain all tests", json_string_from_table_extractor)
        print(result['response'])
    """
    from datetime import datetime
    
    try:
        if isinstance(lab_data_json, str):
            data = json.loads(lab_data_json)
        else:
            data = lab_data_json
    except:
        return {'error': 'Invalid data format', 'response': ''}
    
    if not data:
        return {'error': 'No data', 'response': '⚠️ No lab data available'}
    
    # 🔥 NEW: Assess urgency before generating response
    urgency = assess_clinical_urgency(data)
    
    response_text = ask_about_lab_report(question, data)
    
    return {
        'response': response_text,
        'question': question,
        'tests_count': len(data),
        'abnormal_count': len([t for t in data if t.get('flag')]),
        'urgency_level': urgency['level'],  # 🔥 NEW
        'critical_count': urgency['critical_count'],  # 🔥 NEW
        'timestamp': datetime.now().isoformat(),
    }
    