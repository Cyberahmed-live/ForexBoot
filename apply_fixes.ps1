#!/usr/bin/env powershell
# Script to apply database fixes for large losses issue
# Target: appdbpri server, ForexBotDB database

$server = "appdbpri"
$database = "ForexBotDB"
$sqlFile = "c:\Program Files\Python310\forex_env\forex_data\fix_large_losses.sql"

Write-Host "🔧 Applying fixes to ForexBotDB on appdbpri" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan

# Check if SQL file exists
if (!(Test-Path $sqlFile)) {
    Write-Host "❌ SQL file not found: $sqlFile" -ForegroundColor Red
    exit 1
}

# Try to connect and execute
try {
    Write-Host "`n📌 Server: $server" -ForegroundColor Yellow
    Write-Host "📌 Database: $database" -ForegroundColor Yellow
    Write-Host "📌 Script: $sqlFile" -ForegroundColor Yellow
    
    # Read SQL file
    $sqlContent = Get-Content $sqlFile -Raw
    
    # Execute SQL
    Write-Host "`n⏳ Executing SQL commands..." -ForegroundColor Cyan
    Invoke-Sqlcmd -ServerInstance $server -Database $database -InputFile $sqlFile -ErrorAction Stop
    
    Write-Host "`n✅ Database fixes applied successfully!" -ForegroundColor Green
    Write-Host "`n📋 Applied changes:" -ForegroundColor Green
    Write-Host "   ✓ Blacklist symbols updated (GBPCHF)" -ForegroundColor Green
    Write-Host "   ✓ Lot size reduced to 0.3" -ForegroundColor Green
    Write-Host "   ✓ TIME_EXIT_HOURS reduced to 8h" -ForegroundColor Green
    Write-Host "   ✓ Confidence thresholds for JPY pairs increased" -ForegroundColor Green
    Write-Host "   ✓ NPM_ALERT_R adjusted to -0.5" -ForegroundColor Green
    Write-Host "   ✓ MAX_DAILY_LOSSES set to 2" -ForegroundColor Green
    
    Write-Host "`n⚠️  IMPORTANT: Restart the bot to load new configuration!" -ForegroundColor Yellow
    Write-Host "   Command: python forex_ai_bot_v1.3.py" -ForegroundColor Yellow
    
} catch {
    Write-Host "`n❌ Error applying SQL: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "`n💡 Troubleshooting:" -ForegroundColor Yellow
    Write-Host "   • Verify SQL Server is running" -ForegroundColor Yellow
    Write-Host "   • Check appdbpri server is reachable" -ForegroundColor Yellow
    Write-Host "   • Verify ForexBotDB exists" -ForegroundColor Yellow
    Write-Host "   • Check user has appropriate permissions" -ForegroundColor Yellow
    exit 1
}

Write-Host "`n================================================" -ForegroundColor Cyan
Write-Host "✅ Process completed" -ForegroundColor Cyan
