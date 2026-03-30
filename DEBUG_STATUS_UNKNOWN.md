# 🔍 DEBUGGING: Status Shows UNKNOWN

## What I Added

I've added comprehensive debugging output to help identify why all status values show "UNKNOWN".

## How to Use

### Step 1: Start Server with Debug Output
```bash
cd medical_system/backend
python manage.py runserver
```

### Step 2: Upload a PDF
Go to http://localhost:8000 and upload a medical report PDF.

### Step 3: Watch Terminal Output
You'll see output like:
```
===== TABLE TEXT DEBUG =====
Table text length: 1250
First 500 chars:
TABLE ROW → Test: Hemoglobin, Value: 7.5, Unit: g/dL, Range: 4.0-5.5
TABLE ROW → Test: WBC, Value: 15.2, Unit: K/uL, Range: 4.5-11.0
...
===========================
```

### Step 4: Query and Check Output
Ask a question like "Show all tests"

You'll see:
```
===== QUERY DEBUG START =====
Table text from cache: True
Table text length: 1250
First 300 chars: TABLE ROW → Test: Hemoglobin...

Parsed 15 initial rows
DEBUG: Test=Hemoglobin, Value=7.5, Range=4.0-5.5, Status=HIGH
DEBUG: Test=WBC, Value=15.2, Range=4.5-11.0, Status=HIGH
...
After dedup: 12 unique rows
===== QUERY DEBUG END =====
```

---

## Interpreting the Output

### If Status Shows UNKNOWN:
Look for these issues in the output:

**Case 1: Range is empty**
```
DEBUG: ..., Range=, Status=UNKNOWN
```
**Solution**: PDF doesn't have reference ranges in tables

**Case 2: Value is empty**
```
DEBUG: ..., Value=, Range=4.0-5.5, Status=UNKNOWN
```
**Solution**: PDF table values not being extracted

**Case 3: Range format unexpected**
```
DEBUG: ..., Range=See Lab Guidelines, Status=UNKNOWN
```
**Solution**: Range is text, not numeric

**Case 4: Value not numeric**
```
DEBUG: ..., Value=Result Pending, Range=4.0-5.5, Status=UNKNOWN
```
**Solution**: Cell contains text instead of number

---

## Common Issues

### Issue: "Parsed 0 initial rows"
- PDF has no table data extracted
- Check if PDF has clear lab tables
- Try another PDF

### Issue: Range shows "UNKNOWN"
- Table formatting not being parsed
- Check if PDF has reference range column
- May need manual table inspection

### Issue: All values are 0 or empty
- Text extraction failing
- PDF might be scanned (need OCR)
- Try: `pip install --upgrade easyocr`

---

## To Fix Specific Issues

### PDFs with Missing Reference Ranges
Add them manually or create a mapping:
```python
# Add to views.py in detect_status()
KNOWN_RANGES = {
    "hemoglobin": "4.0-5.5",
    "wbc": "4.5-11.0",
    # etc...
}
if not ref_range and test_name in KNOWN_RANGES:
    ref_range = KNOWN_RANGES[test_name]
```

### PDFs with Scanned Tables (OCR)
The system tries this automatically, but ensure easyocr is installed:
```bash
pip install --upgrade easyocr
```

### For Better PDF Extraction
Ensure PDF is:
- ✓ Text-based (not scanned)
- ✓ Has clear table structure
- ✓ Has values in standard format (e.g., "7.5" not "7.5 ±0.2")
- ✓ Has reference ranges (e.g., "4.0-5.5")

---

## Example: Good PDF vs Bad PDF

### GOOD PDF ✅
```
Test Name    | Value  | Unit   | Reference Range
Hemoglobin   | 7.5    | g/dL   | 4.0-5.5
WBC Count    | 15.2   | K/uL   | 4.5-11.0
Platelets    | 250    | K/uL   | 150-400
```
→ Will extract correctly and show status

### BAD PDF ❌
```
Test Analysis Report
Patient: John Doe
Lab Values Below:
Hemoglobin: Result Pending
WBC: See Notes Section
Platelets: Not Tested
```
→ Won't extract any values

---

## Next Steps

1. **Look at debug output** when you query
2. **Identify the issue** using examples above
3. **Try different PDF** to see if it works better
4. **Report pattern** - let me know what you see

Once I see the debug output, I can make targeted fixes!

---

## Quick Test

Use a simple medical PDF from your system:
1. Ensure it has proper tables
2. Has clear Value and Reference Range columns
3. Values are numbers, not text

Upload and ask "Show all tests" → Look at terminal output 👆

