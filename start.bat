@echo off
title WebPulse AI v2.0
color 0B

echo.
echo  ==========================================
echo    WebPulse AI  --  Starting up...
echo  ==========================================
echo.

REM Check Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python not found. Install from https://python.org
    pause
    exit /b 1
)

REM Install dependencies
echo  Installing dependencies...
pip install fastapi uvicorn httpx beautifulsoup4 fpdf2 python-multipart --quiet

echo.
echo  ==========================================
echo    Server starting on http://localhost:8000
echo    API docs at   http://localhost:8000/docs
echo    Press Ctrl+C to stop
echo  ==========================================
echo.

REM Start the server
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

pause
