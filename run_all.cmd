@echo off
setlocal

rem SIMRAI :: start backend (FastAPI) and frontend (React) dev servers on Windows.
rem
rem Requirements (one-time):
rem   - In this repo:    pip install -e .
rem   - In .\web folder: npm install
rem   - Recommended: create a venv at .\venv (auto-activated if present)

cd /d "%~dp0"

echo.
echo SIMRAI :: starting backend on http://127.0.0.1:8000 ...
if exist "venv\Scripts\activate.bat" (
  echo Using local venv at .\venv
  start "SIMRAI Backend" cmd /c "call venv\Scripts\activate.bat && simrai serve --host 0.0.0.0 --port 8000"
) else (
  echo No venv found at .\venv — falling back to global Python
  start "SIMRAI Backend" cmd /c "simrai serve --host 0.0.0.0 --port 8000"
)

echo.
echo SIMRAI :: starting web UI on http://127.0.0.1:5658 ...
cd web
npm run dev -- --host 127.0.0.1 --port 5658

endlocal


