# forex_ai_bot v1.3 — Technical Reference

> **Purpose**: Machine-readable technical specification for forex_ai_bot_v1.3.py.
> Optimized for LLM/AI consumption. All identifiers match source code exactly.

---

## 1. System Overview

Automated Forex trading bot for MetaTrader 5. Core loop:
1. Sync MT5 state → MS SQL
2. Per-symbol: ML inference → HTF filter → order placement
3. 4-stage trailing SL (R-multiple based profit protection)
4. Heartbeat + wisdom aggregation

Runtime: infinite loop, exits at 23:59 daily. Restarted by Task Scheduler.

## 2. Runtime Environment

### 2.1 Srodowisko lokalne (DEV)

| Component | Value |
|-----------|-------|
| Python | 3.10 (`C:\Program Files\Python310`) |
| Virtual env | `C:\Program Files\Python310\forex_env` |
| OS | Windows Server 2025 |
| Database | MS SQL Server, `localhost`, `ForexBotDB`, Windows Auth, ODBC Driver 17 |
| Broker API | MetaTrader 5 (`terminal64.exe`) + MetaTrader5 Python package |
| Scheduler | Task Scheduler, account `PRI\btrender`, trigger: user logon |
| Start script | `start.bat` → `taskkill python.exe /F` → `py forex_ai_bot_v1.3.py` |

### 2.2 Srodowisko produkcyjne (PROD)

