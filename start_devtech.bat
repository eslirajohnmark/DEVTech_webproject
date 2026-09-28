@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
start "DEVTech Server" cmd /k python app.py
timeout /t 3 /nobreak >nul
start "" "https://localhost:5000/login"