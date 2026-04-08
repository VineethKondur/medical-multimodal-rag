"""
Graph Router - Routes graphical pages to appropriate analyzers.

This module:
1. Receives pages flagged as 'graphical' by pdf_processor.classify_pages()
2. Determines if it's ECG, Chart, or Other
3. Calls the right analyzer (signal_analyzer or chart_interpreter)
4. Returns structured insights

🔥 FIXED: Now extracts COMPLETE ECG data including:
   - All measurements from tables
   - Physiologist's findings
   - Cardiology advice
   - Proper reference ranges
   - Clinical urgency classification

NO ML training. Deterministic routing only.
"""

import fitz
import os
import json
import re


def analyze_graphical_pages(file_path, pages_info):
    """
    Main entry point for analyzing graphical/chart pages.
    
    Args:
        file_path: Path to PDF file
        pages_info: List from pdf_processor.classify_pages() containing
                   only unsafe/graphical pages
    
    Returns:
        dict: {
            'ecg_analysis': {...} or None,
            'chart_analysis': [{...}, ...] or None,
            'total_pages_analyzed': int,
            'errors': [...]
        }
    """
    
    results = {
        'ecg_analysis': None,
        'chart_analysis': [],
        'total_pages_analyzed': 0,
        'errors': [],
        'skipped_pages': []
    }
    
    # Filter to only get unsafe pages
    graphical_pages = [p for p in pages_info if not p['is_safe']]
    
    if not graphical_pages:
        print("   📈 No graphical pages to analyze")
        return results
    
    print(f"\n{'='*60}")
    print(f"📊 GRAPH ANALYZER: Processing {len(graphical_pages)} graphical page(s)")
    print(f"{'='*60}\n")
    
    for page_info in graphical_pages:
        page_num = page_info['page_num']
        reason = page_info.get('reason', '')
        
        print(f"   📍 Page {page_num}: {reason}")
        
        try:
            # Determine page type and route appropriately
            page_type = _classify_graph_type(page_info, file_path)
            
            if page_type == 'ECG':
                print(f"      ↳ Routing to Signal Analyzer (ECG)...")
                ecg_result = _analyze_ecg_page(file_path, page_num)
                
                if ecg_result:
                    results['ecg_analysis'] = ecg_result
                    results['total_pages_analyzed'] += 1
                    print(f"      ✅ ECG analysis complete")
                    
                    # Log critical findings
                    if ecg_result.get('analysis', {}).get('observations'):
                        crit_count = sum(1 for obs in ecg_result['analysis']['observations'] 
                                       if 'bradycardia' in obs.lower() or 'prolonged' in obs.lower())
                        if crit_count > 0:
                            print(f"      🚨 Found {crit_count} critical observation(s)!")
                else:
                    results['skipped_pages'].append({
                        'page': page_num,
                        'reason': 'ECG analysis returned no data'
                    })
                    
            elif page_type == 'CHART':
                print(f"      ↳ Routing to Chart Interpreter...")
                chart_result = _analyze_chart_page(file_path, page_num)
                
                if chart_result:
                    results['chart_analysis'].append(chart_result)
                    results['total_pages_analyzed'] += 1
                    print(f"      ✅ Chart analysis complete")
                else:
                    results['skipped_pages'].append({
                        'page': page_num,
                        'reason': 'Chart analysis returned no data'
                    })
                    
            else:
                # Unknown graph type - try both or skip
                print(f"      ⚠️ Unknown graph type, attempting ECG analysis...")
                ecg_result = _analyze_ecg_page(file_path, page_num)
                
                if ecg_result:
                    results['ecg_analysis'] = ecg_result
                    results['total_pages_analyzed'] += 1
                else:
                    print(f"      ⏭️ Skipping page {page_num} (cannot analyze)")
                    results['skipped_pages'].append({
                        'page': page_num,
                        'reason': f'Unrecognized graph type: {page_type}'
                    })
                    
        except Exception as e:
            error_msg = f"Page {page_num}: {str(e)}"
            print(f"      ❌ ERROR: {error_msg}")
            results['errors'].append(error_msg)
    
    # Summary
    print(f"\n   📊 Graph Analysis Summary:")
    print(f"      - ECG analyses: {1 if results['ecg_analysis'] else 0}")
    print(f"      - Chart analyses: {len(results['chart_analysis'])}")
    print(f"      - Total analyzed: {results['total_pages_analyzed']}")
    print(f"      - Skipped: {len(results['skipped_pages'])}")
    print(f"      - Errors: {len(results['errors'])}")
    print(f"{'='*60}\n")
    
    return results


