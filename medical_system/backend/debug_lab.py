"""
🔬 Lab Report Extraction Diagnostic Tool v1.0
============================================
Run: python debug_lab.py <path-to-pdf>

This will show you EXACTLY why categorical values are being rejected!
"""

import sys
import os

# Add project path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set Django settings - CHANGE THIS if your settings file is named differently!
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

# Initialize Django
import django
django.setup()

# Import your table extractor - CHANGE 'lab_reports' to your actual app name!
try:
    from rag.services.table_extractor import (
    is_valid_categorical_value,
    is_valid_in_table_context,
    is_metadata_text,
    is_garbage_value,
    extract_tables,
)
    print("✅ Successfully imported table_extractor")
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("\n⚠️  You may need to change the import line above!")
    print("   Look for: from lab_reports.table_extractor import ...")
    print("   Change 'lab_reports' to your actual app folder name")
    sys.exit(1)

import fitz
import camelot
import re


def separator(char="=", length=80):
    print(char * length)


def test_categorical_values():
    """
    Test 1: Check if is_valid_categorical_value() works correctly
    """
    separator()
    print("🧪 TEST 1: CATEGORICAL VALUE VALIDATOR")
    separator()
    
    # List of values we want to test
    # Format: (value_string, should_it_be_accepted?)
    test_values = [
        # These SHOULD pass ✅
        ("Not Detected", True),
        ("Positive", True),
        ("Negative", True),
        ("Reactive", True),
        ("Non-Reactive", True),
        ("Non reactive", True),
        ("Pale Yellow", True),
        ("Yellow", True),
        ("Clear", True),
        ("Cloudy", True),
        ("Turbid", True),
        ("Normal", True),
        ("Abnormal", True),
        ("Present", True),
        ("Absent", True),
        ("Trace", True),
        ("Small", True),
        ("Moderate", True),
        ("Large", True),
        ("A", True),           # Blood group
        ("B", True),
        ("AB", True),
        ("O", True),
        ("0-5", True),         # Range
        ("2-3", True),         # Range
        ("1+", True),          # Grade
        ("2+", True),
        ("3+", True),
        ("4+", True),
        ("Reactive 1:64", True),  # VDRL result
        ("Few", True),
        ("Many", True),
        ("Occasional", True),
        ("Scarce", True),
        ("Not Seen", True),
        ("None", True),
        ("Nil", True),
        
        # These should FAIL ❌ (they're numeric, not categorical)
        ("12.6", False),
        ("88", False),
        ("139", False),
        ("6.0", False),
        ("1.015", False),
        ("5.600", False),
        ("3240", False),
    ]
    
    print(f"\n{'Value':<25} {'Expected':<10} {'Actual':<10} {'Result'}")
    print("-" * 55)
    
    passed = 0
    failed = 0
    failed_items = []
    
    for value, expected in test_values:
        try:
            actual = is_valid_categorical_value(value)
            
            if actual == expected:
                status = "✅ PASS"
                passed += 1
            else:
                status = "❌ FAIL"
                failed += 1
                failed_items.append((value, expected, actual))
            
            print(f"{value:<25} {str(expected):<10} {str(actual):<10} {status}")
            
        except Exception as e:
            failed += 1
            failed_items.append((value, expected, f"ERROR: {e}"))
            print(f"{value:<25} {str(expected):<10} {'ERROR':<10} ❌ {e}")
    
    print("-" * 55)
    print(f"\n📊 Results: {passed}/{len(test_values)} passed, {failed} failed")
    
    if failed > 0:
        print(f"\n⚠️  FAILED ITEMS:")
        for value, expected, actual in failed_items:
            print(f"   '{value}' → Expected {expected}, got {actual}")
        return False
    else:
        print("\n✅ All categorical value tests passed!")
        return True


