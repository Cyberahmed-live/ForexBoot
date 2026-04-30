# 🏭 PRODUCTION APPLICATION INVENTORY

**Generated:** 2026-04-30  
**Environment (Local):** c:\Program Files\Python310\forex_env  
**Environment (Production/Disk B):** \\Appdbpri\c$\Program Files\Python310\forex_env  
**Database Server:** appdbpri  
**Database Name:** ForexBotDB  
**Git Version:** fd1ae4d (Dynamic Negative Trailing Stop)  
**Status:** ACTIVE - Forex AI Bot v1.3 Trading System

---

## 🔐 PRODUCTION INFRASTRUCTURE

### Server Details
- **Hostname:** Appdbpri
- **Network Path:** \\Appdbpri\c$\Program Files\Python310\forex_env
- **Disk:** B (symlinked as C$ share on Appdbpri)
- **Database:** MSSQL Server running on appdbpri
- **Database Name:** ForexBotDB
- **Critical Tables:**
  - `bot_config` - All runtime parameters (blacklist, lot sizes, thresholds, etc.)
  - `bot_logs` - Trading activity and diagnostic logs
  - `trades` - Individual trade records
  - `wisdom_observations` - Market observation tracking

### Connection Info
```
Server: appdbpri
Database: ForexBotDB
Port: 1433 (default MSSQL)
Auth: Windows Integrated (via pyodbc)
```

---

## 🚀 DEPLOYMENT PROCESS

### Automated Deployment Script
**File:** `deploy_production.ps1`

**Purpose:** Safely synchronize local development to production server

**Usage:**
```powershell
# Standard deployment (will sync and cleanup)
.\deploy_production.ps1

# Dry run (preview without making changes)
.\deploy_production.ps1 -DryRun

# Deployment with verification
.\deploy_production.ps1 -Verify
```

**What It Does:**
1. Copies `forex_ai_bot_v1.3.py` (latest version)
2. Syncs all modules: `forex_base/`, `forex_v14/`, `forex_dashboard/`
3. Updates documentation files
4. Removes debug/test scripts from production
5. Verifies file integrity (optional)
6. Reports deployment status

**Important:** After deployment, **restart the bot** on Appdbpri to load new code.

### Manual Deployment Steps (if script fails)
```powershell
# 1. Connect to production
cd \\Appdbpri\c$\Program Files\Python310\forex_env

# 2. Backup current bot (optional)
Copy-Item forex_ai_bot_v1.3.py "forex_ai_bot_v1.3_backup_$(Get-Date -f yyyyMMdd_HHmmss).py"

# 3. Sync from local
Copy-Item C:\Program Files\Python310\forex_env\forex_ai_bot_v1.3.py . -Force
Copy-Item C:\Program Files\Python310\forex_env\forex_base\* .\forex_base\ -Recurse -Force
Copy-Item C:\Program Files\Python310\forex_env\forex_v14\* .\forex_v14\ -Recurse -Force

# 4. Verify
ls *.py
```

### Preventing Missed Updates

**Problem:** Code changes on local but not deployed to production → bot runs old code

**Prevention Checklist:**
1. ✅ After `git push` to main: Run `deploy_production.ps1`
2. ✅ Check `appdbpri:ForexBotDB.bot_logs` for "Bot started" messages (shows version)
3. ✅ Verify bot is running new code before leaving terminal
4. ✅ Document deployment in a log file

**Automated Check:**
```powershell
# Add this to pre-commit hook or deployment checklist
$localVersion = Get-FileHash C:\Program Files\Python310\forex_env\forex_ai_bot_v1.3.py
$prodVersion = Get-FileHash \\Appdbpri\c$\Program Files\Python310\forex_env\forex_ai_bot_v1.3.py

if ($localVersion.Hash -ne $prodVersion.Hash) {
    Write-Host "⚠️ ALERT: Local and production versions DO NOT MATCH"
    Write-Host "   Run: deploy_production.ps1"
}
```

---

## 📦 CORE APPLICATION FILES (REQUIRED)

### Main Application
- **forex_ai_bot_v1.3.py** (v1.3) - PRIMARY TRADING BOT
  - Entry point for all trading operations
  - 1600+ lines, handles ML predictions, position management, NPM, trailing stops
  - Config: Loaded dynamically from appdbpri/ForexBotDB

### Application Modules (forex_base/)
- **common.py** - Common utilities (format_time, MT5 connection helpers)
- **indicators.py** - Technical indicators (ATR, Fibo, formations)
- **formation_detection.py** - Candle formation detection
- **globalcfg.py** - Database config loader (get_global_cfg function)
- **tran_logs.py** - Trade logging to SQL Server
- **train_forex_ai_model_v1_2.py** - Model training pipeline