| Component | Value |
|-----------|-------|
| Serwer | `Appdbpri` (Windows Server 2025) |
| Sciezka | `\\Appdbpri\c$\Program Files\Python310\forex_env` (mapowany jako dysk `B:`) |
| Python | 3.10 (`C:\Program Files\Python310`) |
| Broker | MetaTrader 5 zalogowany na koncie live/demo |
| Baza danych | MS SQL Server na `appdbpri`, baza `ForexBotDB`, Windows Auth |
| Konto | `PRI\btrender` (db_owner na ForexBotDB) |
| Uprawnienia zapisu | `forex_logs\`, `forex_models\`, `extreme_price_dict.pkl` |

## 3. Dependencies

### Standard Library
`os`, `sys`, `math`, `time`, `logging`, `pickle`, `datetime`

### External Packages
`MetaTrader5`, `pandas`, `numpy`, `talib`, `joblib`, `pyodbc`, `pytz`

### Local Modules — `forex_base`
| Module | Imports | Purpose |
|--------|---------|---------|
| `indicators` | `generate_features` | Technical feature engineering |
| `formation_detection` | `detect_candle_formations` | Candlestick pattern detection |
| `tran_logs` | `log_trade`, `set_mssql_writer` | Trade logging to MS SQL |
| `globalcfg` | `get_global_cfg`, `get_global_cfg_as_dict` | Global config access |
| `train_forex_ai_model_v1_2` | `run` (aliased `retrain_models`) | Model retraining |
| `common` | `format_time` | Time formatting utility |

### Local Modules — `forex_v14`
| Module | Imports | Purpose |
|--------|---------|---------|
| `wisdom_aggregator` | `WisdomAggregator` | 24/7 market observation, scoring, outcomes |
| `db_writer` | `MSSQLWriter`, `DBLogHandler` | MS SQL data access layer |

### Model Artifacts (per symbol)
```
{MODEL_PATH}/{SYMBOL}_model.pkl
{MODEL_PATH}/{SYMBOL}_scaler.pkl
{MODEL_PATH}/{SYMBOL}_feature_columns.pkl
```

## 4. Global Configuration (`globalcfg.py`)

All values accessed via `get_global_cfg(key)`.

### Trading Parameters
| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `symbols` | list[str] | 21 pairs | Traded instruments (Capital.com naming) |
| `interval_minutes` | int | 240 | Analysis interval (H4) |
| `timeframe` | MT5 enum | `TIMEFRAME_H4` | MT5 timeframe constant |
| `candles` | int | 60 | Candle window for analysis |
| `candles_max` | int | 120 | Extended candle window (Fibo TP) |
| `model_path` | str | `"forex_models"` | Model directory |
| `magic` | int | 123456 | MT5 magic number |
| `lot` | float | 1.0 | Max lot size |
| `min_lot` | float | 0.33 | Min lot size |
| `tp_atr_multiplier` | float | 1.618 | TP = Fibonacci level from swing range |
| `sl_atr_multiplier` | float | 1.3 | SL = ATR × 1.3 from entry |
| `atr_min` | float | 0.001 | Minimum ATR to enter trade |
| `predict_proba_threshold` | float | 0.75 | ML confidence threshold (Variant C: raised from 0.6) |
| `tran_incubator_sec` | float | 72000 | Min hold time (5 × H4 = 20h) |
| `risk_per_trade` | float | 0.09 | Risk per trade as fraction of balance |

### 4-Stage Trailing SL Parameters
| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `trail_breakeven_r` | float | 0.7 | Stage 1 trigger: break-even (Variant C: lowered from 1.0) |
| `trail_lock_r` | float | 1.5 | Stage 2 trigger: lock profit |
| `trail_lock_fraction` | float | 0.5 | Stage 2: guaranteed R fraction |
| `trail_atr_r` | float | 2.0 | Stage 3 trigger: ATR trailing |
| `trail_atr_factor` | float | 1.0 | Stage 3: ATR distance from extreme price |
| `trail_tight_r` | float | 3.0 | Stage 4 trigger: tight trailing |
| `trail_tight_factor` | float | 0.5 | Stage 4: ATR distance from extreme price |

### Variant C: Entry Filters
| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `min_rr_ratio` | float | 2.0 | Min R:R ratio (TP/SL) to open trade |
| `spread_filter_pct` | float | 0.20 | Block if spread > 20% of SL distance |
| `volatility_block_start` | int | 0 | Block new trades from UTC hour |
| `volatility_block_end` | int | 4 | Block new trades until UTC hour |
| `symbol_cooldown_hours` | float | 24 | Cooldown per symbol after a loss |
| `max_daily_losses` | int | 3 | Max losses per day before stopping |
| `max_open_positions` | int | **3** | Max simultaneous open positions (was 5, reduced 2026-05-04) |
| `daily_loss_usd_limit` | float | 1000 | Max USD realized loss today → stop trading (added 2026-05-04) |

### Variant C: Position Protection
| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `partial_close_r` | float | 1.5 | Partial close trigger (R-multiple) |
| `partial_close_pct` | float | 0.5 | Fraction of volume to close (50%) |
| `time_exit_hours` | float | 16 | Close negative position after N hours |

### NPM: Negative Position Manager
| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `npm_alert_r` | float | -0.5 | R threshold for ALERT level |
| `npm_critical_r` | float | -1.0 | R threshold for CRITICAL level |
| `npm_hard_cap_r` | float | -2.5 | Hard cap: close 100% regardless |
| `npm_alert_npm_threshold` | float | 50 | NPM score < 50 → ALERT |
| `npm_critical_npm_threshold` | float | 30 | NPM score < 30 → CRITICAL |
| `npm_scaled_exit_50_r` | float | -1.0 | Close 50% at R + NPM criteria |
| `npm_scaled_exit_100_r` | float | -1.5 | Close 100% at R + NPM criteria |
| `npm_tighten_sl_r_factor` | float | 1.5 | ALERT: tighten SL to -1.5R |
| `npm_weekend_block_hour` | int | 20 | Friday: block closes after 20:00 UTC |
| `npm_weekend_recovery` | bool | True | Enable weekend recovery window |

## 5. Persistent State Files

| File | Contents | Used by |
|------|----------|---------|
| `extreme_price_dict.pkl` | `dict[ticket → float]` — best price reached per position | `update_trailing_sl()` |
| `forex_logs/forex_bot_{date}.log` | Daily application log (UTF-8) | `logging` module |

In-memory only:
| Variable | Contents |
|----------|----------|
| `open_time_dict` | `dict[ticket → int]` — position open timestamps |
| `symbol_last_loss` | `dict[symbol → datetime]` — last loss time per symbol (cooldown) |
| `daily_loss_count` | `int` — losses today (reset daily) |
| `daily_loss_date` | `str` — date of last counter reset (YYYY-MM-DD) |
| `daily_loss_usd_today` | `float` — realized USD P/L today, queried from DB each iteration |
| `partial_closed_tickets` | `set[int]` — tickets already partially closed |
| `npm_scaled_exit_tickets` | `set[int]` — tickets with NPM 50% scaled exit done |

## 6. Function Reference

### 6.1 MT5 Integration Layer

| Function | Signature | Description |
|----------|-----------|-------------|
| `initialize_mt5()` | `() → None` | Initialize MT5 terminal connection |
| `shutdown_mt5()` | `() → None` | Close MT5 session |
| `reconnect_mt5()` | `() → None` | Restart MT5 connection (called on `order_send() → None`) |
| `get_data(symbol)` | `(str) → DataFrame \| None` | Fetch OHLCV candles from MT5 |
| `calculate_atr(df)` | `(DataFrame) → float` | `talib.ATR(period=14).iloc[-1]` |

### 6.2 Signal Layer

| Function | Signature | Returns |
|----------|-----------|---------|
| `generate_features(df)` | `(DataFrame) → DataFrame` | Technical feature matrix |
| `detect_candle_formations(df)` | `(DataFrame) → DataFrame` | Candlestick pattern flags |
| `should_trade(df, model, scaler, feature_columns)` | `(...) → tuple[int, float] \| None` | `(action, confidence)` or `None`. action: 0=BUY, 1=SELL |

### 6.3 Order Execution

#### `place_order(symbol, action, atr, pred_proba)`

Entry logic:
1. **SL** = `price ± ATR × SL_ATR_MULTIPLIER` (1.3)
2. **TP** = `calculate_fibo_tp(df, action, fibo_level=1.618, window=CANDLES_MAX)`
3. **Min distance validation** against `symbol_info.trade_stops_level × trade_tick_size`
4. **ATR filter**: skip if `atr < ATR_MIN`
5. **Confidence filter**: skip if `pred_proba < PREDICT_PROBA_THRESHOLD`
6. **R:R filter** (Variant C): skip if `tp_distance / sl_distance < MIN_RR_RATIO` (2.0)
7. **Spread filter** (Variant C): skip if `spread / sl_distance > SPREAD_FILTER_PCT` (20%)
8. **SL distance** = `abs(price - sl)` (price units, NOT raw SL price)
7. **Lot** = `calculate_lot_size(symbol, sl_distance, risk_percent=1.0, confidence=pred_proba)`
8. Send `TRADE_ACTION_DEAL` to MT5

#### `calculate_lot_size(symbol, sl_distance, risk_percent, confidence)`

Equity-based position sizing with confidence scaling and margin safety.

**Formula:**
```
risk_money    = equity × (risk_percent / 100)          # e.g. 100k × 1% = 1000
sl_ticks      = sl_distance / tick_size                 # e.g. 0.0065 / 0.00001 = 650
loss_per_lot  = sl_ticks × tick_value                   # monetary loss per 1.0 lot at SL
base_lot      = risk_money / loss_per_lot               # e.g. 1000 / 650 = 1.54
```

**Confidence scaling** (linear interpolation):
| Confidence | Scale factor | Effect on base_lot |
|------------|-------------|--------------------|
| 0.60 (threshold) | 0.50 | 50% of base |
| 0.70 | 0.625 | 62.5% of base |
| 0.80 | 0.75 | 75% of base |
| 0.90 | 0.875 | 87.5% of base |
| 1.00 | 1.00 | 100% of base |

**Safety constraints** (applied sequentially):
1. Margin cap: `scaled_lot ≤ margin_free × 0.70 / margin_per_lot`
2. Broker limits: `volume_min ≤ scaled_lot ≤ volume_max`
3. Step rounding: `floor(scaled_lot / volume_step) × volume_step`

**Example** (EURUSD, equity=100k PLN, leverage=100, SL=65 pips):
```
risk_money = 1000, loss_per_lot = 650, base_lot = 1.54
confidence=0.7 → scale=0.625 → scaled_lot = 0.96
margin check: OK → final = 0.96 lot
```

#### `calculate_fibo_tp(df, action, fibo_level, window)`

Returns TP price using Fibonacci extension from last N candle swing range:
- BUY: `high - (high - low) × (1 - fibo_level)`
- SELL: `low + (high - low) × (1 - fibo_level)`

### 6.4 Position Management — 4-Stage Trailing SL

#### `update_trailing_sl()` — Core Profit Protection

Called once per main loop iteration. Iterates all open positions.

**Key concept: R-multiple**
```
1R = |entry_price - initial_sl|    (initial risk in price units)
R  = (current_price - entry) / 1R   (BUY)
R  = (entry - current_price) / 1R   (SELL)
```

**Extreme price tracking**: `extreme_price_dict[ticket]` stores:
- BUY: `max(all_prices_seen)` — highest price reached
- SELL: `min(all_prices_seen)` — lowest price reached

Persisted to `extreme_price_dict.pkl` every tick.

**Decision flow per position:**

```
                    ┌──────────────┐
                    │  Read pos    │
                    │  Compute R   │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │ age < 20h?   │── YES ──> SKIP (incubator)
                    └──────┬───────┘
                           │ NO
                    ┌──────▼───────┐
                    │ duration≥16h │── YES ──> NPM handles (time_exit in CRITICAL)
                    │ and R<0?     │
                    └──────┬───────┘
                           │ NO
                    ┌──────▼───────┐
                    │  R < 0 and   │── YES ──> NPM: Negative Position Manager
                    │  profit < 0? │            ├── HARD CAP (R≤-2.5) → close 100%
                    └──────┬───────┘            ├── WEEKEND WINDOW → hold
                           │ NO                 ├── CRITICAL + scaled exit
                                                ├── ALERT → tighten SL to -1.5R
                                                └── WATCH → monitor only
                    ┌──────▼───────┐
                    │ R≥1.5 and   │── YES ──> PARTIAL CLOSE 50% volume
                    │ not yet done?│
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │  R < 0.7?    │── YES ──> SKIP (Stage 0: original SL)
                    └──────┬───────┘
                           │ NO
                    ┌──────▼───────┐
                    │ Compute new  │
                    │ SL by stage  │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │ new_sl better│── NO ──> SKIP
                    │ than current?│
                    └──────┬───────┘
                           │ YES
                    ┌──────▼───────┐
                    │ MODIFY SL    │
                    │ via MT5 API  │
                    └──────────────┘