def test_full_validation():
    """
    Test 2: Check complete validation pipeline with realistic examples
    """
    separator()
    print("🧪 TEST 2: FULL VALIDATION PIPELINE")
    separator()
    
    # Real-world test cases
    test_cases = [
        # (test_name, value, should_pass, description)
        ("Haemoglobin", "12.6", True, "Numeric CBC value"),
        ("WBC Count", "5400", True, "Numeric WBC"),
        ("RBC Count", "4.1", True, "Numeric RBC"),
        ("Platelets", "210000", True, "Numeric platelet"),
        ("pH", "6.0", True, "Urine pH numeric"),
        ("Specific Gravity", "1.015", True, "Urine SG decimal"),
        ("Fasting Glucose", "88", True, "Blood sugar numeric"),
        ("TSH", "5.600", True, "Thyroid numeric"),
        ("Colour", "Pale Yellow", True, "Urine color categorical"),
        ("Appearance", "Clear", True, "Urine appearance"),
        ("Glucose (urine)", "Not Detected", True, "Urine glucose negative"),
        ("Protein", "Not Detected", True, "Urine protein negative"),
        ("Ketones", "Not Detected", True, "Urine ketones negative"),
        ("Blood (urine)", "Not Detected", True, "Urine blood negative"),
        ("Bilirubin", "Not Detected", True, "Urine bilirubin negative"),
        ("Pus Cells", "0-5", True, "Microscopic range"),
        ("Epithelial Cells", "2-3", True, "Microscopic range"),
        ("Casts", "Not Detected", True, "Microscopic negative"),
        ("Crystals", "Not Detected", True, "Microscopic negative"),
        ("Bacteria", "Not Detected", True, "Microscopic negative"),
        ("VDRL", "Reactive 1:64", True, "Serology result"),
        ("HIV Antibody", "Non Reactive", True, "Serology negative"),
        ("Blood Grouping", "A", True, "Blood group"),
        ("Rh (D) Typing", "Positive", True, "Rh factor"),
        ("Urobilinogen", "Normal", True, "Urine chemical"),
        ("Nitrite", "Not Detected", True, "Urine chemical"),
        
        # These should FAIL ❌
        ("Sample ID", "10002304958", False, "Metadata - sample ID"),
        ("Patient Name", "Mrs. PL02", False, "Metadata - patient name"),
        ("Report Status", "Final", False, "Metadata - status"),
        ("Empty Value", "", False, "Empty string"),
        ("Just Dashes", "-", False, "Dash placeholder"),
    ]
    
    print(f"\n{'Test Name':<22} {'Value':<22} {'Expect':<8} {'Actual':<8} {'Status'}")
    print("-" * 75)
    
    passed = 0
    failed = 0
    failed_items = []
    
    for test_name, value, expected, desc in test_cases:
        try:
            actual = is_valid_in_table_context(test_name, value)
            
            if actual == expected:
                status = "✅"
                passed += 1
            else:
                status = "❌"
                failed += 1
                failed_items.append((test_name, value, expected, actual))
            
            print(f"{test_name:<22} {value:<22} {str(expected):<8} {str(actual):<8} {status}  {desc}")
            
        except Exception as e:
            failed += 1
            failed_items.append((test_name, value, expected, f"ERROR: {e}"))
            print(f"{test_name:<22} {value:<22} {str(expected):<8} {'ERR':<8} ❌  {e}")
    
    print("-" * 75)
    print(f"\n📊 Results: {passed}/{len(test_cases)} passed, {failed} failed")
    
    if failed > 0:
        print(f"\n⚠️  FAILED CASES:")
        for test_name, value, expected, actual in failed_items:
            print(f"   ❌ {test_name}: '{value}' → Expected {expected}, got {actual}")
        return False
    else:
        print("\n✅ All validation tests passed!")
        return True


