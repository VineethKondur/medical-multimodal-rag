# 🔍 DIAGNOSTIC & DEBUGGING GUIDE

## Quick Diagnostic Checklist

### Before Running Server
```
☐ backend/.env file exists with GROQ_API_KEY
☐ All dependencies installed: pip install -r requirements.txt
☐ No Python syntax errors
☐ Python version 3.8+
```

### After Starting Server
```
☐ Server starts without errors
☐ Visit http://localhost:8000 and see the UI
☐ Browser console (F12) shows no major errors
☐ Upload form visible and accepts files
```

### After Uploading PDF
```
☐ Green success message appears
☐ Console shows "INDEXING PDF..."
☐ Console shows "PDF INDEXED SUCCESSFULLY"
☐ No 500 error responses
☐ FAISS index created at: backend/faiss_index/
```

### After Querying
```
☐ Response appears within 5 seconds
☐ For table queries: 5 columns visible (Test, Value, Unit, Range, Status)
☐ Status column shows: NORMAL (green), HIGH (red), LOW (orange), or UNKNOWN (gray)
☐ No "UNKNOWN" status for all values (if so, check reference ranges)
```

---

## Common Issues & Fixes

### Issue 1: ImportError: No module named 'camelot'
```
Symptom: 
  ModuleNotFoundError: No module named 'camelot'

Fix:
  pip install camelot-py
  
Verify:
  python -c "import camelot; print('✓ camelot installed')"
```

### Issue 2: ImportError: No module named 'groq'
```
Symptom:
  ModuleNotFoundError: No module named 'groq'

Fix:
  pip install groq
  
Verify:
  python -c "import groq; print('✓ groq installed')"
```

### Issue 3: GROQ_API_KEY environment variable not found
```
Symptom:
  GROQ_API_KEY not found in environment
  LLM responses show errors or return None

Fix:
  1. Create backend/.env file
  2. Add: GROQ_API_KEY=your_actual_key
  3. Restart Django server
  
Verify:
  python -c "from dotenv import load_dotenv; import os; load_dotenv(); print(bool(os.getenv('GROQ_API_KEY')))"
```

### Issue 4: Status column shows all "UNKNOWN"
```
Symptom:
  All test results show Status: UNKNOWN

Possible Causes:
  1. Reference range not parsed correctly
  2. Value not extracted correctly
  3. Reference range format unexpected

Debug:
  1. Check console output (terminal) for parsing debug info
  2. Add debug: print(f"Parsing: value={row['value']}, range={row['range']}")
  3. Check PDF has standard reference ranges like "4.0-5.5"
  
Fix:
  1. Use standard reference range formats
  2. Ensure PDFs have clear reference ranges in tables
```

### Issue 5: No tables extracted from PDF
```
Symptom:
  Console shows: "Tables extracted: 0"
  Query result: "Could not understand query"

Possible Causes:
  1. PDF has no structured tables
  2. Tables are scanned images (OCR needed)
  3. Table format not recognized by camelot

Fix:
  1. Try different PDFs with clear table structures
  2. Install OCR: pip install easyocr
  3. Check PDF is actually readable by camelot:
     python -c "import camelot; tables = camelot.read_pdf('file.pdf'); print(tables.n)"
```

### Issue 6: FAISS index errors
```
Symptom:
  Error: FAISS index not found
  Error: Directory permissions

Fix:
  1. Make sure to upload a PDF first (creates index)
  2. Check backend/faiss_index/ directory exists
  3. Check read/write permissions:
     ls -la backend/faiss_index/
  4. On Windows, may need to run as admin
```

### Issue 7: Frontend table doesn't show Status column
```
Symptom:
  Table renders with 4 columns instead of 5
  Status column missing

Fix:
  1. Hard refresh: Ctrl+Shift+R (Windows/Linux) or Cmd+Shift+R (Mac)
  2. Clear browser cache and cookies
  3. Check browser console (F12) for errors
  4. Try different browser
```

### Issue 8: Slow LLM responses or timeouts
```
Symptom:
  Queries take >10 seconds
  Connection timeout errors

Possible Causes:
  1. GROQ API key rate limited
  2. Network issues
  3. PDF too large

Fix:
  1. Wait a minute and retry
  2. Check internet connection
  3. Try smaller PDF
  4. Check GROQ API status at console.groq.com
```

