@echo off
REM === AKTUALIZUJ ŚCIEŻKI DO PYTHONA I SKRYPTU PONIŻEJ ===

taskkill /IM python.exe /F

REM Ścieżka do interpretera Pythona w Twoim środowisku (np. venv)
set PYTHON_PATH=C:\Program Files\Python310\python.exe

REM Ścieżka do Twojego skryptu bota
set SCRIPT_PATH=C:\Program Files\Python310\forex_env\forex_ai_bot_v1.3.py

REM Przejdź do katalogu skryptu (opcjonalne, ale zalecane)
cd /d C:\Program Files\Python310\forex_env\

echo Uruchamiam bota Forex...
"%PYTHON_PATH%" "%SCRIPT_PATH%"