def analyze_pdf_tables(pdf_path):
    """
    Test 3: Extract tables from PDF and show what gets accepted/rejected
    """
    separator()
    print(f"🔍 TEST 3: PDF TABLE ANALYSIS")
    print(f"   File: {pdf_path}")
    separator()
    
    if not os.path.exists(pdf_path):
        print(f"❌ ERROR: File not found!")
        print(f"   Looking for: {pdf_path}")
        print(f"   Current directory: {os.getcwd()}")
        return
    
    file_size = os.path.getsize(pdf_path) / 1024
    print(f"   File size: {file_size:.1f} KB")
    
    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    print(f"   Total pages: {total_pages}")
    
    total_accepted = 0
    total_rejected = 0
    
    # Analyze first 5 pages (or fewer if PDF is smaller)
    pages_to_check = min(5, total_pages)
    
    for page_num in range(pages_to_check):
        page = doc[page_num]
        
        print(f"\n{'─' * 80}")
        print(f"📄 PAGE {page_num + 1} of {total_pages}")
        print(f"{'─' * 80}")
        
        page_accepted = 0
        page_rejected = 0
        
        try:
            # Try Camelot extraction
            ct = camelot.read_pdf(
                pdf_path, 
                pages=str(page_num + 1),
                flavor='lattice',
                suppress_stdout=True
            )
            
            if ct.n == 0:
                ct = camelot.read_pdf(
                    pdf_path,
                    pages=str(page_num + 1),
                    flavor='stream',
                    suppress_stdout=True
                )
            
            if ct.n == 0:
                print(f"   ℹ️  No tables found on this page")
                continue
            
            for t_idx, table in enumerate(ct):
                df = table.df
                
                if df.shape[0] < 2 or df.shape[1] < 2:
                    continue
                
                print(f"\n   📊 Table {t_idx}: {df.shape[0]} rows × {df.shape[1]} columns")
                print(f"   Columns: {list(df.columns)[:5]}...")
                print(f"\n   {'#':<4} {'Test Name':<28} {'Value':<20} {'Valid?':<7} {'Reason if Rejected'}")
                print(f"   {'-' * 85}")
                
                rows_shown = 0
                
                for i in range(len(df)):
                    try:
                        row = df.iloc[i]
                        
                        # Get test name and value
                        if df.shape[1] >= 2:
                            test_raw = str(row.iloc[0]).strip()
                            val_raw = str(row.iloc[1]).strip()
                        else:
                            continue
                        
                        # Skip empty/invalid rows
                        if not test_raw or test_raw.lower() in ['nan', '', 'none', 'test name']:
                            continue
                        if not val_raw or val_raw.lower() in ['nan', '', 'none', '-', 'result']:
                            continue
                        
                        # Run validation
                        is_valid = is_valid_in_table_context(test_raw, val_raw)
                        
                        if is_valid:
                            total_accepted += 1
                            page_accepted += 1
                            status = "✅"
                            reason = ""
                        else:
                            total_rejected += 1
                            page_rejected += 1
                            status = "❌"
                            
                            # Determine WHY it was rejected
                            if is_metadata_text(test_raw):
                                reason = "Metadata text"
                            elif is_garbage_value(val_raw):
                                reason = "Garbage pattern"
                            elif not re.search(r'\d', val_raw) and not is_valid_categorical_value(val_raw):
                                reason = f"Not num & not cat ('{val_raw[:18]}')"
                            else:
                                reason = "Unknown reason"
                        
                        # Display row (limit to first 30 per table to avoid flooding)
                        if rows_shown < 30:
                            display_test = test_raw[:26]
                            display_val = val_raw[:18]
                            print(f"   {i:<4} {display_test:<28} {display_val:<20} {status:<7} {reason}")
                            rows_shown += 1
                    
                    except Exception as e:
                        pass
                
                if rows_shown >= 30:
                    print(f"   ... ({rows_shown} rows shown, more exist)")
            
            print(f"\n   📈 Page {page_num + 1}: ✅ {page_accepted} accepted, ❌ {page_rejected} rejected")
                
        except Exception as e:
            print(f"   ⚠️ Error processing page: {e}")
    
    doc.close()
    
    print(f"\n{'=' * 80}")
    print(f"📊 TABLE ANALYSIS SUMMARY:")
    print(f"   Total accepted: {total_accepted}")
    print(f"   Total rejected: {total_rejected}")
    
    if total_rejected > total_accepted:
        print(f"   ⚠️  WARNING: More rejections than acceptances!")
        print(f"   → Your validator is probably too strict")
    elif total_accepted == 0:
        print(f"   ❌ CRITICAL: Nothing was accepted at all!")
        print(f"   → Something is fundamentally broken")
    else:
        print(f"   ✅ Looks reasonable")
    
    return total_accepted, total_rejected


