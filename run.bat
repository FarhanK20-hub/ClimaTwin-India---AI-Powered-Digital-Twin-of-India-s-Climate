@echo off
echo ===================================================
echo   ClimaTwin India - AI Digital Twin of Climate
echo   ISRO Hack2Skill 2026 - Maharashtra Pilot
echo ===================================================
echo.

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found. Please install Python 3.10+
    pause
    exit /b 1
)

:: Install dependencies if needed
if not exist ".venv" (
    echo [1/3] Creating virtual environment...
    python -m venv .venv
)

echo [2/3] Installing dependencies...
call .venv\Scripts\activate.bat
pip install -r requirements.txt -q

echo [3/3] Starting ClimaTwin India server...
echo.
echo  Dashboard will open at: http://127.0.0.1:8000
echo  Press Ctrl+C to stop the server.
echo.

:: Start server
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload

pause