```

**Stage table:**

**Variant C additions (before stage evaluation):**
- **NPM (Negative Position Manager)**: Replaces simple `should_close_negative_position()` with 3-level escalation system
- **Time-based exit**: Integrated into NPM CRITICAL level (R < 0 for ≥ `TIME_EXIT_HOURS`)
- **Partial close**: At R ≥ `PARTIAL_CLOSE_R` (1.5), close 50% volume (once per ticket)

### 6.4.1 NPM: Negative Position Manager

**NPM Score** (0-100, weighted composite):

| Component | Weight | Max pts | Favorable signal |
|-----------|--------|---------|------------------|
| Momentum H1 | 20% | 20 | EMA(9) > EMA(21) for BUY, inverse for SELL |
| RSI extremum | 15% | 15 | Oversold (<30) for BUY, overbought (>70) for SELL |
| ATR contraction | 15% | 15 | ATR(5)/ATR(14) < 1.0 — move losing momentum |
| S/R proximity | 20% | 20 | Price near Fibo 38.2% or 61.8% level |
| Time penalty | 15% | 15 | Decays linearly: 0h=15pts, 48h=0pts |
| Swap cost | 15% | 15 | Low swap relative to loss = high score |

**Escalation levels:**

| Level | Trigger | Action |
|-------|---------|--------|
| 🟢 WATCH | R > -0.5 AND NPM > 50 | Log only |
| 🟡 ALERT | R ≤ -0.5 OR NPM < 50 | Tighten SL to -1.5R from entry |
| 🔴 CRITICAL | R ≤ -1.0 OR NPM < 30 | Scaled exit: 50% at R≤-1.0, 100% at R≤-1.5 |
| ⛔ HARD CAP | R ≤ -2.5 | Close 100% immediately |

**Weekend recovery window:**
- Friday after 20:00 UTC through Sunday: ALERT/CRITICAL actions suspended
- Rationale: weekend gaps can reverse trends, especially on metals/JPY crosses
- Hard cap (R ≤ -2.5) still enforced during weekend window

**Recovery probability:**
- Queried from `trade_outcomes` table for same symbol
- Logged per cycle to `negative_position_log` table for analysis

**SQL table `negative_position_log`:**

| Column | Type | Description |
|--------|------|-------------|
| ticket | BIGINT | MT5 position ticket |
| npm_score | FLOAT | Computed NPM score (0-100) |
| r_multiple | FLOAT | Current R-multiple |
| escalation | NVARCHAR(10) | WATCH / ALERT / CRITICAL |
| recovery_prob | FLOAT | Historical recovery % |
| action_taken | NVARCHAR(30) | MONITOR / ALERT_TIGHTEN / CRITICAL_CLOSE_50 / etc. |
| swap_cost_daily | FLOAT | Estimated daily swap cost |
| weekend_window | BIT | Whether weekend window was active |

| Stage | Trigger | New SL (BUY) | New SL (SELL) | Effect |
|-------|---------|-------------|--------------|--------|
| 0 | R < 0.7 | original | original | Normal risk |
| 1 | R ≥ 0.7 | `entry + spread_buffer` | `entry - spread_buffer` | Zero risk (break-even) |
| 2 | R ≥ 1.5 | `entry + 1R × 0.5` | `entry - 1R × 0.5` | Guaranteed +0.5R profit |
| 3 | R ≥ 2.0 | `extreme - ATR × 1.0` | `extreme + ATR × 1.0` | Trailing (follows price) |
| 4 | R ≥ 3.0 | `extreme - ATR × 0.5` | `extreme + ATR × 0.5` | Tight trailing |

**Constraint**: SL only moves in favorable direction (never widens risk). Checked via `sl_improves` flag.

**Example** (EURUSD BUY, entry=1.0800, initial_sl=1.0750, 1R=50 pips):

| Price | R | Stage | New SL | Locked profit |
|-------|---|-------|--------|---------------|
| 1.0820 | 0.4 | 0 | 1.0750 | -50 pips risk |
| 1.0850 | 1.0 | 1 | ~1.0801 | ~0 (break-even) |
| 1.0875 | 1.5 | 2 | 1.0825 | +25 pips |
| 1.0900 | 2.0 | 3 | ~1.0820 | +20 pips (trailing) |
| 1.0950 | 3.0 | 4 | ~1.0910 | +110 pips (tight) |

#### `_close_position(pos)`

Helper to close an MT5 position. Sends `TRADE_ACTION_DEAL` with opposite order type.

#### `should_close_negative_position(df, pos, model, scaler, feature_columns)`

Heuristic analysis for positions that have been negative since open (R < 0):

| Signal | Method | Close condition |
|--------|--------|----------------|
| Trend | EMA(20) vs EMA(50) + ADX > 20 | Trend against position |
| RSI | RSI(14) | < 40 for BUY, > 60 for SELL |
| Patterns | `CDLENGULFING`, `CDLHAMMER` | No reversal signal |
| ML | Model re-inference | Opposite prediction with low confidence |
| Fibonacci | Price near fibo_382/fibo_618 | Overrides close → wait |

### 6.5 Trade Deduplication & Time Filters

| Function | Logic |
|----------|-------|
| `is_trade_symbol(sym)` | Returns `False` if any open position exists for symbol |
| `is_not_duplicate_trade(sym, direction)` | Returns `False` if same symbol+direction closed today |
| `is_trading_time()` | `False` on Monday before 01:00, Friday after 23:00, weekends |

### 6.6 Higher Timeframe Trend Filter (HTF)

#### `WisdomAggregator.get_higher_tf_trend(symbol)`

Checks W1 (weekly) and D1 (daily) trend alignment before order placement.

**Method**: EMA(20) vs EMA(50) with 0.05% threshold → "UP" / "DOWN" / "FLAT"

**Decision matrix:**

| W1 + D1 aligned? | Direction vs ML | Action |
|-------------------|----------------|--------|
| YES, both same as ML | Agree | **OPEN** — full confidence |
| W1 agrees ML, D1 **opposite** to W1 | Conflict | **BLOCK** — W1 vs D1 HTF conflict (added 2026-05-04) |
| NO (mixed/flat) | — | **BLOCK** — W1+D1 must agree (Variant C: mandatory) |
| YES, opposite to ML | Conflict | **BLOCK** — do not open |

**Note (2026-05-04 fix)**: Previously the bot would PASS when W1 matched ML regardless of D1. This allowed trades like EURCHF SELL when W1=DOWN (SELL) but D1=UP — a clear HTF conflict. Fix: when W1 is not FLAT and matches ML, D1 must also not be the opposite direction.

### 6.7 DB Sync Layer

#### `update_closed_positions_status(days_back=5)`

Syncs MT5 deal history and open positions to MS SQL `trades` table:
- Filters only `DEAL_ENTRY_OUT` deals (closing transactions)
- Uses `deal.position_id` as primary key (`trades.mt5_position_id`) and `deal.order` as fallback (`trades.mt5_order_id`)
- Closed deals: marks `done='Tak'`, saves `profit`, `result`, `close_time`, records `trade_outcomes`
- Open positions: updates `profit`, `result`, `sl`, `tp`, `current_price`, `swap`, `duration_hours`

#### `MSSQLWriter.sync_open_positions_from_mt5(positions)`

Reconciles open MT5 positions with `trades` table. Missing records inserted with `prediction='SYNC'`, `status='SYNCED'`.

#### `MSSQLWriter.sync_deals_from_mt5(deals)`

Reconciles MT5 deal history with `trades` + `trade_outcomes` tables.
- `DEAL_ENTRY_IN`: inserts missing trade opens and stores both IDs (`mt5_order_id=deal.order`, `mt5_position_id=deal.position_id`)
- `DEAL_ENTRY_OUT`: updates status by `mt5_position_id` (with order fallback)
- If a close deal appears without existing open row (manual trade / missed open sync), bot inserts closed `SYNCED` trade to preserve full history in `trades`

**Sync schedule:**
- Bot startup: 7 days back
- Every loop iteration: 3 days back

### 6.8 Wisdom Aggregator

| Method | Schedule | Description |
|--------|----------|-------------|
| `record_observation()` | Every cycle per symbol | Stores market snapshot to `observations` |
| `update_outcomes()` | Every 15 min | Fills `outcome_1h/4h/24h`, `max_favorable/adverse` |
| `aggregate_formation_effectiveness()` | Every 24h | Computes `win_rate` per formation in `formation_effectiveness` |
| `record_trade_outcome()` | On deal close | Records trade result to `trade_outcomes` |
| `get_higher_tf_trend(symbol)` | Before order | Returns W1/D1 trend alignment dict |

## 7. Main Loop Flow

```python
# Pseudocode — main loop structure (Variant C)
initialize_mt5()
mssql = MSSQLWriter()
wisdom = WisdomAggregator(mssql)
# Startup sync: 7 days
sync_open_positions_from_mt5()
sync_deals_from_mt5(days=7)

