# 🚀 QUICK START - Get Running in 5 Minutes

## Step 1: Get Your GROQ API Key (2 min)
1. Open: https://console.groq.com/
2. Sign up or log in
3. Create new API key
4. Copy the key

## Step 2: Create .env File (1 min)
Create file: `backend/.env`

```
GROQ_API_KEY=paste_your_key_here
```

## Step 3: Install Dependencies (1 min)
```bash
pip install -r requirements.txt
```

If you get errors, try:
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

## Step 4: Start Server (30 sec)
```bash
cd medical_system/backend
python manage.py migrate
python manage.py runserver
```

## Step 5: Test It! (30 sec)
1. Go to: http://localhost:8000
2. Upload a medical PDF
3. Ask: "Show all tests"
4. You should see a table with Status column (green/red/orange)

---

## ✅ What's Been Fixed

| Issue | Fixed? |
|-------|--------|
| Status always showing "UNKNOWN" | ✅ YES |
| Frontend table missing Status column | ✅ YES |
| Missing dependencies (camelot, easyocr) | ✅ YES |
| Table extraction failing | ✅ YES |
| Wrong FAISS index path | ✅ YES |

---

## 🐛 Having Issues?

### Error: "GROQ_API_KEY not found"
- Check .env file exists in `backend/` folder
- Check it has: `GROQ_API_KEY=your_actual_key`
- Restart server

### Error: "No module named 'camelot'"
- Run: `pip install camelot-py`

### Status shows all "UNKNOWN"
- Make sure PDF has reference ranges like "4.0-5.5"
- Try with a different PDF
- Check console output for parsing errors

### Table missing Status column
- Hard refresh: Ctrl+Shift+R
- Clear browser cache
- Check browser console (F12) for errors

---

## 📚 Need More Help?

- **Setup Guide**: See `SETUP_GUIDE.md` for detailed instructions
- **Troubleshooting**: See `DEBUG_GUIDE.md` for common issues
- **Full Analysis**: See `COMPLETE_ANALYSIS.md` for what was wrong

---

That's it! 🎉 You should be running now. Good luck! 🩺