### Issue 9: Database errors (OperationalError)
```
Symptom:
  Error: database is locked
  Error: no such table

Fix:
  1. Run migrations:
     python manage.py migrate
  2. Delete db.sqlite3 and re-run migrations (if safe):
     rm db.sqlite3
     python manage.py migrate
```

### Issue 10: Port already in use
```
Symptom:
  Error: Address already in use :8000

Fix:
  1. Use different port:
     python manage.py runserver 8001
  2. Or kill existing process:
     lsof -ti:8000 | xargs kill -9  # Linux/Mac
     netstat -ano | findstr :8000   # Windows
```

---

## Debug Mode: Enable Verbose Logging

### Add to Django settings for more debug output
Edit `backend/backend/settings.py`:

```python
# At the end of the file, add:
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'DEBUG',
    },
}
```

### Add debug prints to views.py
Edit `backend/rag/views.py`, add near table parsing:

```python
print(f"\n=== DEBUG ===")
print(f"Table text: {table_text[:200]}...")  # First 200 chars
print(f"Number of rows parsed: {len(table_rows)}")
for i, row in enumerate(table_rows[:3]):  # First 3 rows
    print(f"  Row {i}: {row}")
print(f"=============\n")
```

---

## Performance Profiling

### Check PDF extraction time
```python
import time

start = time.time()
text = extract_text_from_pdf(file_path)
elapsed = time.time() - start
print(f"Text extraction took {elapsed:.2f}s")
```

### Check table extraction time
```python
start = time.time()
tables = camelot.read_pdf(file_path, pages="all", flavor="lattice")
elapsed = time.time() - start
print(f"Table extraction found {tables.n} tables in {elapsed:.2f}s")
```

### Check vector search time
```python
start = time.time()
docs = vectorstore.similarity_search(question, k=5)
elapsed = time.time() - start
print(f"Vector search took {elapsed:.2f}s")
```

---

## Testing Checklist

### Test with Sample Data
Create `test_sample.py`:

```python
import os
from backend.rag.views import detect_status

# Test status detection
test_cases = [
    (7.5, "4.0-5.5", "HIGH"),      # Above range
    (4.5, "4.0-5.5", "NORMAL"),    # In range
    (3.0, "4.0-5.5", "LOW"),       # Below range
    (150, "<200", "NORMAL"),       # Less than
    (250, "<200", "HIGH"),         # More than limit
    (15, ">10", "NORMAL"),         # More than
    (5, ">10", "LOW"),             # Less than limit
]

print("Testing detect_status():")
for value, ref_range, expected in test_cases:
    result = detect_status(value, ref_range)
    status = "✓" if result == expected else "✗"
    print(f"{status} detect_status({value}, '{ref_range}') = {result} (expected {expected})")
```

Run:
```bash
cd backend
python ../test_sample.py
```

---

## Browser DevTools Debugging

### 1. Open Console (F12)
Check for JavaScript errors

### 2. Open Network tab
- Watch API requests
- Check `/api/upload/` and `/api/query/` responses
- Look for 200 (success) or 500 (error) status codes

### 3. Open Storage tab
Check if session data is being saved

### 4. Inspect table element
Right-click table → Inspect → Check HTML structure

---

## Final Verification Script

Create `verify_setup.py` and run it:

```python
#!/usr/bin/env python
import os
import sys

print("🔍 Medical Project Verification\n")

checks = {
    ".env exists": os.path.exists("backend/.env"),
    "GROQ_API_KEY set": bool(os.getenv("GROQ_API_KEY")),
    "requirements.txt exists": os.path.exists("requirements.txt"),
    "manage.py exists": os.path.exists("backend/manage.py"),
    "views.py exists": os.path.exists("backend/rag/views.py"),
    "index.html exists": os.path.exists("backend/rag/templates/rag/index.html"),
}

print("File Checks:")
for check, result in checks.items():
    status = "✓" if result else "✗"
    print(f"  {status} {check}")

try:
    print("\nDependency Checks:")
    import django
    print(f"  ✓ Django {django.get_version()}")
    import rest_framework
    print(f"  ✓ Django REST Framework")
    import camelot
    print(f"  ✓ Camelot")
    import groq
    print(f"  ✓ Groq")
    import langchain
    print(f"  ✓ LangChain")
except ImportError as e:
    print(f"  ✗ {e}")

print("\n" + "="*50)
if all(checks.values()):
    print("✓ Setup looks good! Ready to run.")
else:
    print("✗ Some checks failed. Fix issues above.")
```