while True:
    if time == 23:59: sys.exit()
    
    update_closed_positions_status()
    sync_mt5_to_db(days=3)
    
    if not is_trading_time():
        heartbeat(); sleep(300); continue
    
    retrain_models()  # WARNING: runs every cycle
    
    # --- Variant C: pre-loop filters ---
    reset_daily_loss_counter()              # reset at midnight
    update_loss_tracker_from_mt5_history()   # scan closed deals for losses
    
    if daily_loss_count >= MAX_DAILY_LOSSES:
        update_trailing_sl(); sleep(); continue   # stop new trades, SL still active

    today_usd = mssql.get_today_loss_usd()      # sum(profit) from trades table today
    if today_usd <= -DAILY_LOSS_USD_LIMIT:       # default: -1000 USD
        update_trailing_sl(); sleep(); continue   # USD circuit breaker — stop new trades
    
    if utc_hour in [0, 1, 2, 3]:
        update_trailing_sl(); sleep(); continue   # volatility window block
    
    for symbol in SYMBOLS:
        if is_trade_symbol(symbol) == False: continue
        if symbol in cooldown (< 24h since last loss): continue  # per-symbol cooldown
        
        model, scaler, features = load_model(symbol)
        df = get_data(symbol)
        atr = calculate_atr(df)
        result = should_trade(df, model, scaler, features)
        
        wisdom.record_observation(symbol, ...)
        
        if result is None: continue
        action, confidence = result
        
        # HTF filter (Variant C: mandatory — both W1+D1 must agree)
        htf = wisdom.get_higher_tf_trend(symbol)
        if htf['aligned'] and htf_conflicts_with_ml(action): continue  # BLOCKED
        if not htf['aligned']: continue                                # BLOCKED (was: open with warning)
        
        if is_not_duplicate_trade(symbol, action):
            # place_order includes: R:R filter, spread filter
            place_order(symbol, action, atr, confidence)
    
    update_trailing_sl()  # 4-stage + partial close + NPM (negative position manager)
    
    heartbeat()
    wisdom.update_outcomes()           # every 15 min
    wisdom.aggregate_effectiveness()   # every 24h
    sleep(TRAILING_UPDATE_SEC)
