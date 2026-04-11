@echo off
REM === AKTUALIZUJ ŚCIEŻKI DO PYTHONA I SKRYPTU PONIŻEJ ===

REM Ścieżka do interpretera Pythona
set "PYTHON_PATH=C:\Program Files\Python310\python.exe"

REM Ścieżka do Twojego skryptu dashboardu
set "SCRIPT_PATH=C:\Program Files\Python310\forex_env\forex_dashboard\forex_dashboard.py"

REM Przejdź do katalogu skryptu (zalecane)
cd /d C:\Program Files\Python310\forex_env\
echo Odpalam HTTP server na porcie 8000...
start "HTTP Server" "%PYTHON_PATH%" -m http.server 8000

REM Opcjonalna pauza 2 sekundy, aby serwer miał czas się uruchomić
timeout /t 5 > nul

REM Przejdź do katalogu skryptu (zalecane)
cd /d C:\Program Files\Python310\forex_env\forex_dashboard\

echo Uruchamiam dashboard ForexBot...
start "Forex Dashboard" "%PYTHON_PATH%" "%SCRIPT_PATH%"

echo Wszystko uruchomione. Możesz zamknąć to okno, jeśli nie jest już potrzebne.
pause