### v1.4 Wisdom System (forex_v14/)
- **wisdom_aggregator.py** - Market observation tracking
- **db_writer.py** - MSSQLWriter for database operations

### Dashboard
- **forex_dashboard/forex_dashboard.py** - Dashboard application
- **forex_dashboard/dashboard.html** - Dashboard UI

### Runtime Configuration
- **pyvenv.cfg** - Python virtual environment config

---

## 📊 DATA & MODELS

### Historical Data (forex_data/)
- **SYMBOL.csv** - Historical OHLC data (training data)
- **SYMBOL.pro.csv** - Professional/pre-processed data
- Coverage: 50+ FX pairs + commodities (AUD, GBP, EUR, USD, NZD, CHF, JPY, XAUUSD, XAGUSD, Gold, Silver)

### Trained Models (forex_models/)
- **SYMBOL_model.pkl** - Scikit-learn ML models (XGBoost/Random Forest)
- **SYMBOL_scaler.pkl** - Feature scalers (StandardScaler)
- **SYMBOL_feature_columns.pkl** - Feature definitions

### Database Scripts (forex_data/)
- **create_forexbot_db.sql** - Schema creation (one-time, archived reference)
- **fix_large_losses.sql** - Configuration fixes (reference documentation)

---

## 📋 DOCUMENTATION

### Configuration & Fixes
- **FIX_LARGE_LOSSES.md** - Issue #2997158 analysis and solutions
- **IMPLEMENTATION_SUMMARY.txt** - Quick reference for all fixes

### Logs
- **forex_logs/forex_bot_YYYY-MM-DD.log** - Daily trading logs
  - Current active: forex_bot_2026-04-16.log
  - Archive: 2026-04-12 through 2026-04-15

---

## 🗑️ UNUSED/TEST FILES (CANDIDATES FOR REMOVAL)

### Backup Files (NOT IN GIT)
- **forex_ai_bot_v1.3 - Copy.py** - ⚠️ REMOVE: Duplicate backup
- **dashboard - Copy.html** - ⚠️ REMOVE: Duplicate backup

### Debugging Scripts (Testing Only)
- **analyze_transaction.py** - ⚠️ REMOVE: One-off transaction analysis
- **check_logs.py** - ⚠️ REMOVE: Log debugging utility
- **check_mt5_status.py** - ⚠️ REMOVE: MT5 status check
- **check_mt5_transaction.py** - ⚠️ REMOVE: MT5 transaction lookup
- **find_transaction.py** - ⚠️ REMOVE: Transaction search utility
- **fix_db_writer.py** - ⚠️ REMOVE: DB writer debugging
- **tst.py** - ⚠️ REMOVE: Test script

### Deployment Scripts (One-Time Use)
- **apply_fixes.ps1** - ⚠️ REMOVE: One-time SQL deployment (documented in FIX_LARGE_LOSSES.md)
- **deploy.ps1** - ⚠️ REMOVE: One-time deployment script
- **setup_tasks.ps1** - ⚠️ REMOVE: Setup script

### Launch Scripts (Redundant)
- **start.bat** - ⚠️ REVIEW: Use start_dashboard.bat or direct python command
- **start_dashboard.bat** - ✅ KEEP: Dashboard launcher