```

## 8. Database Schema

### 8.1 Connection
```
Server=localhost; Database=ForexBotDB; Trusted_Connection=yes; Driver={ODBC Driver 17 for SQL Server}
```

### 8.2 Tables

| Table | Purpose | Population |
|-------|---------|------------|
| `observations` | 24/7 market snapshots | Every cycle per symbol |
| `trade_outcomes` | Closed trade results | On DEAL_ENTRY_OUT + sync |
| `formation_effectiveness` | Aggregated formation stats | Every 24h automatically |
| `trades` | Trade log + live status | On order + sync + per-cycle update |
| `bot_status` | Bot heartbeat | Every cycle |
| `bot_logs` | WARNING/ERROR/CRITICAL logs | Automatically via `DBLogHandler` |
| `negative_position_log` | NPM decision history | Every cycle per negative position |
| `bot_version_history` | Historia wersji bota | Przy starcie bota (kazda nowa wersja) |

### 8.3 `trades` Table Columns

| Column | Type | Description |
|--------|------|-------------|
| `open_time` | DATETIME2 | Position open time |
| `symbol` | NVARCHAR(20) | Currency pair |
| `direction` | NVARCHAR(10) | BUY / SELL |
| `price` | FLOAT | Entry price |
| `sl` | FLOAT | Current Stop Loss (updated by trailing) |
| `tp` | FLOAT | Current Take Profit |
| `lot` | FLOAT | Position volume |
| `prediction` | NVARCHAR(10) | ML prediction or 'SYNC' |
| `status` | NVARCHAR(30) | Order status (OK / SYNCED) |
| `order_id` | BIGINT | Legacy MT5 ID (backward compatibility) |
| `mt5_order_id` | BIGINT | MT5 order ticket (deal/order layer) |
| `mt5_position_id` | BIGINT | MT5 position ticket (position lifecycle key) |
| `confidence` | FLOAT | Model confidence |
| `atr` | FLOAT | ATR at entry |
| `result` | NVARCHAR(5) | Z (profit) / S (loss) — live updated |
| `profit` | FLOAT | Current (open) or final (closed) profit |
| `done` | NVARCHAR(5) | 'Nie' (open) / 'Tak' (closed) |
| `close_time` | DATETIME2 | Close time (NULL if open) |
| `current_price` | FLOAT | Live market price (updated per cycle) |
| `swap` | FLOAT | Accumulated swap |
| `duration_hours` | FLOAT | Position duration in hours |
| `bot_version` | NVARCHAR(20) | Wersja bota w chwili otwarcia (np. 1.3.0.5); '' dla rekordów synced z MT5 |

## 9. Known Issues & Technical Debt

| # | Issue | Location | Risk | Status |
|---|-------|----------|------|--------|
| 1 | ~~`calculate_lot_size()` receives SL price~~ | `place_order()` | ~~Incorrect base_lot~~ | **FIXED** |
| 2 | ~~`final_lot` always clips to ≤ LOT_MIN~~ | `calculate_lot_size()` | ~~Volume never exceeds min~~ | **FIXED** |
| 3 | ~~`base_lot` undefined on exception~~ | `calculate_lot_size()` | ~~NameError~~ | **FIXED** |
| 4 | `retrain_models()` runs every cycle | Main loop | Host overload | Open |
| 5 | Model files loaded per negative position | `update_trailing_sl()` | I/O bottleneck | Open |
| 6 | `is_not_duplicate_trade()` deal.type semantics | `is_not_duplicate_trade()` | False blocking | Open |
| 7 | ~~`check_margin_available()` never called~~ | `place_order()` | ~~Unused check~~ | Margin check inside `calculate_lot_size()` (70% cap) |
| 8 | Time calculation `abs(open_time - time.time())` | `update_trailing_sl()` | Wrong duration | Open |
| 9 | ~~Duplicate `return` after spread filter~~ | `place_order()` L395 | ~~Unreachable code~~ | **FIXED 2026-04** |
| 10 | ~~Manual trades partially missing in `trades` due to order/position ID mismatch~~ | `db_writer.py` sync layer | ~~Inconsistent reporting~~ | **FIXED 2026-05-14 (Variant B)** |

## 10. Recommended Improvements

1. ~~Fix `calculate_lot_size()`~~ — **DONE**: equity-based, proper SL distance, confidence scaling, margin safety
2. Throttle `retrain_models()` to run every N hours, not every cycle
3. Cache model files per symbol (load once, refresh on retraining)
4. ~~Use `check_margin_available()` before `place_order()`~~ — margin check now inside `calculate_lot_size()` (70% cap)
5. Add unit tests for lot sizing, deduplication, trailing SL stages
6. Replace `abs(open_time - time.time())` with proper `datetime` arithmetic

---

## 11. Changelog

### 2026-05-14 — Variant B (MT5 ID normalization for manual/synced trades)

#### `forex_v14/db_writer.py`
- Added automatic schema migration: `ensure_trades_mt5_columns()` creates `trades.mt5_order_id` and `trades.mt5_position_id` when missing.
- Added safe backfill for historical rows:
       - `mt5_order_id <- order_id`
       - `mt5_position_id <- order_id` (fallback for old data)
- Added indexes: `ix_trades_mt5_order_id`, `ix_trades_mt5_position_id`.
- `insert_trade()` now stores both MT5 IDs (`mt5_order_id`, `mt5_position_id`).
- `update_trade_status()` now matches by `mt5_position_id` (primary), `mt5_order_id` (fallback), and legacy `order_id`.
- `sync_deals_from_mt5()` now inserts closed `SYNCED` row when `DEAL_ENTRY_OUT` has no matching open row (manual trade/missed IN sync).

#### `forex_ai_bot_v1.3.py`
- Startup now calls `mssql.ensure_trades_mt5_columns()` before sync.
- `update_closed_positions_status()` now updates records using both MT5 IDs (`mt5_position_id` + `mt5_order_id`) with legacy fallback.

#### Efekt biznesowy
- Manual trades and broker-side transactions are now consistently represented in `trades` and can be linked with `trade_outcomes` without relying on ambiguous `order_id` semantics.

### 2026-05-14 — Variant B+A (risk tightening after loss audit)

#### `forex_ai_bot_v1.3.py`
- Raised global weak-signal entry floor: `CONF_THRESHOLD_MIN` `0.60 -> 0.65`.
- Added per-symbol minimum confidence floor (`CONF_THRESHOLD_MIN_SYMBOL`) for risky instruments:
       - `XAGUSD=0.70`
       - `EURAUD`, `USDCHF`, `USDCAD`, `NZDJPY`, `CADCHF`, `AUDCHF` = `0.67`
- Added hard per-symbol max lot caps (`MAX_LOT_SYMBOL`) applied after adaptive sizing:
       - `XAGUSD=0.03`
       - `EURAUD`, `USDCHF`, `USDCAD`, `NZDJPY`, `CADCHF`, `AUDCHF` = `0.60`
- Added conservative per-symbol weak-signal min lots (`LOT_MIN_SYMBOL`) for the same risky instruments.
- `reload_cfg()` now supports DB overrides for:
       - `conf_threshold_min_<SYMBOL>`
       - `max_lot_<SYMBOL>`
       - existing `min_lot_<SYMBOL>` remains supported.

#### Cel zmiany
- Cut off weak entries in the `0.60–0.65` band that produced disproportionate losses in production audit.
- Limit monetary damage on high-volatility / high-risk symbols even when ML signal still passes filters.

### 2026-05-04 (popołudnie) — poprawki jakości logów + bot_version w trades

#### `forex_ai_bot_v1.3.py` — throttle powtórnych WARNINGów
- **FIX**: Komunikat `"🚫 BLACKLIST aktywny"` był oznaczony `# DEBUG` i wpadal co 5 min — usunięty.
- **FIX**: `"⛔ Dzienny limit strat osiągnięty"` — logowany co każdą iterację (~5 min) przez cały dzień. Dodano flagę `_daily_limit_warned` — komunikat wysyłany tylko **raz na dobę** (reset przy zmianie daty).
- **FIX**: `"⛔ Dzienny limit straty USD osiągnięty"` — analogicznie, dodano `_usd_limit_warned`.

