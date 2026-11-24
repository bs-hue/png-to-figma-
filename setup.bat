@echo off
echo ========================================================
echo   Setting up PNG to Figma (BloomX) on new machine
echo ========================================================

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python install nahi hai! 
    echo Kripya python.org se Python 3.10 ya latest install karein aur "Add to PATH" zaroor tick karein.
    pause
    exit /b 1
)

:: Create virtual environment if not exists
if not exist .venv (
    echo [1/3] Creating virtual environment (.venv)...
    python -m venv .venv
) else (
    echo [1/3] Virtual environment (.venv) already exists.
)

:: Install requirements
echo [2/3] Installing required packages...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt

:: Check Tesseract
echo [3/3] Checking environment & Tesseract OCR...
python check_environment.py

echo.
echo ========================================================
echo   Setup Complete! Ab aap "start_server.bat" double-click karke server chala sakte hain.
echo ========================================================
pause