def run_full_extraction(pdf_path):
    """
    Test 4: Run the actual extract_tables() function and show results
    """
    separator()
    print("🎯 TEST 4: FULL EXTRACTION TEST")
    separator()
    
    print(f"\n   Running extract_tables('{pdf_path}')...")
    print(f"   This may take 15-30 seconds...\n")
    
    results = extract_tables(pdf_path)
    
    if not results:
        print("\n❌ NO TESTS EXTRACTED!")
        print("   The extractor returned an empty list.")
        return []
    
    print(f"\n✅ SUCCESS! Extracted {len(results)} tests total\n")
    
    # Group by category for better readability
    categories = {}
    
    for r in results:
        test_lower = r['test'].lower()
        
        # Categorize based on keywords
        if any(kw in test_lower for kw in [
            'haemoglobin', 'hemoglobin', 'rbc count', 'wbc count', 'platelet',
            'neutrophil', 'lymphocyte', 'eosinophil', 'monocyte', 'basophil',
            'pcv', 'hematocrit', 'mcv', 'mch', 'mchc', 'rdw'
        ]):
            cat = '🩸 CBC / HEMATOLOGY'
        
        elif any(kw in test_lower for kw in [
            'glucose', 'fasting', 'random', 'hba1c', 'sugar'
        ]):
            cat = '🍬 BLOOD SUGAR'
        
        elif any(kw in test_lower for kw in [
            'cholesterol', 'triglyceride', 'hdl', 'ldl', 'vldl', 'lipid'
        ]):
            cat = '🫀 LIPID PROFILE'
        
        elif any(kw in test_lower for kw in [
            'tsh', 't3', 't4', 'thyroid', 'free t3', 'free t4'
        ]):
            cat = '🦋 THYROID FUNCTION'
        
        elif any(kw in test_lower for kw in [
            'colour', 'color', 'appearance', 'specific gravity', 'ph',
            'protein', 'ketone', 'pus cell', 'epithelial', 'cast', 'crystal',
            'bilirubin', 'urobilinogen', 'nitrite', 'bacteria', 'yeast', 'mucus'
        ]):
            cat = '💧 URINE ROUTINE'
        
        elif any(kw in test_lower for kw in [
            'vdrl', 'hiv', 'hepatitis', 'hbsag', 'hcv', 'malaria', 'dengue'
        ]):
            cat = '🦠 SEROLOGY / INFECTIOUS'
        
        elif any(kw in test_lower for kw in [
            'blood group', 'rh typing', 'abo'
        ]):
            cat = '🅰️ BLOOD GROUPING'
        
        elif any(kw in test_lower for kw in [
            'sgot', 'sgpt', 'alt', 'ast', 'albumin', 'globulin', 'bilirubin'
        ]):
            cat = '🫁 LIVER FUNCTION'
        
        elif any(kw in test_lower for kw in [
            'creatinine', 'urea', 'uric acid', 'sodium', 'potassium'
        ]):
            cat = '🫘 KIDNEY FUNCTION'
        
        else:
            cat = '📋 OTHER TESTS'
        
        if cat not in categories:
            categories[cat] = []
        
        categories[cat].append(r)
    
    # Print results grouped by category
    print("=" * 80)
    print("📋 EXTRACTED TESTS BY CATEGORY:")
    print("=" * 80)
    
    for cat_name in sorted(categories.keys()):
        tests = categories[cat_name]
        
        print(f"\n{cat_name}  ({len(tests)} tests)")
        print("-" * 75)
        
        for t in sorted(tests, key=lambda x: x['test']):
            # Format output nicely
            flag_str = ""
            if t.get('flag'):
                flag_str = f" ⚠️ [{t['flag'].upper()}]"
            
            unit_str = f" {t['unit']}" if t.get('unit') else ""
            range_str = f" (Ref: {t['range']})" if t.get('range') else ""
            
            print(f"  • {t['test']:<35} {t['value']:<15}{unit_str:<8}{range_str}{flag_str}")
    
    # Critical checks
    separator()
    print("🎯 CRITICAL VERIFICATION:")
    separator()
    
    # Check for pH specifically
    ph_tests = [r for r in results if 'ph' in r['test'].lower()]
    urine_tests = [r for r in results if any(
        kw in r['test'].lower()
        for kw in ['ph', 'colour', 'color', 'appearance', 'pus cells', 
                   'epithelial', 'specific gravity']
    )]
    categorical_tests = [r for r in results if is_valid_categorical_value(r['value'])]
    
    print(f"   ✓ Total tests extracted:     {len(results)}")
    print(f"   ✓ Urine-related tests:       {len(urine_tests)}")
    print(f"   ✓ Tests with categorical values: {len(categorical_tests)}")
    print(f"   ✓ pH value found:            {'YES ✅ → ' + ph_tests[0]['value'] if ph_tests else 'NO ❌'}")
    
    if ph_tests:
        print(f"\n   🎉 URINE pH DETAILS:")
        print(f"      Test:  {ph_tests[0]['test']}")
        print(f"      Value: {ph_tests[0]['value']}")
        print(f"      Unit:  {ph_tests[0].get('unit', 'N/A')}")
        print(f"      Range: {ph_tests[0].get('range', 'N/A')}")
    
    return results


