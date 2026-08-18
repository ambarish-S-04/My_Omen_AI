@echo off
title AETHER-OS // Terminal TUI
cd /d "%~dp0"

echo [*] Activating .venv on D: drive...
call .venv\Scripts\activate.bat

echo [*] Starting AETHER-OS TUI...
.venv\Scripts\python.exe cli.py

pause
