# ============================================================
# Setup Task Scheduler - Forex AI Bot + MetaTrader 5
# Uruchom jako Administrator na serwerze
# ============================================================

$User     = "PRI\btrender"
$MT5Path  = "C:\Program Files\MetaTrader 5\terminal64.exe"
$BotDir   = "C:\Program Files\Python310\forex_env"
$Python   = "C:\Program Files\Python310\python.exe"
$BotScript = "forex_ai_bot_v1.3.py"

# --- Nadaj uprawnienie "Log on as batch job" ---
Write-Host "Nadaje uprawnienia 'Log on as batch job' dla $User..." -ForegroundColor Cyan

# --- Task 1: MetaTrader 5 (uruchom przy logowaniu) ---
Write-Host "Tworzę task: ForexBot - MetaTrader5..." -ForegroundColor Green

$mt5Action  = New-ScheduledTaskAction -Execute $MT5Path
$mt5Trigger = New-ScheduledTaskTrigger -AtLogOn -User $User
$mt5Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 365)

Register-ScheduledTask `
    -TaskName "ForexBot - MetaTrader5" `
    -Action $mt5Action `
    -Trigger $mt5Trigger `
    -Settings $mt5Settings `
    -User $User `
    -RunLevel Limited `
    -Description "Uruchamia MetaTrader 5 przy logowaniu uzytkownika btrender" `
    -Force

Write-Host "  OK: Task 'ForexBot - MetaTrader5' utworzony" -ForegroundColor Green

# --- Task 2: Forex AI Bot (30s po MT5, z auto-restart) ---
Write-Host "Tworzę task: ForexBot - AI Bot v1.3..." -ForegroundColor Green

$botAction  = New-ScheduledTaskAction `
    -Execute $Python `
    -Argument $BotScript `
    -WorkingDirectory $BotDir

$botTrigger = New-ScheduledTaskTrigger -AtLogOn -User $User
$botTrigger.Delay = "PT30S"  # 30 sekund opóźnienia (czekaj na MT5)

$botSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 2) `
    -ExecutionTimeLimit (New-TimeSpan -Days 365)

Register-ScheduledTask `
    -TaskName "ForexBot - AI Bot v1.3" `
    -Action $botAction `
    -Trigger $botTrigger `
    -Settings $botSettings `
    -User $User `
    -RunLevel Limited `
    -Description "Uruchamia Forex AI Bot v1.3 (Python) 30s po logowaniu btrender. Auto-restart co 2 min przy awarii." `
    -Force

Write-Host "  OK: Task 'ForexBot - AI Bot v1.3' utworzony" -ForegroundColor Green

# --- Auto-logon dla btrender ---
Write-Host ""
Write-Host "UWAGA: Auto-logon wymaga recznej konfiguracji:" -ForegroundColor Yellow
Write-Host "  1. Uruchom: netplwiz" -ForegroundColor Yellow
Write-Host "  2. Odznacz 'Users must enter a user name and password'" -ForegroundColor Yellow
Write-Host "  3. Wybierz PRI\btrender i podaj haslo" -ForegroundColor Yellow
Write-Host "  Lub uzyj Autologon.exe z Sysinternals (bezpieczniejsze - szyfruje haslo)" -ForegroundColor Yellow
Write-Host ""

# --- Podsumowanie ---
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Podsumowanie:" -ForegroundColor Cyan
Write-Host "  Task 1: ForexBot - MetaTrader5  (at logon)" -ForegroundColor White
Write-Host "  Task 2: ForexBot - AI Bot v1.3  (at logon + 30s delay)" -ForegroundColor White
Write-Host "         Auto-restart: co 2 min, max 999 prób" -ForegroundColor White
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Sprawdz taski: Get-ScheduledTask | Where TaskName -like 'ForexBot*'" -ForegroundColor Gray
