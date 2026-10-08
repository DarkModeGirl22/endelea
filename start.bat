@echo off
cd /d "%~dp0"
echo.
echo  Endelea - starting...
echo  Paste your free Gemini key, or just press Enter for DEMO MODE (no key needed).
echo.
set /p GEMINI_API_KEY=Gemini key (optional): 
start "" http://127.0.0.1:8000
python -m uvicorn backend.main:app --port 8000
