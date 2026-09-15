@echo off
cd /d "%~dp0"
if "%PORT%"=="" set PORT=8000
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port %PORT%
