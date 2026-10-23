@echo off
cd /d "%~dp0"
if exist .venv\Scripts\activate.bat (call .venv\Scripts\activate.bat) else (call venv\Scripts\activate.bat)
set "SCHEME=http"
for /f "tokens=2 delims==" %%a in ('findstr /b "DEV_SSL=" .env 2^>nul') do if "%%a"=="1" set "SCHEME=https"
start "DEVTech Server" cmd /k python app.py
timeout /t 3 /nobreak >nul
start "" "%SCHEME%://localhost:5000/login"
