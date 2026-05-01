# ============================================================================
# FOREX AI BOT - UNIFIED DEPLOYMENT SCRIPT
# ============================================================================
# Srodowisko produkcyjne:
#   OS        : Windows Server 2025
#   Python    : 3.10 (C:\Program Files\Python310)
#   MT5       : MetaTrader 5 (terminal64.exe)
#   Produkcja : \\Appdbpri\c$\Program Files\Python310\forex_env  (dysk B:)
#   Baza DB   : appdbpri\ForexBotDB  (MSSQL, Windows Auth)
#   Konto     : PRI\btrender
#
# Uzycie:
#   .\deploy.ps1                     Pelny deploy wszystkich modulow
#   .\deploy.ps1 -DryRun             Symulacja (brak zmian)
#   .\deploy.ps1 -Files "plik1,plik2" Wybrany zestaw plikow
#   .\deploy.ps1 -Verify             Deploy + weryfikacja rozmiaru
#   .\deploy.ps1 -SetupTasks         Skonfiguruj Task Scheduler na serwerze
#
# Git workflow (OBOWIAZKOWY):
#   1. Po zmianach lokalnych        : git add . ; git commit -m "opis" ; git push origin dev
#   2. Po wdrozeniu na produkcje    : git push origin dev
#   3. Po wdrozeniu na produkcje    : git checkout main ; git merge dev ; git push origin main ; git checkout dev
# ============================================================================

param(
    [string]$Files = "",
    [switch]$DryRun,
    [switch]$Verify,
    [switch]$SetupTasks
)

$ErrorActionPreference = "Stop"

$DEV      = "C:\Program Files\Python310\forex_env"
$PROD_UNC = "\\Appdbpri\c$\Program Files\Python310\forex_env"
$PROD     = "B:"
$DB_HOST  = "appdbpri"
$DB_NAME  = "ForexBotDB"
$BOT_USER = "PRI\btrender"
$PYTHON   = "C:\Program Files\Python310\python.exe"
$MT5      = "C:\Program Files\MetaTrader 5\terminal64.exe"

# Pliki wdrazane domyslnie (pelny deploy)
$DEFAULT_FILES = @(
    "forex_ai_bot_v1.3.py",
    "forex_v14\db_writer.py",
    "forex_v14\wisdom_aggregator.py",
    "forex_base\globalcfg.py",
    "forex_base\train_forex_ai_model_v1_2.py",
    "forex_base\indicators.py",
    "forex_base\formation_detection.py",
    "forex_base\tran_logs.py",
    "forex_base\common.py",
    "start.bat"
)

# Katalogi wdrazane w calosci (rekurencyjnie)
$DEFAULT_DIRS = @("forex_dashboard")

# Pliki debugowe do usuniecia z produkcji
$DEBUG_FILES = @(
    "analyze_transaction.py", "check_logs.py", "check_mt5_status.py",
    "check_mt5_transaction.py", "find_transaction.py", "fix_db_writer.py",
    "tst.py", "apply_fixes.ps1", "deploy_production.ps1", "setup_tasks.ps1"
)

# ===========================================================================
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "      FOREX AI BOT - DEPLOY NA PRODUKCJE" -ForegroundColor Cyan
Write-Host "      $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "  Zrodlo (DEV) : $DEV" -ForegroundColor Yellow
Write-Host "  Cel (PROD)   : $PROD_UNC" -ForegroundColor Yellow
Write-Host "  Baza danych  : $DB_HOST\$DB_NAME" -ForegroundColor Yellow
if ($DryRun) { Write-Host "  [TRYB: DRY RUN - zadne pliki nie zostana zmienione]" -ForegroundColor Magenta }
Write-Host ""

# --- Mapowanie dysku B: ---
if (-not (Test-Path "$PROD\")) {
    Write-Host "Mapowanie dysku B: -> $PROD_UNC ..." -ForegroundColor Yellow
    net use B: /delete /y 2>&1 | Out-Null
    $result = net use B: $PROD_UNC /persistent:no 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[BLAD] Nie mozna zmapowac dysku B: -- $result" -ForegroundColor Red
        Write-Host "       Sprawdz dostep sieciowy do Appdbpri i uprawnienia." -ForegroundColor Red
        exit 1
    }
    Write-Host "  OK: B: zmapowany." -ForegroundColor Green
}

# ===========================================================================
# SEKCJA 0: AUTO-INCREMENT WERSJI (BOT_VERSION w forex_ai_bot_v1.3.py)
# ===========================================================================
$botFile = "$DEV\forex_ai_bot_v1.3.py"
$versionUpdated = $false