### Auto-Generated (Safe to Remove)
- **forex_base/__pycache__/*.pyc** - ⚠️ REMOVE: Python compiled cache
- **max_profit_dict.pkl** - ⚠️ REMOVE: Runtime cache file
- **.vs/** - ⚠️ REMOVE: Visual Studio metadata

### Archive Logs (Keep 7 Days)
- **forex_logs/forex_bot_2026-04-12.log** - ⚠️ ARCHIVE: 18 days old
- **forex_logs/forex_bot_2026-04-13.log** - ⚠️ ARCHIVE: 17 days old
- **forex_logs/forex_bot_2026-04-14.log** - ⚠️ ARCHIVE: 16 days old
- **forex_logs/forex_bot_2026-04-15.log** - ⚠️ ARCHIVE: 15 days old

---

## 🔐 VERSION CONTROL STATUS

```
Branch: main
Latest: fd1ae4d - ✨ FEATURE: Dynamic Negative Trailing Stop
Status: All files committed, working tree clean
Remote: Up to date with origin/main
```

### Recent Commits
1. fd1ae4d - Dynamic Negative Trailing Stop for loss management
2. b2d27b3 - Blacklist safety checks and diagnostic logging
3. de67f6f - Confidence threshold stratification (0.60-0.75 LOT_MIN)
4. 63e9c51 - FIX: Large loss issue #2997158
5. d159be0 - Per-symbol confidence threshold

---

## 📊 CURRENT CONFIGURATION (appdbpri/ForexBotDB)

**Active Parameters:**
- `blacklist_symbols = 'GBPCHF,GBPJPY,EURJPY,CHFJPY'` - Disabled pairs
- `lot = 0.3` - Reduced position size
- `min_lot = 0.20` - Minimum lot for weak signals
- `conf_threshold_min = 0.60` - Skip below this
- `conf_threshold_normal = 0.75` - Normal threshold
- `trail_neg_active_r = -0.5` - Activate negative trailing
- `trail_neg_max_loss_r = -2.0` - Hard cap on losses
- `time_exit_hours = 8` - Close negative positions after 8h

---

## 🚀 SAFE CLEANUP PLAN

### Priority 1: DELETE (Safe - Not in Git)
```
❌ forex_ai_bot_v1.3 - Copy.py
❌ dashboard - Copy.html
❌ max_profit_dict.pkl
```

### Priority 2: DELETE (Debugging/One-Time - In Git but documented)
```
❌ analyze_transaction.py
❌ check_logs.py
❌ check_mt5_status.py
❌ check_mt5_transaction.py
❌ find_transaction.py
❌ fix_db_writer.py
❌ tst.py
❌ apply_fixes.ps1
❌ deploy.ps1
❌ setup_tasks.ps1
```

### Priority 3: ARCHIVE (Logs older than 7 days)
```
📦 forex_logs/forex_bot_2026-04-12.log
📦 forex_logs/forex_bot_2026-04-13.log
📦 forex_logs/forex_bot_2026-04-14.log
📦 forex_logs/forex_bot_2026-04-15.log
→ Archive to: c:\Program Files\Python310\forex_env\forex_logs_archive\
```

### Priority 4: CLEAN (Auto-generated, safe)
```
🗑️ forex_base/__pycache__/
🗑️ .vs/
```

### Priority 5: REVIEW
```
📋 start.bat - Keep or use start_dashboard.bat?
```

---

## ✅ PRODUCTION-READY FILES (DO NOT REMOVE)

```
✅ forex_ai_bot_v1.3.py
✅ forex_base/*.py
✅ forex_v14/*.py
✅ forex_dashboard/
✅ forex_models/*.pkl
✅ forex_data/*.sql
✅ forex_data/*.csv
✅ forex_logs/
✅ pyvenv.cfg
✅ start_dashboard.bat
✅ FIX_LARGE_LOSSES.md
✅ IMPLEMENTATION_SUMMARY.txt
✅ PRODUCTION_INVENTORY.md (this file)
```

---

## 📌 NOTES

- All debugging scripts exist in GitHub (can be restored if needed)
- Logs auto-rotate daily (log file per date)
- Models are pre-trained and actively used by bot
- Configuration is entirely database-driven (appdbpri)
- No sensitive data in version control

---

**Last Reviewed:** 2026-04-30  
**Last Deployed:** 2026-04-30 20:20:11 (commit fd1ae4d)  
**Next Cleanup:** 2026-05-07 (archive logs older than 7 days)

### Deployment Log
```
2026-04-30 20:20:11 - ✅ DEPLOYED commit fd1ae4d
  - Updated: forex_ai_bot_v1.3.py
  - Updated: forex_base/*, forex_v14/*, forex_dashboard/*
  - Updated: Documentation (FIX_LARGE_LOSSES.md, IMPLEMENTATION_SUMMARY.txt)
  - Cleaned: Removed debug scripts (tst.py, setup_tasks.ps1)
  - Status: Production ready ✓
  
2026-04-30 - ✅ Created deploy_production.ps1 script
  - Automated deployment to \\Appdbpri\c$\Program Files\Python310\forex_env
  - Includes verification and cleanup
  - Prevents missed updates

2026-04-30 21:00+ - ✅ CRITICAL BLACKLIST BUG FIX & DEPLOYMENT SUCCESS
  - **Issue Found:** Trade #102 GBPCHF opened at 18:03 despite blacklist (loaded at 20:41)
  - **Root Cause:** reload_cfg() not called before main trading loop
  - **Fix #1:** Added reload_cfg() before while loop (commit 343eef9)
  - **Fix #2:** Auto-close positions on blacklist (commit 0e70319)
  - **Fix #3:** UTF-8 encoding for Windows (commit 4e50046)
  - **Deployment:** All fixes synced to production (21:04:50 UTC)
  - **Result:** Trade #102 GBPCHF CLOSED at 21:07:30
    - Final loss: -213.1 pips (vs -280 before close)
    - Blacklist respected: No new blacklist trades opened
    - Daily loss limit: Activated (2/2), bot paused
  - **Status:** ✅ All fixes verified working on appdbpri
```