def _classify_graph_type(page_info, file_path):
    """
    Determine if a graphical page is ECG, Chart, or Other.
    
    Uses heuristics from page_info + optional text analysis.
    
    Returns:
        str: One of 'ECG', 'CHART', or 'UNKNOWN'
    """
    reason = page_info.get('reason', '').lower()
    
    # Strong ECG indicators in reason string
    ecg_keywords = ['ecg', 'electrocardiogram', 'waveform', 'lead ', 
                   'qrs', 'p-wave', 't-wave', 'sinus rhythm',
                   '12-lead', 'cardiac']
    
    ecg_matches = sum(1 for kw in ecg_keywords if kw in reason)
    
    if ecg_matches >= 2:
        return 'ECG'
    
    # Strong chart indicators
    chart_keywords = ['chart', 'graph', 'plot', 'trend', 'visualization',
                     'line chart', 'bar chart', 'pie chart']
    
    chart_matches = sum(1 for kw in chart_keywords if kw in reason)
    
    if chart_matches >= 1:
        return 'CHART'
    
    # If still unknown, check actual page text
    try:
        doc = fitz.open(file_path)
        page = doc[page_info['page_num'] - 1]
        text = page.get_text().lower()
        doc.close()
        
        # Re-check with full text
        text_ecg_matches = sum(1 for kw in ecg_keywords if kw in text)
        text_chart_matches = sum(1 for kw in chart_keywords if kw in text)
        
        if text_ecg_matches >= 3:
            return 'ECG'
        elif text_chart_matches >= 2:
            return 'CHART'
        elif 'ecg' in text or 'electrocardi' in text:
            return 'ECG'  # Default to ECG if any mention
            
    except Exception:
        pass
    
    return 'UNKNOWN'


