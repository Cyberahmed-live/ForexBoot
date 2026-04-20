param(
    [string]$Files = "",
    [switch]$DryRun
)

$PROD     = "B:"
$DEV      = "C:\Program Files\Python310\forex_env"
$PROD_UNC = "\\Appdbpri\c$\Program Files\Python310\forex_env"

$DEFAULT_FILES = @(
    "forex_ai_bot_v1.3.py",
    "forex_v14\db_writer.py",
    "forex_v14\wisdom_aggregator.py",
    "forex_base\globalcfg.py",
    "forex_base\train_forex_ai_model_v1_2.py"
)

# Auto-remap B: jesli niedostepny
if (-not (Test-Path "$PROD\")) {
    Write-Host "Mapowanie dysku B: -> $PROD_UNC ..." -ForegroundColor Yellow
    $result = net use B: $PROD_UNC /persistent:no 2>&1
    if ($LASTEXITCODE -ne 0) {
        # Sprobuj usunac i zmapowac ponownie
        net use B: /delete /y 2>&1 | Out-Null
        $result = net use B: $PROD_UNC /persistent:no 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Nie mozna zmapowac dysku B: -- $result"
            exit 1
        }
    }
    Write-Host "  OK: B: zmapowany." -ForegroundColor Green
}

if ($Files -ne "") {
    $fileList = $Files -split "," | ForEach-Object { $_.Trim() }
} else {
    $fileList = $DEFAULT_FILES
}

$ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
Write-Host "=== Deploy na produkcje $ts ===" -ForegroundColor Cyan
if ($DryRun) { Write-Host "[DRY RUN]" -ForegroundColor Yellow }

$ok = 0
$fail = 0

foreach ($file in $fileList) {
    $src  = Join-Path $DEV  $file
    $dest = Join-Path $PROD $file

    if (-not (Test-Path $src)) {
        Write-Host "  BRAK:  $file" -ForegroundColor Red
        $fail++
        continue
    }

    $destDir = Split-Path $dest -Parent
    if (-not (Test-Path $destDir)) {
        if (-not $DryRun) { New-Item -ItemType Directory -Path $destDir -Force | Out-Null }
    }

    if ($DryRun) {
        Write-Host "  DRY:   $file" -ForegroundColor Yellow
        $ok++
    } else {
        try {
            Copy-Item -Path $src -Destination $dest -Force
            Write-Host "  OK:    $file" -ForegroundColor Green
            $ok++
        } catch {
            Write-Host "  BLAD:  $file -- $_" -ForegroundColor Red
            $fail++
        }
    }
}

Write-Host ""
if ($fail -eq 0) {
    Write-Host "Wynik: $ok OK" -ForegroundColor Green
} else {
    Write-Host "Wynik: $ok OK, $fail BLAD" -ForegroundColor Yellow
}