#### `forex_ai_bot_v1.3.py` — spam logów poza godzinami handlu (weekend)
- **BUG** (potwierdzony w logach): `"🌙 Poza godzinami handlu, czekam 5 minut"` występował co 5 min przez cały weekend — 713 linii logu w samą niedzielę (3.05.2026).
- **FIX**: Dodano throttle `_off_hours_last_log` — log max **1 raz na godzinę**.
- **FIX**: Sleep w weekend (sob/niedz) wydłużony z 5 min do **30 min** — rynek zamknięty, nie ma potrzeby sprawdzać co 5 min.
- **BUG**: Check `23:59 → sys.exit()` był po bloku `is_trading_time()`, który w weekend robił `continue` przed 23:59 — restart nie następował. W weekend 1–3.05 bot pracował bez dziennego restartu.
- **FIX**: Dodano osobny check `if _now_oh.hour == 23 and _now_oh.minute >= 58: sys.exit()` wewnątrz bloku off-hours — restart działa teraz także w weekend.

#### `forex_v14/db_writer.py` + `forex_base/tran_logs.py` + tabela `trades`
- **NOWE POLE** `trades.bot_version NVARCHAR(20) NOT NULL DEFAULT ''` — dodane przez `ALTER TABLE` na DB (appdbpri/ForexBotDB).
- `insert_trade()`: nowy parametr `bot_version=""` — dołączany do każdego INSERT.
- `log_trade()`: nowy parametr `bot_version=""` — przekazywany do `insert_trade()`.
- `place_order()` wywołuje `log_trade(..., bot_version=VERSION)` — każda nowa transakcja zapisuje aktualną wersję bota.
- Rekordy synchronizowane z MT5 (`status='SYNCED'`) mają `bot_version=''`.

#### `forex_ai_bot_v1.3.py` — komentarz zlecenia MT5
- `request["comment"]`: zmiana formatu `"AI Forex Bot 1.3"` → `"AI FBoot {VERSION}"` (np. `"AI FBoot 1.3.0.5"`).
- Komentarz jest dynamiczny — wersja zmienia się automatycznie z `globalcfg.VERSION`.

---

### 2026-05-04 — v1.3.0.5: HTF Scoring + Adaptive conf/lot + fixes

#### `forex_v14/wisdom_aggregator.py`
- `get_higher_tf_trend()`: dodano H4 jako trzeci timeframe.
  - Zwraca teraz: `{'w1_trend', 'd1_trend', 'h4_trend', 'aligned', 'direction'}`.
  - `h4_df = self._get_rates(symbol, 240, 60)` — `_TIMEFRAME_MAP` zawierał już `240: TIMEFRAME_H4`.

#### `forex_v14/db_writer.py`
- Dodano `get_symbol_performance(min_trades=10)` — zwraca `{symbol: {winrate, avg_profit, n}}` dla symboli z ≥ N zamkniętych transakcji. Używane przez Adaptive (Variant A).

#### `forex_ai_bot_v1.3.py` — Variant B: HTF Scoring (zastąpiło binarny filtr)

Nowa logika filtracji wejść oparta na punktach (zamiast prostego bloku W1 vs D1):

