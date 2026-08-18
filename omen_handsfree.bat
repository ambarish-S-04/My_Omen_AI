@echo off
title OMEN // Hands-Free Voice Mode
cd /d "%~dp0"

echo [*] Activating environment...
call .venv\Scripts\activate.bat

echo [*] Starting OMEN in Hands-Free Voice Mode...
.venv\Scripts\python.exe omen.py --voice

pause