if (Test-Path $botFile) {
    $botContent = Get-Content $botFile -Raw -Encoding UTF8
    if ($botContent -match 'BOT_VERSION\s*=\s*"1\.3\.(\d+)\.(\d+)"') {
        $verX = [int]$Matches[1]
        $verY = [int]$Matches[2]
        $oldVersion = "1.3.$verX.$verY"

        if (-not $DryRun) {
            $verY++
            if ($verY -gt 99) { $verX++; $verY = 1 }
            $newVersion = "1.3.$verX.$verY"
            $botContent = $botContent -replace 'BOT_VERSION\s*=\s*"1\.3\.\d+\.\d+"', "BOT_VERSION             = `"$newVersion`"                                      # Wersja bota (auto-increment przy deploy)"
            [System.IO.File]::WriteAllText($botFile, $botContent, [System.Text.Encoding]::UTF8)
            Write-Host "  Wersja : $oldVersion  ->  $newVersion" -ForegroundColor Cyan
            $versionUpdated = $true
        } else {
            $verY++
            if ($verY -gt 99) { $verX++; $verY = 1 }
            $newVersion = "1.3.$verX.$verY"
            Write-Host "  Wersja : $oldVersion  ->  $newVersion  [DRY RUN - brak zmiany]" -ForegroundColor Magenta
        }
    } else {
        Write-Host "  UWAGA: Nie znaleziono BOT_VERSION w pliku bota - pomijam increment." -ForegroundColor Yellow
    }
}
Write-Host ""

# ===========================================================================
# SEKCJA A: SETUP TASK SCHEDULER (opcjonalnie, flaga -SetupTasks)
# ===========================================================================
if ($SetupTasks) {
    Write-Host ""
    Write-Host "[SETUP] Konfiguracja Task Scheduler na serwerze produkcyjnym..." -ForegroundColor Cyan

    # Task 1: MetaTrader 5
    $mt5Action   = New-ScheduledTaskAction -Execute $MT5
    $mt5Trigger  = New-ScheduledTaskTrigger -AtLogOn -User $BOT_USER
    $mt5Settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -StartWhenAvailable -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit (New-TimeSpan -Days 365)
    Register-ScheduledTask `
        -TaskName "ForexBot - MetaTrader5" -Action $mt5Action `
        -Trigger $mt5Trigger -Settings $mt5Settings `
        -User $BOT_USER -RunLevel Limited `
        -Description "Uruchamia MetaTrader 5 przy logowaniu uzytkownika btrender" -Force
    Write-Host "  OK: Task 'ForexBot - MetaTrader5' utworzony." -ForegroundColor Green

    # Task 2: Forex AI Bot (30s opoznienie - czeka na MT5)
    $botAction  = New-ScheduledTaskAction `
        -Execute $PYTHON -Argument "forex_ai_bot_v1.3.py" `
        -WorkingDirectory "$PROD\"
    $botTrigger = New-ScheduledTaskTrigger -AtLogOn -User $BOT_USER
    $botTrigger.Delay = "PT30S"
    $botSettings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -StartWhenAvailable -RestartCount 999 `
        -RestartInterval (New-TimeSpan -Minutes 2) `
        -ExecutionTimeLimit (New-TimeSpan -Days 365)
    Register-ScheduledTask `
        -TaskName "ForexBot - AI Bot v1.3" -Action $botAction `
        -Trigger $botTrigger -Settings $botSettings `
        -User $BOT_USER -RunLevel Limited `
        -Description "Uruchamia Forex AI Bot v1.3 (Python) 30s po logowaniu. Auto-restart co 2 min." -Force
    Write-Host "  OK: Task 'ForexBot - AI Bot v1.3' utworzony." -ForegroundColor Green

    Write-Host ""
    Write-Host "UWAGA: Auto-logon wymaga recznej konfiguracji (netplwiz lub Autologon.exe)." -ForegroundColor Yellow
}

# ===========================================================================
# SEKCJA B: KOPIOWANIE PLIKOW
# ===========================================================================
Write-Host "[DEPLOY] Kopiowanie plikow..." -ForegroundColor Cyan

if ($Files -ne "") {
    $fileList = $Files -split "," | ForEach-Object { $_.Trim() }
    $dirList  = @()
} else {
    $fileList = $DEFAULT_FILES
    $dirList  = $DEFAULT_DIRS
}

$ok = 0
$fail = 0
$startTime = Get-Date

foreach ($file in $fileList) {
    $src  = Join-Path $DEV  $file
    $dest = Join-Path $PROD $file
    if (-not (Test-Path $src)) {
        Write-Host "  BRAK : $file" -ForegroundColor Red
        $fail++; continue
    }
    $destDir = Split-Path $dest -Parent
    if (-not $DryRun -and -not (Test-Path $destDir)) {
        New-Item -ItemType Directory -Path $destDir -Force | Out-Null
    }
    if ($DryRun) {
        Write-Host "  DRY  : $file" -ForegroundColor Yellow; $ok++
    } else {
        try {
            Copy-Item -Path $src -Destination $dest -Force
            Write-Host "  OK   : $file" -ForegroundColor Green; $ok++
        } catch {
            Write-Host "  BLAD : $file -- $_" -ForegroundColor Red; $fail++
        }
    }
}

foreach ($dir in $dirList) {
    $src  = Join-Path $DEV  $dir
    $dest = Join-Path $PROD $dir
    if (-not (Test-Path $src)) {
        Write-Host "  BRAK : $dir\" -ForegroundColor Red
        $fail++; continue
    }
    if ($DryRun) {
        Write-Host "  DRY  : $dir\" -ForegroundColor Yellow; $ok++
    } else {
        try {
            if (-not (Test-Path $dest)) { New-Item -ItemType Directory -Path $dest -Force | Out-Null }
            Copy-Item "$src\*" "$dest\" -Recurse -Force
            Write-Host "  OK   : $dir\" -ForegroundColor Green; $ok++
        } catch {
            Write-Host "  BLAD : $dir\ -- $_" -ForegroundColor Red; $fail++
        }
    }
}

# --- Czyszczenie plikow debugowych z produkcji ---
Write-Host ""
Write-Host "[CLEANUP] Usuwanie plikow debug z produkcji..." -ForegroundColor DarkGray
$cleaned = 0
foreach ($f in $DEBUG_FILES) {
    $path = Join-Path $PROD $f
    if (Test-Path $path) {
        if (-not $DryRun) { Remove-Item $path -Force -ErrorAction SilentlyContinue }
        Write-Host "  REMOVED: $f" -ForegroundColor DarkGray
        $cleaned++
    }
}

# --- Weryfikacja ---
if ($Verify) {
    Write-Host ""
    Write-Host "[VERIFY]" -ForegroundColor Cyan
    $botLocal = Get-Item "$DEV\forex_ai_bot_v1.3.py" -ErrorAction SilentlyContinue
    $botProd  = Get-Item "$PROD\forex_ai_bot_v1.3.py" -ErrorAction SilentlyContinue
    if ($botLocal -and $botProd) {
        if ($botLocal.Length -eq $botProd.Length) {
            Write-Host "  OK: Rozmiar pliku bota zgodny ($($botLocal.Length) B)" -ForegroundColor Green
        } else {
            Write-Host "  UWAGA: Roznica rozmiarow! Local=$($botLocal.Length) Prod=$($botProd.Length)" -ForegroundColor Yellow
        }
    } else {
        Write-Host "  UWAGA: Nie mozna zweryfikowac pliku bota." -ForegroundColor Yellow
    }
}

# ===========================================================================
# PODSUMOWANIE
# ===========================================================================
$duration = [Math]::Round(((Get-Date) - $startTime).TotalSeconds, 2)
Write-Host ""
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "  Skopiowano : $ok  |  Bledy: $fail  |  Debug usunieto: $cleaned  |  Czas: ${duration}s"
Write-Host "  Baza DB    : $DB_HOST\$DB_NAME  (Windows Auth)" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  PO DEPLOYMENCIE - git workflow:" -ForegroundColor Yellow
Write-Host "    git add . ; git commit -m 'deploy prod $(Get-Date -Format yyyy-MM-dd)'" -ForegroundColor Yellow
Write-Host "    git push origin dev" -ForegroundColor Yellow
Write-Host "    git checkout main ; git merge dev ; git push origin main ; git checkout dev" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Nastepnie zrestartuj bota na Appdbpri (lub poczekaj do 23:59)." -ForegroundColor Yellow
Write-Host "======================================================================" -ForegroundColor Cyan

if ($fail -eq 0) {
    Write-Host "  [SUCCESS] DEPLOYMENT ZAKONCZONY POMYSLNIE" -ForegroundColor Green
    exit 0
} else {
    Write-Host "  [FAILED]  DEPLOYMENT Z BLEDAMI - sprawdz powyzej" -ForegroundColor Red
    exit 1
}

