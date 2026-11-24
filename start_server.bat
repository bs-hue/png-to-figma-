@echo off
echo ========================================================
echo   Starting PNG to Figma Backend Server (Port 8000)
echo ========================================================

if not exist .venv\Scripts\python.exe (
    echo [ERROR] Virtual environment nahi mila! Pehle "setup.bat" run karein.
    pause
    exit /b 1
)

.venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
pause