| Timeframe | Punkty (zgodny) | Punkty (przeciwny) |
|-----------|----------------|--------------------|
| W1 | +2 | −2 |
| D1 | +1 | −1 |
| H4 | +1 | −1 |

Wynik `htf_score = max(0, raw_score)`:

| Score | Akcja |
|-------|-------|
| 0–1 | BLOCK — zbyt słaba zgodność |
| 2 | WEAK PASS — min lot + conf ≥ `CONF_THRESHOLD_MIN + HTF_PARTIAL_CONF_BOOST` |
| 3–4 | FULL PASS — normalny lot i conf |

- Nowe stałe globalne: `HTF_PARTIAL_CONF_BOOST` (default 0.05), reloadowane z DB.
- `bot_diagnostics.extra_json` rozszerzony o `htf_score` i `h4`.

#### `forex_ai_bot_v1.3.py` — Variant A: Adaptive conf/lot per symbol

- Nowe stałe: `ADAPTIVE_MIN_TRADES`, `ADAPTIVE_WINRATE_THRESH` (0.35), `ADAPTIVE_CONF_BOOST` (0.10), `ADAPTIVE_LOT_FACTOR` (0.5).
- `symbol_adaptive` dict — ładowany co 60 min z `db_writer.get_symbol_performance()`.
- Symbole z WR < 35% i ≥ 10 transakcji: conf_threshold += 0.10, lot × 0.50.
- `place_order()` rozszerzony o parametr `lot_factor=1.0`.
- Nowe klucze w `bot_config` DB: `htf_partial_conf_boost`, `adaptive_min_trades`, `adaptive_winrate_thresh`, `adaptive_conf_boost`, `adaptive_lot_factor`.

#### `forex_ai_bot_v1.3.py` + `forex_base/globalcfg.py` — fixes

- **BUG FIX**: `get_global_cfg("blacklist_symbols", "")` → `get_global_cfg("blacklist_symbols") or ""` — funkcja przyjmuje tylko 1 argument.
- **FIX startup**: usunięto `print(get_global_cfg_as_dict())` — wyrzucał cały config (~40 linii) na stdout przy każdym starcie. Zastąpiono `logging.info()` z kluczowymi parametrami (wersja, liczba symboli, conf_min, limit strat USD).
- **FIX wersja**: `globalcfg.py` zaktualizowany do `"1.3.0.5"` i będzie synchronizowany z każdym releasem.
- **Architektura config**: plik `globalcfg.py` jest **fallbackiem** — config ładuje się z `bot_config` w DB przez `_load_cfg_from_db()`. Plik używany tylko gdy DB niedostępna.

### 2026-04 — Variant B + Structured DB Diagnostics

#### `forex_v14/db_writer.py`
- Added `ensure_diagnostics_table()` — creates `bot_diagnostics` table (IF NOT EXISTS):
  `id, timestamp, symbol, event_type, ml_decision, ml_confidence, filter_blocked, filter_reason, htf_w1, htf_d1, htf_aligned, atr, rr_ratio, npm_score, action_taken, extra_json`
- Added `insert_diagnostic(event_type, ...)` — inserts a structured diagnostic event row.

#### `forex_base/train_forex_ai_model_v1_2.py`
- `prepare_dataset()`: spread-adjusted target threshold (`max(0.0003, min(atr_median × 0.03, 0.0020))`), replaces hardcoded `0.0005`.
- `prepare_dataset()`: returns `sample_weight` (3rd return value) = `abs(next_return) / atr`, clipped at 5.0, normalized to mean=1.
- `train_model()`: accepts and passes `sample_weight` to `model.fit()`.
- `train_model()`: `eval_metric` changed `logloss` → `error` (optimizes accuracy, not log-probability).
- `get_recent_win_rate(symbol, last_n=20)`: new helper function — queries `trade_outcomes` via pyodbc, returns `float [0.0–1.0]` or `None`.
- `run()`: profit-aware check — if `win_rate < 35%` in last 20 trades AND scheduled retrain not due yet, triggers immediate retrain.

#### `forex_ai_bot_v1.3.py`
- **BUG FIX**: removed duplicate `return` statement after spread filter in `place_order()`.
- **HTF filter relaxed**: W1 is primary; D1 neutral (FLAT) is now allowed (previously blocked). Block conditions:
  - W1 OPPOSITE to ML direction → block
  - W1 FLAT + D1 OPPOSITE to ML → block
  - W1 FLAT + D1 FLAT → block (no trend signal)
  - W1 matches ML (D1 neutral or same) → allow
- `ensure_diagnostics_table()` called at bot startup.
- `insert_diagnostic()` calls added in:
  - HTF block path (`event_type="HTF_BLOCK"`)
  - HTF pass path (`event_type="HTF_PASS"`)
  - ATR filter block (`event_type="FILTER_ATR"`)
  - Confidence filter block (`event_type="FILTER_CONFIDENCE"`)
  - R:R filter block (`event_type="FILTER_RR"`)
  - Spread filter block (`event_type="FILTER_SPREAD"`)

### `bot_diagnostics` Table — Query Examples
```sql
-- Which filter blocks the most?
SELECT event_type, COUNT(*) AS cnt
FROM bot_diagnostics
WHERE filter_blocked = 1 AND timestamp >= DATEADD(day,-7,GETDATE())
GROUP BY event_type ORDER BY cnt DESC;

-- Confidence distribution at HTF_PASS
SELECT symbol, AVG(ml_confidence) AS avg_conf, COUNT(*) AS signals
FROM bot_diagnostics
WHERE event_type = 'HTF_PASS'
GROUP BY symbol ORDER BY avg_conf DESC;

-- HTF block breakdown by W1/D1
SELECT htf_w1, htf_d1, COUNT(*) AS cnt
FROM bot_diagnostics
WHERE event_type = 'HTF_BLOCK'
GROUP BY htf_w1, htf_d1 ORDER BY cnt DESC;
```

### 15.3 Deployment — ujednolicony skrypt

**Git workflow — zasada:**

| Sytuacja | Akcja git |
|---|---|
| Zmiana wdrożona na produkcję (`deploy.ps1`) | commit dev + merge dev → **main** + push oba |
| Zmiana tylko lokalna / w trakcie prac | commit tylko **dev** |

`main` zawsze = aktualny stan produkcji.

