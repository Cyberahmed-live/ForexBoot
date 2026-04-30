# ============================================================================
# FOREX AI BOT - PRODUCTION DEPLOYMENT SCRIPT
# ============================================================================
# Purpose: Synchronize local development to production environment on Appdbpri
# Production Location: \\Appdbpri\c$\Program Files\Python310\forex_env
# Database: appdbpri (MSSQL Server)
# 
# Usage: .\deploy_production.ps1
# ============================================================================

param(
    [switch]$Verify = $false,
    [switch]$DryRun = $false
)

$ErrorActionPreference = "Stop"

$SOURCE = "c:\Program Files\Python310\forex_env"
$PROD = "\\Appdbpri\c$\Program Files\Python310\forex_env"
$DB_HOST = "appdbpri"
$DB_NAME = "ForexBotDB"

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "      FOREX AI BOT - PRODUCTION DEPLOYMENT" -ForegroundColor Cyan
Write-Host "      $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan

Write-Host ""
Write-Host "[SOURCE (Local):      ] $SOURCE" -ForegroundColor Yellow
Write-Host "[TARGET (Production): ] $PROD" -ForegroundColor Yellow
Write-Host "[DATABASE:           ] $DB_HOST\$DB_NAME" -ForegroundColor Yellow

if ($DryRun) {
    Write-Host "[MODE: DRY RUN - No files will be modified]" -ForegroundColor Magenta
}

Write-Host ""

# Verify source exists
if (!(Test-Path $SOURCE)) {
    Write-Host "[ERROR] Source directory not found: $SOURCE" -ForegroundColor Red
    exit 1
}

# Verify production is accessible
try {
    Test-Path $PROD -ErrorAction Stop | Out-Null
} catch {
    Write-Host "[ERROR] Cannot access production server" -ForegroundColor Red
    Write-Host "   Path: $PROD" -ForegroundColor Red
    Write-Host "   Verify network access to Appdbpri and credentials" -ForegroundColor Red
    exit 1
}

$deploySteps = @()

# === STEP 1: Main Bot File ===
$deploySteps += @{
    Name = "Main Bot File"
    Source = "$SOURCE\forex_ai_bot_v1.3.py"
    Target = "$PROD\forex_ai_bot_v1.3.py"
    Type = "File"
}

# === STEP 2: Core Modules ===
$modules = @("forex_base", "forex_v14", "forex_dashboard")
foreach ($mod in $modules) {
    $deploySteps += @{
        Name = "$mod (Module)"
        Source = "$SOURCE\$mod"
        Target = "$PROD\$mod"
        Type = "Directory"
    }
}

# === STEP 3: Documentation ===
$docs = @("FIX_LARGE_LOSSES.md", "IMPLEMENTATION_SUMMARY.txt", "PRODUCTION_INVENTORY.md")
foreach ($doc in $docs) {
    $deploySteps += @{
        Name = "$doc"
        Source = "$SOURCE\$doc"
        Target = "$PROD\$doc"
        Type = "File"
    }
}

# === EXECUTE DEPLOYMENT ===
Write-Host "[DEPLOYMENT PLAN]" -ForegroundColor Green
Write-Host ""

$successCount = 0
$failCount = 0
$startTime = Get-Date

for ($i = 0; $i -lt $deploySteps.Count; $i++) {
    $step = $deploySteps[$i]
    $stepNum = $i + 1
    
    Write-Host "[$stepNum/$($deploySteps.Count)] $($step.Name)..."
    
    try {
        if (!$DryRun) {
            if ($step.Type -eq "Directory") {
                if (!(Test-Path $step.Target)) {
                    New-Item -ItemType Directory -Path $step.Target -Force | Out-Null
                }
                Copy-Item "$($step.Source)\*" "$($step.Target)\" -Force -Recurse
            } else {
                Copy-Item $step.Source $step.Target -Force
            }
        }
        Write-Host "           [OK]" -ForegroundColor Green
        $successCount++
    } catch {
        Write-Host "           [FAILED] $_" -ForegroundColor Red
        $failCount++
    }
}

# === CLEANUP PRODUCTION DEBUG FILES ===
Write-Host ""
Write-Host "[DEBUG CLEANUP] Removing test/debug files from production..."

$DEBUG_SCRIPTS = @(
    "analyze_transaction.py",
    "check_logs.py",
    "check_mt5_status.py",
    "check_mt5_transaction.py",
    "find_transaction.py",
    "fix_db_writer.py",
    "tst.py",
    "apply_fixes.ps1",
    "deploy.ps1"
)

$cleanupCount = 0
foreach ($file in $DEBUG_SCRIPTS) {
    $path = "$PROD\$file"
    if (Test-Path $path) {
        if (!$DryRun) {
            Remove-Item $path -Force -ErrorAction SilentlyContinue
        }
        Write-Host "           [REMOVED] $file" -ForegroundColor DarkGray
        $cleanupCount++
    }
}

# === VERIFY DEPLOYMENT ===
if ($Verify) {
    Write-Host ""
    Write-Host "[VERIFICATION]" -ForegroundColor Cyan
    
    $prodBotFile = Get-Item "$PROD\forex_ai_bot_v1.3.py" -ErrorAction SilentlyContinue
    if ($prodBotFile) {
        $localBotFile = Get-Item "$SOURCE\forex_ai_bot_v1.3.py"
        if ($prodBotFile.Length -eq $localBotFile.Length) {
            Write-Host "   [OK] Bot file size matches" -ForegroundColor Green
        } else {
            Write-Host "   [WARNING] Bot file size mismatch!" -ForegroundColor Yellow
            Write-Host "      Local:  $($localBotFile.Length) bytes" -ForegroundColor Yellow
            Write-Host "      Remote: $($prodBotFile.Length) bytes" -ForegroundColor Yellow
        }
    }
}

# === SUMMARY ===
$endTime = Get-Date
$duration = ($endTime - $startTime).TotalSeconds

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "                    DEPLOYMENT SUMMARY" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan

Write-Host ""
Write-Host "[RESULTS]"
Write-Host "   Successful:  $successCount items" -ForegroundColor Green
Write-Host "   Failed:      $failCount items" -ForegroundColor $(if ($failCount -gt 0) { "Red" } else { "Green" })
Write-Host "   Cleanup:     $cleanupCount debug files removed" -ForegroundColor DarkGray
Write-Host "   Duration:    $([Math]::Round($duration, 2))s" -ForegroundColor Yellow

if ($DryRun) {
    Write-Host ""
    Write-Host "   [NOTE] DRY RUN - No changes were made" -ForegroundColor Magenta
}

Write-Host ""
Write-Host "[DATABASE CONNECTION]"
Write-Host "   Server:      $DB_HOST" -ForegroundColor DarkGray
Write-Host "   Database:    $DB_NAME" -ForegroundColor DarkGray

Write-Host ""
Write-Host "[IMPORTANT NOTES]"
Write-Host "   * After deployment, restart the bot on Appdbpri to apply changes" -ForegroundColor Yellow
Write-Host "   * Configuration is in: $DB_HOST\$DB_NAME (bot_config table)" -ForegroundColor Yellow
Write-Host "   * Check: appdbpri:ForexBotDB.bot_logs for deployment verification" -ForegroundColor Yellow

Write-Host ""

if ($failCount -gt 0) {
    Write-Host "[FAILED] DEPLOYMENT COMPLETED WITH ERRORS" -ForegroundColor Red
    exit 1
} else {
    Write-Host "[SUCCESS] DEPLOYMENT COMPLETED" -ForegroundColor Green
    exit 0
}
