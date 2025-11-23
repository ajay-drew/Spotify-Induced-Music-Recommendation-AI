@echo off
setlocal

rem SIMRAI :: start backend (FastAPI) and frontend (React) dev servers on Windows.
rem
rem Requirements (one-time):
rem   - In this repo:    pip install -e .
rem   - In .\web folder: npm install

cd /d "%~dp0"

echo.
echo SIMRAI :: starting backend on http://localhost:8000 ...
start "SIMRAI Backend" cmd /c "simrai serve --host 0.0.0.0 --port 8000"

echo.
echo SIMRAI :: starting web UI on http://localhost:5658 ...
cd web
npm run dev -- --port 5658

endlocal