# ════════════════════════════════════════════════════════════
# MAIN EXECUTION POINT
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":
    
    print("\n" + "🔬" * 50)
    print("🔬 LAB REPORT EXTRACTION DIAGNOSTIC SUITE v1.0")
    print("🔬" * 50)
    
    # Check command line arguments
    if len(sys.argv) < 2:
        print("\n" + "=" * 80)
        print("❌ ERROR: No PDF file specified!")
        print("=" * 80)
        print("\nUsage:")
        print("   python debug_lab.py <path-to-your-pdf-file>")
        print("\nExamples:")
        print("   python debug_lab.py 77055070-c7ef-419e-97bb-2403f4436c14.pdf")
        print("   python debug_lab.py ..\\pdfs\\report.pdf")
        print("   python debug_lab.py C:\\Users\\You\\Documents\\lab_report.pdf")
        print("=" * 80)
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    
    # Verify file exists
    if not os.path.exists(pdf_path):
        print(f"\n❌ ERROR: File not found!")
        print(f"   Path: {pdf_path}")
        print(f"   Current directory: {os.getcwd()}")
        print("\nTips:")
        print("   • Make sure the filename is correct")
        print("   • Use double backslashes (\\) in paths")
        print("   • If file is in parent folder, use ..\\filename.pdf")
        sys.exit(1)
    
    print(f"\n📁 Target PDF: {pdf_path}")
    print(f"📏 File size: {os.path.getsize(pdf_path) / 1024:.1f} KB")
    print(f"📍 Current dir: {os.getcwd()}")
    
    # Run all diagnostic tests
    print("\n" + "⏳" * 50)
    print("Running diagnostics... (this may take up to a minute)")
    print("⏳" * 50)
    
    # Test 1: Categorical value validator
    test1_result = test_categorical_values()
    
    # Test 2: Full validation pipeline  
    test2_result = test_full_validation()
    
    # Test 3: PDF table analysis
    accepted, rejected = analyze_pdf_tables(pdf_path)
    
    # Test 4: Full extraction
    final_results = run_full_extraction(pdf_path)
    
    # Final verdict
    print("\n\n" + "=" * 80)
    print("🎯 FINAL VERDICT & RECOMMENDATIONS")
    print("=" * 80)
    
    issues_found = []
    successes = []
    
    # Evaluate Test 1
    if test1_result:
        successes.append("✅ Categorical value validator works correctly")
    else:
        issues_found.append("❌ Categorical value validator has bugs")
    
    # Evaluate Test 2
    if test2_result:
        successes.append("✅ Full validation pipeline works correctly")
    else:
        issues_found.append("❌ Validation pipeline rejects valid data")
    
    # Evaluate Test 3
    if rejected > accepted:
        issues_found.append(f"⚠️  Too many rejections ({rejected} vs {accepted} accepted)")
    elif accepted > 0:
        successes.append(f"✅ Table extraction working ({accepted} rows accepted)")
    
    # Evaluate Test 4 - Most important!
    ph_exists = any('ph' in r['test'].lower() for r in final_results)
    urine_count = len([r for r in final_results if any(
        kw in r['test'].lower() 
        for kw in ['colour', 'color', 'appearance', 'ph', 'pus cells', 'epithelial']
    )])
    
    if ph_exists:
        successes.append("✅ Urine pH successfully extracted!")
    else:
        issues_found.append("❌ CRITICAL: Urine pH NOT extracted (main bug!)")
    
    if urine_count >= 10:
        successes.append(f"✅ Good urine test coverage ({urine_count} tests)")
    elif urine_count > 0:
        issues_found.append(f"⚠️  Partial urine extraction ({urine_count} tests) - some missing")
    else:
        issues_found.append("❌ No urine tests extracted at all!")
    
    # Print results
    print("\n✅ WHAT'S WORKING:")
    for s in successes:
        print(f"   {s}")
    
    if issues_found:
        print("\n❌ ISSUES FOUND:")
        for issue in issues_found:
            print(f"   {issue}")
        
        print("\n" + "-" * 80)
        print("📋 NEXT STEPS:")
        print("-" * 80)
        print("""
   1. Copy this ENTIRE output (Ctrl+A, then Ctrl+C)
   2. Paste it in the chat where you got this script
   3. I'll analyze it and give you the EXACT fix needed
   
   OR if you want to fix it yourself:
   
   If "Categorical value validator has bugs":
      → Fix is_valid_categorical_value() function
   
   If "Validation pipeline rejects valid data":  
      → Fix is_valid_in_table_context() function
   
   If "pH NOT extracted":
      → One of the above two functions is too strict
""")
    else:
        print("\n" + "🎉" * 40)
        print("EVERYTHING IS WORKING PERFECTLY!")
        print(f"Successfully extracted {len(final_results)} tests including urine pH!")
        print("🎉" * 40)
    
    print("\n" + "=" * 80)
    print("Diagnostic complete! Have a nice day! 😊")
    print("=" * 80 + "\n")