**Obowiązek aktualizacji dokumentacji po każdej zmianie:**
- `AIDoc/forex_ai_bot_v1_3_dokumentacja_techniczna.md` — zmiany techniczne
- `AIDoc/forex_ai_bot_v1_4_dokumentacja_teoretyczna.md` — zmiany biznesowe/strategiczne

Jedyny skrypt wdrozeniowy: `forex_env\deploy.ps1`

```powershell
# Pelny deploy (domyslnie) — auto-inkrementuje wersje
.\deploy.ps1

# Symulacja (brak zmian na serwerze, pokazuje nowa wersje)
.\deploy.ps1 -DryRun

# Wybrane pliki (BEZ auto-incrementu wersji)
.\deploy.ps1 -Files "forex_v14\db_writer.py"

# Deploy + weryfikacja rozmiaru plikow
.\deploy.ps1 -Verify

# Jednorazowa konfiguracja Task Scheduler na serwerze (po reinstalacji)
.\deploy.ps1 -SetupTasks
```

Skrypt automatycznie:
- **inkrementuje `BOT_VERSION`** w `forex_ai_bot_v1.3.py` przed skopiowaniem na produkcje
- mapuje dysk `B:` → `\\Appdbpri\c$\Program Files\Python310\forex_env`
- kopiuje wszystkie moduly produkcyjne
- usuwa pliki debug/diagnostyczne z serwera
- po zakonczeniu wyswietla git workflow do wykonania

**Pliki domyslnie wdrazane:**
- `forex_ai_bot_v1.3.py`
- `forex_v14\db_writer.py`, `forex_v14\wisdom_aggregator.py`
- `forex_base\globalcfg.py`, `forex_base\train_forex_ai_model_v1_2.py`
- `forex_base\indicators.py`, `forex_base\formation_detection.py`, `forex_base\tran_logs.py`, `forex_base\common.py`
- `start.bat`
- katalog `forex_dashboard\` (rekurencyjnie)

### 15.3.1 Wersjonowanie bota

**Schemat**: `1.3.X.Y`
- `1.3` — numer wersji glownej (zmiana tylko przy nowej wersji bota)
- `X` — numer zestawu poprawek (`0–9`)
- `Y` — numer poprawki (`1–99`); gdy Y > 99, X++, Y = 1

**Stala w kodzie** (`forex_ai_bot_v1.3.py`):
```python
BOT_VERSION = "1.3.0.X"   # auto-increment przy deploy
VERSION     = BOT_VERSION  # autorytatywne — DB nie nadpisuje
```

**Zasady:**
- `BOT_VERSION` jest jedynym zrodlem prawdy — DB nie nadpisuje
- Kazdy deploy przez `deploy.ps1` **automatycznie** inkrementuje `Y` PRZED skopiowaniem na produkcje
- Przy starcie bota: `bot_config[version]` aktualizowany do `BOT_VERSION`, wpis do `bot_version_history`
- Wersja wyswietlana przy starcie: `[START] Bot AI version: 1.3.0.X uruchomiony`
- Wersja dolaczana do komentarzy zlecen MT5

**Tabela `bot_version_history`** (MS SQL `ForexBotDB`):

| Kolumna | Typ | Opis |
|---------|-----|------|
| `id` | INT IDENTITY | PK |
| `version` | NVARCHAR(20) | Numer wersji (unikalny) |
| `deployed_at` | DATETIME2 | Czas pierwszego uruchomienia tej wersji |
| `description` | NVARCHAR(500) | Opis zmian |

Zapytanie podglad historii:
```sql
SELECT version, deployed_at, description FROM bot_version_history ORDER BY deployed_at DESC;
```

**Historia wersji:**

| Wersja | Data | Opis zmian |
|--------|------|------------|
| 1.3.0.1 | 2026-05-01 | Dodanie BOT_VERSION, ujednolicony deploy.ps1, wersjonowanie |
| 1.3.0.2 | 2026-05-01 | fix: stdout tylko CRITICAL (WARNING/INFO tylko do pliku logu), fix deploy.ps1 em-dash encoding |
| 1.3.0.3 | 2026-05-01 | fix: VERSION = BOT_VERSION zawsze (klucz `version` w DB nadpisowal do "1.3.0") |
| 1.3.0.4 | 2026-05-01 | feat: tabela `bot_version_history`, `record_version()` aktualizuje DB przy starcie bota |
| 1.3.0.5 | 2026-05-04 | feat: HTF scoring W1+D1+H4 (score 0–4) + adaptive conf/lot per symbol (Variant B+A); fix: usunięto dump całego configu na stdout przy starcie; poprawiono `get_global_cfg` — tylko 1 argument; wersja w `globalcfg.py` synchronizowana z releasem |

### 15.4 Git Workflow — OBOWIAZKOWY

#### Po zmianach lokalnych (DEV)
```bash
git add .
git commit -m "opis zmian"
git push origin dev
```

#### Po wdrozeniu na produkcje (PROD)
```bash
# 1. Upewnij sie ze dev jest aktualny
git push origin dev

# 2. Merge dev -> main (release na produkcje)
git checkout main
git merge dev
git push origin main
git checkout dev
```

**Zasady:**
- Aktywna galezia deweloperska: `dev`
- Galezia produkcyjna: `main` (odzwierciedla stan serwera Appdbpri)
- Nigdy nie commituj bezposrednio na `main`
- Merge `dev` → `main` tylko po udanym wdrozeniu i weryfikacji na produkcji

### 15.5 Uprawnienia produkcyjne
- Konto `PRI\btrender`: `db_owner` na `ForexBotDB` na serwerze `appdbpri`
- Zapis do: `forex_logs\`, `forex_models\`, `extreme_price_dict.pkl`

## 16. Podsumowanie
Skrypt jest kompletnym botem transakcyjnym opartym o ML i reguly techniczne, z rozbudowanym zarzadzaniem pozycja. Architektura jest modularna, ale zawiera krytyczne miejsca wymagajace korekt (szczegolnie lot sizing, synchronizacja logu i wydajnosc petli). Po usunieciu wskazanych bledow oraz dodaniu testow mozna istotnie zwiekszyc stabilnosc i przewidywalnosc dzialania produkcyjnego.
