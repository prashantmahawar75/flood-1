@echo off
setlocal
cd /d "%~dp0"
title PRAHARI Full-Stack Flash Flood Routing
if "%PORT%"=="" set PORT=8000
echo Starting PRAHARI FastAPI backend on http://127.0.0.1:%PORT% ...
start "PRAHARI API" cmd /k "cd /d ""%~dp0"" && python -m uvicorn backend.app.main:app --host 127.0.0.1 --port %PORT%"
timeout /t 3 /nobreak >nul
start "" "http://127.0.0.1:%PORT%"
echo Dashboard opened. Keep the PRAHARI API window running during the demo.
endlocal
