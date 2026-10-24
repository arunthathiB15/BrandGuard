@echo off
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (echo Python was not found. Install Python 3.10 or newer from https://www.python.org/downloads/ and enable Add Python to PATH. & pause & exit /b 1)
python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
