@echo off
title OMEN // Autonomous Personal AI Companion & OS Operator
cd /d "%~dp0"

echo [*] Activating virtual environment on D: drive...
call .venv\Scripts\activate.bat

echo [*] Starting OMEN...
.venv\Scripts\python.exe omen.py

pause