def _analyze_ecg_page(file_path, page_num):
    """
    🔥 FIXED: Comprehensive ECG data extraction from report pages.
    
    Now extracts:
    1. Measurement History table (PR, QRS, QT, QTc, etc.)
    2. Physiologist's qualitative findings
    3. Cardiology advice/conclusions
    4. Proper reference ranges for ALL parameters
    5. Clinical urgency classification
    
    Args:
        file_path: Path to PDF
        page_num: Page number (1-indexed)
    
    Returns:
        dict: Complete ECG analysis with measurements + interpretations
    """
    try:
        doc = fitz.open(file_path)
        page = doc[page_num - 1]
        text = page.get_text()
        doc.close()
        
        # 🔥 STRATEGY: Multi-layered extraction
        measurements = []
        physio_findings = []
        cardiology_advice = []
        
        # ===== LAYER 1: Extract Numerical Measurements =====
        measurements = _extract_all_ecg_measurements(text)
        print(f"         Found {len(measurements)} numerical measurements")
        
        # ===== LAYER 2: Extract Physiologist's Qualitative Findings =====
        physio_findings = _extract_physiologist_findings(text)
        if physio_findings:
            print(f"         Found {len(physio_findings)} physiologist findings")
        
        # ===== LAYER 3: Extract Cardiology Advice/Conclusions =====
        cardiology_advice = _extract_cardiology_advice(text)
        if cardiology_advice:
            print(f"         Found cardiology advice/conclusions")
        
        if not measurements and not physio_findings:
            return None
        
        # Build comprehensive result
        result = {
            'type': 'comprehensive_ecg_analysis',
            'source': 'text_extraction',
            'page': page_num,
            'measurements': measurements,
            'physiologist_findings': physio_findings,
            'cardiology_advice': cardiology_advice,
            'analysis': _generate_comprehensive_ecg_summary(measurements, physio_findings, cardiology_advice)
        }
        
        return result
        
    except ImportError:
        print("         ⚠️ signal_analyzer not available")
        return None
        
    except Exception as e:
        print(f"         ❌ ECG analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def _extract_all_ecg_measurements(text):
    """
    FIXED v4.0: Correctly handles pattern tuples with variable length.
    Prevents: ValueError: too many values to unpack (expected 4)
    
    Each pattern tuple format: (regex_pattern, display_name, unit, normal_range [, optional_extra])
    Now safely handles 4-tuple, 5-tuple, or any length ≥ 4.
    """
    measurements = {}
    
    # Define patterns as tuples
    # Format: (pattern, name, unit, ref_range) 
    patterns = [
        (r'Ventricular.*?Rate[:\s]*(\d+)\s*bpm', 'Ventricular Rate', 'bpm', '60-100'),
        (r'Atrial.*?Rate[:\s]*(\d+)\s*bpm', 'Atrial Rate', 'bpm', '60-100'),
        (r'PR\s*Interval[:\s]*([\d.]+)\s*ms', 'PR Interval', 'ms', '120-200'),
        (r'PR\s*interval.*?Prolonged', 'PR Interval', 'ms', '>200'),
        (r'QRS\s*Duration[:\s]*(\d+)\s*ms', 'QRS Duration', 'ms', '80-120'),
        (r'QT\s*Interval[:\s]*(\d+)\s*ms', 'QT Interval', 'ms', '360-460'),
        (r'QTc\s*Interval[:\s]*([\d.]+)\s*ms', 'QTc Interval', 'ms', '370-450'),
        (r'P.*?Axis[:\s]*([-\d]+)\s*°?', 'P Axis', 'degrees', '0 to +90'),
        (r'QRS\s*Axis[:\s]*([-\d]+)\s*°?', 'QRS Axis', 'degrees', '-30 to +90'),
        (r'T.*?Axis[:\s]*([-\d]+)\s*°?', 'T Axis', 'degrees', '-30 to +90'),
        
        # Measurement History table patterns (from the ECG report image)
        (r'Recorded[\s\S]*?PR[:\s]*(\d+)', 'PR (History)', 'ms', '120-200'),
        (r'Recorded[\s\S]*?QRS[:\s]*(\d+)', 'QRS (History)', 'ms', '80-120'),
        (r'Recorded[\s\S]*?QTc[:\s]*(\d+)', 'QTc (History)', 'ms', '370-450'),
        
        # Text-based findings (not numeric)
        (r'(Sinus Rhythm Present[:\s]*)Yes', 'Sinus Rhythm', '', 'Present'),
        (r'(Sinus Rhythm Present[:\s]*)No', 'Sinus Rhythm', '', 'Absent'),
        (r'(Profound Bradycardia)', 'Rhythm Finding', '', 'Profound Bradycardia'),
        (r'(Prolongedly prolonged)', 'PR Status', '', 'Prolonged'),
        (r'(Normal)', 'General Status', '', 'Normal'),
        (r'(Within normal limits)', 'General Status', '', 'Normal'),
        (r'(2nd degree AV block)', 'Conduction Abnormality', '', '2nd Degree AV Block'),
        (r'(Mobitz [IVX]+\s*\d?)', 'Block Type', '', 'Mobitz'),
        (r'(Red)\s*(?:Risk)?$', 'Risk Level', '', 'Red'),
        (r'(Good)\s*(?:Quality)?$', 'ECG Quality', '', 'Good'),
    ]
    
    for pattern_tuple in patterns:
        # 🔥 FIX: Safely handle tuples of any length ≥ 4
        try:
            if len(pattern_tuple) < 4:
                print(f"      ⚠️ Skipping short pattern tuple (length {len(pattern_tuple)})")
                continue
                
            pattern = pattern_tuple[0]
            name = pattern_tuple[1]
            unit = pattern_tuple[2]
            ref_range = pattern_tuple[3]
            # Ignore any extra fields beyond index 3
            
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                try:
                    value = match.group(1) if match.lastindex and match.lastindex >= 1 else match.group(0)
                    measurements[name] = {
                        'value': value,
                        'unit': unit,
                        'ref_range': ref_range,
                        'raw_match': match.group(0)[:80]
                    }
                except (IndexError, Exception) as inner_err:
                    measurements[name] = {
                        'value': 'Detected',
                        'unit': unit,
                        'ref_range': ref_range,
                        'raw_match': match.group(0)[:80] if match.groups() else 'Match found'
                    }
                    
        except Exception as tuple_err:
            print(f"      ⚠️ Pattern processing error: {tuple_err}")
            continue
    
    return measurements



def _analyze_ecg_page(page_text, page_num):
    """Analyze an ECG page for measurements and findings."""
    
    result = {
        'page': page_num,
        'findings': [],
        'measurements': {},
        'rhythm': None,
        'risk_level': None
    }
    
    try:
        # Extract measurements (using fixed function)
        result['measurements'] = _extract_all_ecg_measurements(page_text)
        
        # Detect rhythm
        rhythm_patterns = [
            (r'Sinus\s*Rhythm', 'Sinus Rhythm', 'normal'),
            (r'Atrial\s+Fibrillation', 'Atrial Fibrillation', 'abnormal'),
            (r'Atrial\s*Flutter', 'Atrial Flutter', 'abnormal'),
            (r'Bradycardia', 'Bradycardia', 'abnormal'),
            (r'Tachycardia', 'Tachycardia', 'abnormal'),
        ]
        
        for pattern, name, status in rhythm_patterns:
            if re.search(pattern, page_text, re.IGNORECASE):
                result['rhythm'] = {'name': name, 'status': status}
                break
        
        # Detect risk level
        if re.search(r'\bRed\b', page_text):
            result['risk_level'] = 'Red'
        elif re.search(r'\bAmber\b|\bYellow\b', page_text, re.IGNORECASE):
            result['risk_level'] = 'Amber'
        elif re.search(r'\bGreen\b', page_text, re.IGNORECASE):
            result['risk_level'] = 'Green'
            
        # Extract key findings
        finding_patterns = [
            r'(Profound Bradycardia)',
            r'(Prolonged PR interval)',
            r'(2nd degree AV block)',
            r'(Mobitz [IVX]+)',
            r'(Normal sinus rhythm)',
            r'(Within normal limits)',
        ]
        
        for pattern in finding_patterns:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                result['findings'].append(match.group(1))
                
    except Exception as e:
        print(f"      ❌ Error analyzing ECG page {page_num}: {e}")
        import traceback
        traceback.print_exc()
    
    return result


def _is_value_in_range(value, ref_range):
    """
    Check if a value falls within acceptable reference range.
    
    Args:
        value: float - The measured value
        ref_range: tuple (min_normal, max_normal) or (None, None)
    
    Returns:
        bool: True if normal, False if abnormal, None if cannot determine
    """
    if ref_range == (None, None):
        return None
    
    min_val, max_val = ref_range
    
    if min_val is not None and max_val is not None:
        return min_val <= value <= max_val
    elif min_val is not None:
        return value >= min_val  # Only lower bound (e.g., ">X")
    elif max_val is not None:
        return value <= max_val  # Only upper bound (e.g., "<X")
    
    return None


def _get_measurement_significance(name, value, unit):
    """
    🔥 NEW: Generate clinical significance text for each measurement.
    
    Provides plain-language interpretation of what abnormal values mean.
    
    Args:
        name: Measurement name (e.g., 'pr_interval')
        value: Numeric value
        unit: Unit string (e.g., 'ms')
    
    Returns:
        str: Clinical significance description
    """
    name_lower = name.lower().replace(' ', '_')
    
    significance_map = {
        'ventricular_rate': {
            (None, 50): "🔴 SEVERE BRADYCARDIA - Heart dangerously slow",
            (50, 60): "⚠️ Bradycardia - Below normal resting rate",
            (60, 100): "✅ Normal resting heart rate",
            (100, 120): "⚠️ Tachycardia - Elevated rate",
            (120, 150): "⚠️ Significant tachycardia",
            (150, None): "🔴 SEVERE TACHYCARDIA - Dangerously fast"
        },
        'pr_interval': {
            (None, 120): "✅ Normal PR interval",
            (120, 200): "✅ Borderline prolonged",
            (200, 300): "⚠️ Prolonged - Suggests 1st degree AV block",
            (300, None): "🔴 CRITICALLY PROLONGED - High-grade AV block likely"
        },
        'qrs_duration': {
            (None, 100): "✅ Narrow QRS complex",
            (100, 120): "✅ Normal QRS duration",
            (120, 140): "⚠️ Wide QRS - Possible bundle branch block",
            (140, None): "🔴 Very wide - Serious conduction abnormality"
        },
        'qt_interval': {
            (None, 400): "✅ Normal QT interval",
            (400, 460): "✅ Borderline",
            (460, 500): "⚠️ Prolonged - Monitor medications",
            (500, None): "🔴 Dangerously prolonged - Torsades de Pointes risk"
        },
        'qtc_interval': {
            (None, 370): "✅ Normal QTc (corrected QT)",
            (370, 450): "✅ Normal QTc",
            (450, 470): "⚠️ Borderline QTc prolongation",
            (470, 500): "⚠️ Prolonged QTc - Risk factor",
            (500, None): "🔴 Significantly prolonged - Arrhythmia risk"
        },
        'atrial_pause': {
            (None, 0.5): "✅ Brief pause (may be benign)",
            (0.5, 2.0): "⚠️ Prolonged pause - May be symptomatic",
            (2.0, 3.0): "⚠️ Significantly long pause",
            (3.0, None): "🔴 Dangerously long pause - Syncope/fainting risk"
        },
    }
    
    # Look up significance
    for (range_tuple), text in significance_map.items():
        if name_lower in significance_map:
            min_val, max_val = range_tuple
            
            if min_val is None and max_val is None:
                return text
            elif min_val is not None and max_val is not None:
                if min_val <= value <= max_val:
                    return text
            elif min_val is not None and value < min_val:
                # Below range (e.g., HR < 60)
                # Find matching "below normal" entry
                for (lo, hi), sig_text in list(significance_map[name_lower].items()):
                    if lo is not None and value < lo:
                        return sig_text
                return text
            elif max_val is not None and value > max_val:
                # Above range (e.g., HR > 100)
                for (lo, hi), sig_text in list(significance_map[name_lower].items()):
                    if hi is not None and value > hi:
                        return sig_text
                return text
    
    return ""


def _extract_physiologist_findings(text):
    """
    🔥 NEW: Extract qualitative findings from "Physiologist's Report" section.
    
    Many ECG reports have a structured section like:
    - ECG Quality: Good/Fair/Poor
    - Ventricular Rate: Normal/Bradycardia/Tachycardia
    - PR Interval: Normal/Prolonged
    - etc.
    
    Args:
        text: Full page text
    
    Returns:
        list: dicts with finding name, status, details
    """
    
    findings = []
    
    # Common patterns in physiologist reports
    patterns = [
        # Quality assessments
        (r'(?:ECG\s+Quality|Quality)\s*[:\s]*(Good|Fair|Poor|Excellent)', 'quality'),
        
        # Rate assessments
        (r'(?:Ventricular\s+Rate)\s*[:\s]*(Normal|Bradycardia|Tachycardia|Profoundly\s+\w+)', 'ventricular_rate_status'),
        (r'(?:Atrial\s+Rate)\s*[:\s]*(Normal|Bradycardia|Tachycardia)', 'atrial_rate_status'),
        
        # Interval assessments
        (r'(?:PR\s*(?:Interval)?)\s*[:\s]*(Normal|Prolonged|Prolongely\s+prolonged|Short|Borderline)', 'pr_interval_status'),
        (r'(?:QRS\s*(?:Duration)?)\s*[:\s]*(Normal|Wide|Prolonged|Short|Borderline)', 'qrs_duration_status'),
        (r'(?:QT\s*(?:Interval)?)\s*[:\s]*(Normal|Prolonged|Borderline|Long)', 'qt_interval_status'),
        
        # Rhythm assessments
        (r'(?:Rhythm|Rhythm\s+Present)\s*[:\s]*(Normal|Irregular|Regular|Irregular|Sinus)', 'rhythm_status'),
        
        # Morphology
        (r'(?:P\s+Wave|Morphology)\s*[:\s]*(Normal|Abnormal|Notched|Bifid)', 'p_wave_status'),
        (r'(?:ST\s+Segment)\s*[:\s]*(Normal|Depressed|Elevated|Deviation)', 'st_segment_status'),
        (r'((?:T\s+Wave|Morphology)\s*[:\s]*(Normal|Inverted|Tall|Peaked|Flat)', 't_wave_status'),
        
        # Conduction
        (r'(?:AV\s+Conduction)\s*[:\s]*(Normal|Abnormal|Delayed|Block|2nd\s+degree|1st\s+degree)', 'av_conduction_status'),
        
        # Special findings
        (r'(?:Other\s+Rhythm|Additional\s+finding)\s*[:\s]*(None|Present|Yes|No|\w[\s\w]+)', 'other_rhythm'),
        (r'(?:Atrial\s+Pause)\s*[:\s]*(None|Present|Yes|No|More\s+than\s+\d+\s*sec)', 'atrial_pause_present'),
    ]
    
    for pattern, field_name in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            status = match.group(1).strip()
            
            # Skip if just says "Normal" (we'll capture actual values elsewhere)
            if status.lower() == 'normal':
                continue
            
            findings.append({
                'field': field_name.replace('_', ' ').title(),
                'status': status.title(),
                'raw_text': match.group(0).strip(),
                'is_abnormal': status.lower() not in ['normal', 'none', 'within normal limits']
            })
    
    return findings


def _extract_cardiology_advice(text):
    """
    🔥 NEW: Extract cardiologist's conclusions and advice.
    
    Looks for sections like:
    - "Cardiology Advice:"
    - "Impression:"
    - "Conclusion:"
    - "Recommendation:"
    
    These often contain the MOST clinically important information!
    
    Args:
        text: Full page text
    
    Returns:
        list: dicts with advice/recommendation text
    """
    
    advice_items = []
    
    # Pattern to find advice/conclusion sections
    # Look for multi-line text after these headers
    advice_patterns = [
        r'(?:Cardiology\s+Advice|Advice|Recommendation|Conclusion|Impression|Interpretation)[\s:]*\n([^\n]+(?:\n[^\n]+){0,10})',
        r'(?:Suggest|Recommend|Advise|Consider|Refer)\s+(?:urgent\s+)?(?:referral|follow.?up|evaluation|review|consultation)[^\n]*',
    ]
    
    for pattern in advice_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
        for match in matches:
            advice_text = match.strip()
            if len(advice_text) > 20:  # Substantial text, not just a word
                advice_items.append({
                    'type': 'recommendation',
                    'text': advice_text,
                    'is_urgent': any(kw in advice_text.lower() for kw in [
                        'urgent', 'emergency', 'immediate', 'asap', '24 hour', 
                        '48 hour', 'soon', 'promptly', 'today'
                    ])
                })
    
    # Also look for specific dangerous phrases
    dangerous_phrases = [
        r'(?:type\s+2|second\s*degree|mobitz)\s+(?:heart\s+block|av\s*block)',
        r'(?:pacemaker|implant)',
        r'(?:urgent|emergency|immediate)',
        r'(?:hospitaliz|admit)',
        r'(?:syncope|fainting|collapse|arrest)',
        r'(?:arrhythmi[a]|dysrhythm)',
    ]
    
    for pattern in dangerous_phrases:
        if re.search(pattern, text, re.IGNORECASE):
            match = re.search(pattern, text, re.IGNORECASE)
            advice_items.insert(0, {  # Insert at beginning (most important!)
                'type': 'critical_warning',
                'text': match.group(0).strip(),
                'is_urgent': True
            })
            break  # Only need one match to know it's critical
    
    return advice_items


def _generate_comprehensive_ecg_summary(measurements, physio_findings, cardiology_advice):
    """
    🔥 FIXED: Generate comprehensive ECG summary with proper prioritization.
    
    Now produces output suitable for clinical decision-making.
    
    Args:
        measurements: List of numerical measurements
        physio_findings: List of qualitative findings
        cardiology_advice: List of recommendations
    
    Returns:
        dict: Complete analysis with observations + clinical guidance
    """
    
    observations = []
    urgency_level = 'normal'
    critical_flags = []
    
    # Convert measurements to dict for easy lookup
    meas_dict = {}
    for m in measurements:
        key = m['name'].lower().replace(' ', '_')
        meas_dict[key] = m
    
    # ================================================================
    # SECTION 1: Vital Signs (ALWAYS check these first!)
    # ================================================================
    
    vr = meas_dict.get('ventricular_rate', {}).get('value')
    ar = meas_dict.get('atrial_rate', {}).get('value')
    hr = vr or ar  # Use ventricular if available (more reliable)
    
    if hr is not None:
        if hr < 50:
            observations.append(f"🔴 **HEART RATE: {hr} bpm** - SEVERELY LOW (Profound Bradycardia)")
            observations.append("   Risk: Can cause dizziness, fatigue, syncope (fainting)")
            observations.append("   Causes: Medication effect, sick sinus syndrome, hypothyroidism, AV block, high-level athletics")
            urgency_level = 'critical'
            critical_flags.append('bradycardia')
        elif hr < 60:
            observations.append(f"⚠️ **HEART RATE: {hr} bpm** - Low (Bradycardia)")
            observations.append("   Usually benign if asymptomatic; monitor symptoms")
            if urgency_level == 'normal':
                urgency_level = 'warning'
        elif hr > 100:
            observations.append(f"⚠️ **HEART RATE: {hr} bpm** - Elevated (Tachycardia)")
            if urgency_level == 'normal':
                urgency_level = 'info'
        else:
            observations.append(f"✅ **HEART RATE: {hr} bpm** - Within normal range (60-100)")
    
    # ================================================================
    # SECTION 2: Conduction System (PR, QRS, QT)
    # ================================================================
    
    pr = meas_dict.get('pr_interval', {}).get('value')
    if pr is not None:
        if pr > 300:
            observations.append(f"🔴 **PR INTERVAL: {pr} ms** - CRITICALLY PROLONGED (>300ms)")
            observations.append("   Indicates: High-grade AV conduction delay")
            observations.append("   Differential: 2nd degree AV block Type II, hyperkalemia, drugs (beta-blockers, digoxin)")
            observations.append("   ⚠️ This explains the bradycardia!")
            urgency_level = 'critical'
            critical_flags.append('av_block')
        elif pr > 200:
            observations.append(f"⚠️ **PR INTERVAL: {pr} ms** - Prolonged (>200ms)")
            observations.append("   Indicates: 1st degree AV block or delayed conduction")
            if urgency_level != 'critical':
                urgency_level = 'warning'
            critical_flags.append('possible_av_block')
        else:
            observations.append(f"✅ **PR INTERVAL: {pr} ms** - Normal (<200ms)")
    
    qrs = meas_dict.get('qrs_duration', {}).get('value')
    if qrs is not None:
        if qrs > 140:
            observations.append(f"⚠️ **QRS DURATION: {qrs} ms** - Wide (>120ms)")
            observations.append("   Indicates: Bundle branch block, ventricular pacing, or hypertrophy")
            if urgency_level == 'normal':
                urgency_level = 'warning'
        else:
            observations.append(f"✅ **QRS DURATION: {qrs} ms** - Normal (<120ms)")
    
    qt = meas_dict.get('qt_interval', {}).get('value')
    qtc = meas_dict.get('qtc_interval', {}).get('value')
    
    qt_to_use = qtc or qt  # Prefer QTc (corrected for heart rate)
    
    if qt_to_use is not None:
        if qt_to_use > 500:
            observations.append(f"🔴 **QT/QTc INTERVAL: {qt_to_use} ms** - DANGEROUSLY PROLONGED")
            observations.append("   Risk: Torsades de Pointes (fatal arrhythmia)")
            observations.append("   Causes: Electrolyte imbalance, certain medications (antidepressants, antiemetics)")
            if urgency_level != 'critical':
                urgency_level = 'warning'
        elif qt_to_use > 470:
            observations.append(f"⚠️ **QT/QTc INTERVAL: {qt_to_use} ms** - Prolonged")
            observations.append("   Review medications for QT-prolonging agents")
            if urgency_level == 'normal':
                urgency_level = 'info'
        else:
            observations.append(f"✅ **QT/QTc INTERVAL: {qt_to_use} ms** - Normal")
    
    # ================================================================
    # SECTION 3: Atrial Activity
    # ================================================================
    
    ap = meas_dict.get('atrial_pause', {}).get('value')
    if ap is not None:
        if ap >= 3.0:
            observations.append(f"🔴 **ATRIAL PAUSE: {ap} seconds** - SYMPTOMATIC")
            observations.append("   Risk: Can cause lightheadedness, presyncope, syncope")
            observations.append("   Cause: Sick sinus syndrome, vagotonic episodes, SA block")
            if urgency_level != 'critical':
                urgency_level = 'warning'
        elif ap >= 2.0:
            observations.append(f"⚠️ **ATRIAL PAUSE: {ap} seconds** - Prolonged")
            observations.append("   May be symptomatic; warrants Holter monitoring")
            if urgency_level == 'normal':
                urgency_level = 'info'
        else:
            observations.append(f"✅ **ATRIAL PAUSE: {ap} seconds** - Acceptable (<2s)")
    
    # ================================================================
    # SECTION 4: Physiologist's Qualitative Findings
    # ================================================================
    
    if physio_findings:
        abnormal_physio = [f for f in physio_findings if f.get('is_abnormal')]
        
        if abnormal_physio:
            observations.append("\n--- Physiologist's Notes ---")
            for finding in abnormal_physio[:8]:  # Top 8 max
                icon = "⚠️" if finding.get('is_urgent') else "•"
                observations.append(f"{icon} **{finding['field']}**: {finding['status']}")
    
    # ================================================================
    # SECTION 5: Cardiologist's Recommendations
    # ================================================================
    
    if cardiology_advice:
        urgent_advice = [a for a in cardiology_advice if a.get('is_urgent')]
        
        if urgent_advice:
            observations.append("\n--- ⚠️ CARDIOLOGIST'S ADVICE ---")
            for advice in urgent_advice[:3]:  # Top 3 most important
                observations.append(f"🔴 **RECOMMENDATION**: {advice['text']}")
            
            # Add generic follow-up if not already critical
            if urgency_level != 'critical':
                observations.append("\n⚕ *Seek cardiology evaluation promptly*")
        else:
            # Even non-urgent advice is worth noting
            if cardiology_advice:
                observations.append("\n--- Additional Notes ---")
                for advice in cardiology_advice[:2]:
                    observations.append(f"💡 {advice['text']}")
    
    # ================================================================
    # FINAL: Overall Assessment & Next Steps
    # ================================================================
    
    # Build final summary
    summary_parts = []
    
    if urgency_level == 'critical':
        summary_parts.append("🔴 **OVERALL: CRITICAL ABNORMALITIES DETECTED**")
        if 'bradycardia' in critical_flags:
            summary_parts.append("Primary Issue: Profound bradycardia with conduction system disease")
        if 'av_block' in critical_flags:
            summary_parts.append("Conduction Problem: AV block causing symptomatic pauses")
        summary_parts.append("Action: URGENT cardiology referral (24-48 hours)")
        summary_parts.append("Avoid: Beta-blockers, calcium channel blockers, digoxin until evaluated")
        
    elif urgency_level == 'warning':
        summary_parts.append("⚠️ **OVERALL: ABNORMALITIES REQUIRING ATTENTION**")
        summary_parts.append("Follow-up: Schedule cardiology/electrophysiology review")
        
    else:
        summary_parts.append("✅ **OVERALL: NO CRITICAL ABNORMALITIES**")
        summary_parts.append("Routine follow-up with primary care provider recommended")
    
    return {
        "summary": "\n".join(summary_parts),
        "observations": observations,
        "measurement_count": len(measurements),
        "urgency_level": urgency_level,
        "critical_flags": critical_flags,
        "has_abnormalities": urgency_level != 'normal'
    }


def _analyze_chart_page(file_path, page_num):
    """
    Analyze a non-ECG chart page (line charts, bar charts, etc.)
    
    For now, extracts available metadata about the chart.
    Full implementation would require image recognition to extract
    data points from the chart graphic itself.
    
    Args:
        file_path: Path to PDF
        page_num: Page number (1-inch)
    
    Returns:
        dict: Chart analysis results or None
    """
    try:
        from .chart_interpreter import interpret_chart
        
        doc = fitz.open(file_path)
        page = doc[page_num - 1]
        text = page.get_text()
        doc.close()
        
        # Extract chart metadata from surrounding text
        chart_info = _extract_chart_metadata(text, page_num)
        
        if not chart_info:
            return None
        
        # If we had structured data extraction, would call:
        # result = interpret_chart(structured_chart_data)
        # return result
        
        # For now, return what we can extract
        return {
            'type': 'chart_metadata',
            'source': 'text_extraction',
            'page': page_num,
            'info': chart_info,
            'note': 'Full chart data extraction requires image processing (future enhancement)'
        }
        
    except ImportError:
        print("         ⚠️ chart_interpreter not available")
        return None
        
    except Exception as e:
        print(f"         ❌ Chart analysis failed: {e}")
        return None


def _extract_chart_metadata(text, page_num):
    """
    Extract chart title, labels, type from surrounding text.
    
    Args:
        text: Page text content
        page_num: Page number
    
    Returns:
        dict: Chart metadata or None
    """
    
    lines = text.split('\n')
    metadata = {
        'title': None,
        'type': None,
        'x_axis_label': None,
        'y_axis_label': None,
        'possible_data_points': []
    }
    
    # Look for title (usually first meaningful line)
    for line in lines[:10]:
        line = line.strip()
        if len(line) > 5 and len(line) < 100:
            # Skip if it looks like patient info or metadata
            lower_line = line.lower()
            if not any(kw in lower_line for kw in ['patient', 'date', 'page', 'report']):
                metadata['title'] = line
                break
    
    # Detect chart type from keywords
    lower_text = text.lower()
    if 'trend' in lower_text or 'over time' in lower_text:
        metadata['type'] = 'Line Chart (Trend)'
    elif 'comparison' in lower_text or 'vs' in lower_text:
        metadata['type'] = 'Bar Chart (Comparison)'
    elif 'distribution' in lower_text or '%' in lower_text:
        metadata['type'] = 'Pie/Distribution Chart'
    else:
        metadata['type'] = 'Unknown Chart Type'
    
    # Only return if we found at least a title
    if metadata['title']:
        return metadata
    
    return None


# ============================================================================
# INTEGRATION HELPER: Merge lab data + graph insights
# ============================================================================

def merge_lab_and_graph_data(lab_data_json, graph_results):
    """
    Combine structured lab test data with graph/chart insights.
    
    Creates unified response that query engine can use.
    
    Args:
        lab_data_json: JSON string from table_extractor.extract_tables()
        graph_results: Dict from analyze_graphical_pages()
    
    Returns:
        dict: Unified data structure
    """
    import json
    
    result = {
        'lab_tests': [],
        'graph_insights': {},
        'has_ecg_data': False,
        'has_chart_data': False
    }
    
    # Parse lab data
    if lab_data_json:
        try:
            result['lab_tests'] = json.loads(lab_data_json)
        except:
            result['lab_tests'] = []
    
    # Add graph insights
    if graph_results:
        # ECG data
        if graph_results.get('ecg_analysis'):
            result['graph_insights']['ecg'] = graph_results['ecg_analysis']
            result['has_ecg_data'] = True
            
            # 🔥 NEW: Also add ECG measurements to lab_tests for unified querying!
            ecg_meas = graph_results['ecg_analysis'].get('measurements', [])
            if ecg_meas:
                for m in ecg_meas:
                    # Convert to same format as lab_tests
                    lab_test_entry = {
                        'test': m.get('name', ''),
                        'value': str(m.get('value', '')),
                        'unit': m.get('unit', ''),
                        'range': f"{m.get('reference_range', ('', ''))[0]}-{m.get('reference_range', ('', ''))[1]}" if isinstance(m.get('reference_range', ()), tuple) else '',
                        'flag': 'HIGH' if not m.get('is_normal', True) else ('LOW' if m.get('is_normal') == False else '')
                    }
                    
                    # Avoid duplicates
                    existing_names = [t.get('test', '').lower() for t in result['lab_tests']]
                    if lab_test_entry['test'].lower() not in existing_names:
                        result['lab_tests'].append(lab_test_entry)
        
        # Chart data
        if graph_results.get('chart_analysis'):
            result['graph_insights']['charts'] = graph_results['chart_analysis']
            result['has_chart_data'] = True
        
        # Metadata
        result['graph_insights']['pages_analyzed'] = graph_results.get('total_pages_analyzed', 0)
        result['graph_insights']['errors'] = graph_results.get('errors', [])
    
    return result