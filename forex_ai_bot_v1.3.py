# -*- coding: utf-8 -*-
# forex_ai_bot_full.py
import os
import sys
import math
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import talib
import time
import joblib
import logging
import pickle
from datetime                             import datetime, timedelta
from forex_base.indicators                import generate_features
from forex_base.formation_detection       import detect_candle_formations
from forex_base.tran_logs                 import log_trade, set_mssql_writer  # Importuj funkcję logowania transakcji
from forex_base.globalcfg                 import get_global_cfg             # Importuj funkcję do pobierania interwału
from forex_base.globalcfg                 import get_global_cfg_as_dict     # Importuj funkcję do pobierania interwału
from forex_base.train_forex_ai_model_v1_2 import run as retrain_models      # Process trenowania modelu
import forex_base.common as common         # Importuj moduł common
from forex_v14.wisdom_aggregator          import WisdomAggregator            # v1.4 — obserwacja rynku
from forex_v14.db_writer                  import MSSQLWriter, DBLogHandler       # v1.4 — zapis do MS SQL
# === WERSJA ===
BOT_VERSION             = "1.3.0.1"                                      # Wersja bota (auto-increment przy deploy)

# === KONFIGURACJA ===
SYMBOLS                 = get_global_cfg("symbols")                      # Pobierz listę symboli z konfiguracji
BLACKLIST_SYMBOLS       = get_global_cfg("blacklist_symbols") or ""      # Symbole do wyłączenia (np. GBPCHF)
INTERVAL_MINUTES        = get_global_cfg("interval_minutes")             # Pobierz interwał w minutach
TIMEFRAME               = get_global_cfg("timeframe")                    # Pobierz odpowiedni timeframe
CANDLES                 = get_global_cfg("candles")                      # Liczba świec do analizy
CANDLES_MAX             = get_global_cfg("candles_max")                  # Maksymalna liczba świec do analizy
MODEL_PATH              = get_global_cfg("model_path")                   # Ścieżka do modeli
MAGIC                   = get_global_cfg("magic")                        # Magic number dla transakcji
LOT                     = float(get_global_cfg("lot"))                   # Rozmiar lota dla transakcji
LOT_MIN                 = float(get_global_cfg("min_lot"))               # Minimalny rozmiar lota dla transakcji
LOT_MIN_SYMBOL          = {}                                              # Minimalny lot per-instrument (min_lot_SYMBOL w bot_config)
CONF_THRESHOLD_SYMBOL   = {}                                              # Per-symbol próg confidence (conf_threshold_SYMBOL w bot_config)
CONF_THRESHOLD_MIN      = 0.60                                             # Minimalny próg confidence - poniżej skip, powyżej LOT_MIN
CONF_THRESHOLD_NORMAL   = 0.75                                             # Normalny próg confidence - powyżej normalny LOT
TP_ATR_MULTIPLIER       = float(get_global_cfg("tp_atr_multiplier"))     # Mnożnik ATR dla Take Profit 2.5
SL_ATR_MULTIPLIER       = float(get_global_cfg("sl_atr_multiplier"))     # Mnożnik ATR dla Stop Loss 1.5
ATR_MIN                 = float(get_global_cfg("atr_min"))               # Minimalny ATR do wejścia na rynek
TRAILING_UPDATE_SEC     = get_global_cfg("trade_timeout")                # Czas oczekiwania na aktualizację SL w sekundach 60
PREDICT_PROBA_THRESHOLD = get_global_cfg("predict_proba_threshold")      # Próg prawdopodobieństwa dla decyzji handlowych
TIMEZONE                = get_global_cfg("timezone")                     # Strefa czasowa
VERSION                 = get_global_cfg("version") or BOT_VERSION       # Wersja bota (DB override lub BOT_VERSION)
LOG_FILE                = get_global_cfg("log_file")                     # Plik logów
MIN_HOLD_SECONDS        = float(get_global_cfg("tran_incubator_sec"))    # Minimalny czas trzymania pozycji w sekundach (5 świec H4)
# --- 4-stopniowy trailing SL (dla zysków) ---
TRAIL_BE_R              = float(get_global_cfg("trail_breakeven_r"))      # Stage 1: break-even
TRAIL_LOCK_R            = float(get_global_cfg("trail_lock_r"))           # Stage 2: lock profit
TRAIL_LOCK_FRAC         = float(get_global_cfg("trail_lock_fraction"))    # Stage 2: gwarantowana frakcja R
TRAIL_ATR_R             = float(get_global_cfg("trail_atr_r"))            # Stage 3: trailing ATR
TRAIL_ATR_FACTOR        = float(get_global_cfg("trail_atr_factor"))       # Stage 3: ATR factor
TRAIL_TIGHT_R           = float(get_global_cfg("trail_tight_r"))          # Stage 4: tight trail
TRAIL_TIGHT_FACTOR      = float(get_global_cfg("trail_tight_factor"))     # Stage 4: ATR factor
# --- Dynamic Negative Trailing Stop (dla strat) ---
TRAIL_NEG_ACTIVE_R      = float(get_global_cfg("trail_neg_active_r") or "-0.5")     # Aktivuj negative trail na R <= -0.5
TRAIL_NEG_MAX_LOSS_R    = float(get_global_cfg("trail_neg_max_loss_r") or "-2.0")   # Hard cap: nie pozwól gorzej niż -2.0R
TRAIL_NEG_FACTOR        = float(get_global_cfg("trail_neg_factor") or "0.5")         # 0.5 ATR od najgorszej ceny
# --- Variant C: filtry wejścia ---
MIN_RR_RATIO            = float(get_global_cfg("min_rr_ratio"))           # Min R:R (TP/SL >= 2.0)
SPREAD_FILTER_PCT       = float(get_global_cfg("spread_filter_pct"))      # Spread > 20% SL → block
VOL_BLOCK_START         = int(get_global_cfg("volatility_block_start"))   # Block trading from UTC hour
VOL_BLOCK_END           = int(get_global_cfg("volatility_block_end"))     # Block trading until UTC hour
SYMBOL_COOLDOWN_H       = float(get_global_cfg("symbol_cooldown_hours"))  # Cooldown after loss (hours)
MAX_DAILY_LOSSES        = int(get_global_cfg("max_daily_losses"))         # Max losses per day
MAX_OPEN_POSITIONS      = int(get_global_cfg("max_open_positions"))       # Max simultaneous open positions
# --- Variant C: ochrona pozycji ---
PARTIAL_CLOSE_R         = float(get_global_cfg("partial_close_r"))        # Partial close at R>=1.5
PARTIAL_CLOSE_PCT       = float(get_global_cfg("partial_close_pct"))      # % to close (0.5 = 50%)
TIME_EXIT_HOURS         = float(get_global_cfg("time_exit_hours"))        # Close negative after 16h
# --- NPM: Negative Position Manager ---
NPM_ALERT_R             = float(get_global_cfg("npm_alert_r"))            # ALERT threshold R
NPM_CRITICAL_R          = float(get_global_cfg("npm_critical_r"))         # CRITICAL threshold R
NPM_HARD_CAP_R          = float(get_global_cfg("npm_hard_cap_r"))         # Hard cap: close 100%
NPM_ALERT_NPM           = float(get_global_cfg("npm_alert_npm_threshold"))   # NPM < 50 → ALERT
NPM_CRITICAL_NPM        = float(get_global_cfg("npm_critical_npm_threshold"))# NPM < 30 → CRITICAL
NPM_SCALED_50_R         = float(get_global_cfg("npm_scaled_exit_50_r"))   # Close 50% at R + NPM
NPM_SCALED_100_R        = float(get_global_cfg("npm_scaled_exit_100_r"))  # Close rest at R + NPM
NPM_TIGHTEN_SL_FACTOR   = float(get_global_cfg("npm_tighten_sl_r_factor"))# ALERT: tighten SL
NPM_WEEKEND_BLOCK_HOUR  = int(get_global_cfg("npm_weekend_block_hour"))   # Friday block hour
NPM_WEEKEND_RECOVERY    = bool(get_global_cfg("npm_weekend_recovery"))    # Enable weekend window


def reload_cfg():
    """Odswiezenie konfiguracji z bazy danych na poczatku kazdej iteracji.
    Aktualizuje wszystkie globalne stale. Fallback: wartosc pozostaje bez zmian."""
    global SYMBOLS, BLACKLIST_SYMBOLS, LOT, LOT_MIN, LOT_MIN_SYMBOL, CONF_THRESHOLD_SYMBOL, CONF_THRESHOLD_MIN, CONF_THRESHOLD_NORMAL, TP_ATR_MULTIPLIER, SL_ATR_MULTIPLIER, ATR_MIN
    global PREDICT_PROBA_THRESHOLD, MIN_HOLD_SECONDS, MIN_RR_RATIO, SPREAD_FILTER_PCT
    global VOL_BLOCK_START, VOL_BLOCK_END, SYMBOL_COOLDOWN_H, MAX_DAILY_LOSSES, MAX_OPEN_POSITIONS
    global PARTIAL_CLOSE_R, PARTIAL_CLOSE_PCT, TIME_EXIT_HOURS
    global TRAIL_BE_R, TRAIL_LOCK_R, TRAIL_LOCK_FRAC, TRAIL_ATR_R, TRAIL_ATR_FACTOR
    global TRAIL_TIGHT_R, TRAIL_TIGHT_FACTOR, TRAIL_NEG_ACTIVE_R, TRAIL_NEG_MAX_LOSS_R, TRAIL_NEG_FACTOR
    global TRAILING_UPDATE_SEC
    global NPM_ALERT_R, NPM_CRITICAL_R, NPM_HARD_CAP_R, NPM_ALERT_NPM, NPM_CRITICAL_NPM
    global NPM_SCALED_50_R, NPM_SCALED_100_R, NPM_TIGHTEN_SL_FACTOR
    global NPM_WEEKEND_BLOCK_HOUR, NPM_WEEKEND_RECOVERY, CANDLES, CANDLES_MAX
    try:
        _db_cfg = MSSQLWriter().get_all_config()
        if not _db_cfg:
            return
        def _f(k, default):   return float(_db_cfg[k])      if k in _db_cfg else default
        def _i(k, default):   return int(_db_cfg[k])        if k in _db_cfg else default
        def _b(k, default):   return _db_cfg[k].lower() == 'true' if k in _db_cfg else default
        def _s(k, default):   return _db_cfg[k]             if k in _db_cfg else default
        SYMBOLS              = [x.strip() for x in _s('symbols','').split(',') if x.strip()] or SYMBOLS
        BLACKLIST_SYMBOLS    = _s('blacklist_symbols', '')
        if BLACKLIST_SYMBOLS:
            _blacklist = [x.strip() for x in BLACKLIST_SYMBOLS.split(',') if x.strip()]
            BLACKLIST_SYMBOLS = _blacklist
            # Usuń blacklisted symbole ze listy handlowanych
            _original_count = len(SYMBOLS)
            SYMBOLS = [s for s in SYMBOLS if s not in BLACKLIST_SYMBOLS]
            if len(SYMBOLS) < _original_count:
                logging.warning(f"⛔ Blacklist aktywna: usunięto {_original_count - len(SYMBOLS)} symboli")
        else:
            BLACKLIST_SYMBOLS = []
        LOT                  = _f('lot',                    LOT)
        LOT_MIN              = _f('min_lot',                LOT_MIN)
        LOT_MIN_SYMBOL       = {k[len('min_lot_'):]: float(v) for k, v in _db_cfg.items() if k.startswith('min_lot_') and v}
        CONF_THRESHOLD_SYMBOL = {k[len('conf_threshold_'):]: float(v) for k, v in _db_cfg.items() if k.startswith('conf_threshold_') and v}
        CONF_THRESHOLD_MIN   = _f('conf_threshold_min',    CONF_THRESHOLD_MIN)
        CONF_THRESHOLD_NORMAL = _f('conf_threshold_normal', CONF_THRESHOLD_NORMAL)
        TP_ATR_MULTIPLIER    = _f('tp_atr_multiplier',      TP_ATR_MULTIPLIER)
        SL_ATR_MULTIPLIER    = _f('sl_atr_multiplier',      SL_ATR_MULTIPLIER)
        ATR_MIN              = _f('atr_min',                ATR_MIN)
        TRAILING_UPDATE_SEC  = _i('trade_timeout',          TRAILING_UPDATE_SEC)
        PREDICT_PROBA_THRESHOLD = _f('predict_proba_threshold', PREDICT_PROBA_THRESHOLD)
        MIN_HOLD_SECONDS     = _f('tran_incubator_sec',     MIN_HOLD_SECONDS)
        CANDLES              = _i('candles',                CANDLES)
        CANDLES_MAX          = _i('candles_max',            CANDLES_MAX)
        MIN_RR_RATIO         = _f('min_rr_ratio',           MIN_RR_RATIO)
        SPREAD_FILTER_PCT    = _f('spread_filter_pct',      SPREAD_FILTER_PCT)
        VOL_BLOCK_START      = _i('volatility_block_start', VOL_BLOCK_START)
        VOL_BLOCK_END        = _i('volatility_block_end',   VOL_BLOCK_END)
        SYMBOL_COOLDOWN_H    = _f('symbol_cooldown_hours',  SYMBOL_COOLDOWN_H)
        MAX_DAILY_LOSSES     = _i('max_daily_losses',       MAX_DAILY_LOSSES)
        MAX_OPEN_POSITIONS   = _i('max_open_positions',     MAX_OPEN_POSITIONS)
        PARTIAL_CLOSE_R      = _f('partial_close_r',        PARTIAL_CLOSE_R)
        PARTIAL_CLOSE_PCT    = _f('partial_close_pct',      PARTIAL_CLOSE_PCT)
        TIME_EXIT_HOURS      = _f('time_exit_hours',        TIME_EXIT_HOURS)
        TRAIL_BE_R           = _f('trail_breakeven_r',      TRAIL_BE_R)
        TRAIL_LOCK_R         = _f('trail_lock_r',           TRAIL_LOCK_R)
        TRAIL_LOCK_FRAC      = _f('trail_lock_fraction',    TRAIL_LOCK_FRAC)
        TRAIL_ATR_R          = _f('trail_atr_r',            TRAIL_ATR_R)
        TRAIL_ATR_FACTOR     = _f('trail_atr_factor',       TRAIL_ATR_FACTOR)
        TRAIL_TIGHT_R        = _f('trail_tight_r',          TRAIL_TIGHT_R)
        TRAIL_TIGHT_FACTOR   = _f('trail_tight_factor',     TRAIL_TIGHT_FACTOR)
        TRAIL_NEG_ACTIVE_R   = _f('trail_neg_active_r',     TRAIL_NEG_ACTIVE_R)
        TRAIL_NEG_MAX_LOSS_R = _f('trail_neg_max_loss_r',   TRAIL_NEG_MAX_LOSS_R)
        TRAIL_NEG_FACTOR     = _f('trail_neg_factor',       TRAIL_NEG_FACTOR)
        NPM_ALERT_R          = _f('npm_alert_r',            NPM_ALERT_R)
        NPM_CRITICAL_R       = _f('npm_critical_r',         NPM_CRITICAL_R)
        NPM_HARD_CAP_R       = _f('npm_hard_cap_r',         NPM_HARD_CAP_R)
        NPM_ALERT_NPM        = _f('npm_alert_npm_threshold',   NPM_ALERT_NPM)
        NPM_CRITICAL_NPM     = _f('npm_critical_npm_threshold', NPM_CRITICAL_NPM)
        NPM_SCALED_50_R      = _f('npm_scaled_exit_50_r',   NPM_SCALED_50_R)
        NPM_SCALED_100_R     = _f('npm_scaled_exit_100_r',  NPM_SCALED_100_R)
        NPM_TIGHTEN_SL_FACTOR= _f('npm_tighten_sl_r_factor',NPM_TIGHTEN_SL_FACTOR)
        NPM_WEEKEND_BLOCK_HOUR = _i('npm_weekend_block_hour', NPM_WEEKEND_BLOCK_HOUR)
        NPM_WEEKEND_RECOVERY = _b('npm_weekend_recovery',   NPM_WEEKEND_RECOVERY)
    except Exception as _reload_err:
        logging.warning(f"[reload_cfg] Blad odswiezania config z DB (stare wartosci): {_reload_err}")


# === Trwałość extreme_price_dict (śledzenie najlepszej ceny pozycji) ===
try:
    with open("extreme_price_dict.pkl", "rb") as f:
        extreme_price_dict = pickle.load(f)
except Exception:
    extreme_price_dict = {}
open_time_dict = {}
# === Variant C: state tracking ===
symbol_last_loss = {}      # {symbol: datetime} — ostatnia strata na symbolu (cooldown)
daily_loss_count = 0       # Licznik strat w bieżącym dniu
daily_loss_date = None     # Data ostatniego resetu licznika
partial_closed_tickets = set()  # Pozycje już częściowo zamknięte
npm_scaled_exit_tickets = set()  # Pozycje z NPM skalowanym zamknięciem 50%

# === LOGOWANIE - DYNAMIC LOG FILE HANDLER ===
_last_log_date = None
_log_file_handler = None

def setup_logging():
    """Setup file logging with daily rotation support."""
    global LOG_FILE, _last_log_date, _log_file_handler
    
    # Regenerate LOG_FILE path based on current date
    LOG_FILE = f"{get_global_cfg('logs_dir')}/forex_bot_{datetime.now().strftime('%Y-%m-%d')}.log"
    os.makedirs(get_global_cfg("logs_dir"), exist_ok=True)
    
    # Remove old file handler if exists
    if _log_file_handler:
        logging.getLogger().removeHandler(_log_file_handler)
        _log_file_handler.close()
    
    # Create new file handler
    _log_file_handler = logging.FileHandler(LOG_FILE, mode='a', encoding='utf-8')
    _log_file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    _log_file_handler.setFormatter(formatter)
    
    # Add to root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Usun istniejace StreamHandlery (stdout/stderr) dodane przez basicConfig lub importy
    for h in root_logger.handlers[:]:
        if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler):
            root_logger.removeHandler(h)

    root_logger.addHandler(_log_file_handler)

    # Stdout/stderr: tylko CRITICAL (bledy krytyczne wymagajace natychmiastowej uwagi)
    _console_handler = logging.StreamHandler()
    _console_handler.setLevel(logging.CRITICAL)
    _console_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    root_logger.addHandler(_console_handler)
    
    _last_log_date = datetime.now().date()
    logging.info(f"Logowanie do pliku: {LOG_FILE}")

def check_and_rotate_logs():
    """Sprawdzenie czy zmienił się dzień - jeśli tak, otwórz nowy plik loga."""
    global _last_log_date
    today = datetime.now().date()
    if _last_log_date != today:
        setup_logging()

# Initial logging setup
setup_logging()

logging.info("================== Konfiguracja globalna ==================")
logging.info(str(get_global_cfg_as_dict()))
logging.info("===========================================================")


# === FUNKCJE ===
def initialize_mt5():
    if not mt5.initialize():
        logging.error(f"❌ MetaTrader 5 initialization failed: {mt5.last_error()}")
        print("❌ MetaTrader 5 initialization failed:", mt5.last_error())
        raise RuntimeError("MT5 init error")

def shutdown_mt5():
    mt5.shutdown()

def reconnect_mt5():
    shutdown_mt5()
    time.sleep(5)
    initialize_mt5()

def get_data(symbol):
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, CANDLES)
    if rates is None or len(rates) < CANDLES:
        # logging.warning(f"⚠️ Brak danych dla {symbol} (pobrano {0 if rates is None else len(rates)} świec)")
        return None
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    # logging.info(f"ℹ️ Dane dla {symbol}: {len(df)} świec, kolumny: {list(df.columns)}")
    return df

def calculate_atr(df):
    return talib.ATR(df['high'], df['low'], df['close'], timeperiod=14).iloc[-1]

def should_trade(df, model, scaler, feature_columns):
    try:
        logging.debug("🟡 Generating features...")
        features_df = generate_features(df)
        formations_df = detect_candle_formations(df)

        if formations_df is not None:
            for col in formations_df.columns:
                if col not in features_df.columns:
                    features_df[col] = formations_df[col]
        else:
            logging.debug("🟡 No formations detected.")

        # Upewnij się, że kolumny są stringami
        features_df.columns = features_df.columns.astype(str)

        # Dodaj brakujące kolumny z zerami
        missing = set(feature_columns) - set(features_df.columns)
        if missing:
            logging.warning(f"⚠️ Missing features: {missing}")
            for col in missing:
                features_df[col] = 0.0

        # Wybierz tylko wymagane kolumny
        X = features_df[feature_columns].iloc[[-1]]

        # Loguj kształt i typ danych wejściowych
        # logging.debug(f"🟡 Input X shape: {X.shape}")
        # logging.debug(f"🟡 X columns: {list(X.columns)}")
        # logging.debug(f"🟡 X dtypes: {X.dtypes.tolist()}")

        # Skalowanie
        X_scaled = scaler.transform(X)

        # Predykcja
        pred_proba = model.predict_proba(X_scaled)[0]
        decision = int(np.argmax(pred_proba))
        confidence = float(pred_proba[decision])

        logging.info(f"ℹ️ Prediction: decision={decision}, confidence={confidence:.2f}")
        return decision, confidence

    except Exception as e:
        logging.error(f"❌ Prediction error: {e}", exc_info=True)  # exc_info=True daje traceback

    return None, None

def check_margin_available(symbol, lot):
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        logging.error(f"❌ Nie znaleziono danych symbolu dla {symbol}")
        return False

    account_info = mt5.account_info()
    if account_info is None:
        logging.error("❌ Nie udało się pobrać informacji o koncie")
        return False

    if not symbol_info.trade_calc_mode in [0, 1, 2, 3]:
        logging.warning(f"⚠️ Nieobsługiwany tryb kalkulacji marginesu dla {symbol}")
        return True  # pomijamy sprawdzenie marginesu, pozwalamy kontynuować

    # Cena do obliczenia wartości pozycji
    price = symbol_info.ask if symbol_info.ask > 0 else symbol_info.bid
    if price == 0.0:
        logging.error(f"❌ Błędna cena dla {symbol}")
        return False

    contract_size = symbol_info.trade_contract_size
    leverage = account_info.leverage if account_info.leverage > 0 else 1

    required_margin = lot * contract_size * price / leverage
    free_margin = account_info.margin_free

    logging.info(f"💰 Wymagany margin: {required_margin:.2f}, Wolny margin: {free_margin:.2f}")

    if free_margin < required_margin:
        logging.warning(f"❌ Niewystarczający margines do otwarcia pozycji na {symbol}")
        return False

    return True

def calculate_lot_size(symbol, sl_distance, risk_percent=1.0, confidence=0.5, use_min_lot=False):
    """Oblicz wielkość pozycji na podstawie equity, odległości SL i confidence.

    Args:
        symbol: instrument (np. 'EURUSD')
        sl_distance: odległość SL od ceny wejścia W JEDNOSTKACH CENOWYCH (np. 0.0050 = 50 pips)
        risk_percent: % equity do zaryzykowania na transakcję (domyślnie 1%)
        confidence: pewność modelu ML (0.0–1.0)
        use_min_lot: jeśli True, użyj LOT_MIN zamiast normalnego LOT (dla słabszych sygnałów 0.60-0.75)

    Returns:
        float: wielkość lota zaokrąglona do volume_step
    """
    account_info = mt5.account_info()
    symbol_info = mt5.symbol_info(symbol)
    if account_info is None or symbol_info is None:
        logging.error("❌ Brak danych o koncie lub symbolu.")
        return symbol_info.volume_min if symbol_info else 0.01

    equity = account_info.equity
    margin_free = account_info.margin_free
    leverage = account_info.leverage if account_info.leverage > 0 else 1
    contract_size = symbol_info.trade_contract_size
    vol_min = symbol_info.volume_min
    vol_max = symbol_info.volume_max
    vol_step = symbol_info.volume_step
    tick_size = symbol_info.trade_tick_size or 0.00001
    tick_value = symbol_info.trade_tick_value or 1.0

    # --- 1. Kwota ryzyka: risk_percent % equity ---
    risk_money = equity * (risk_percent / 100.0)

    # --- 2. SL distance → wartość pieniężna per lot ---
    # tick_value = ile waluty konta wart jest ruch o tick_size per 1 lot
    # sl_distance / tick_size = ile ticków w SL
    # loss_per_lot = (sl_distance / tick_size) * tick_value
    if sl_distance <= 0 or tick_size <= 0:
        logging.error(f"❌ Nieprawidłowa odległość SL ({sl_distance}) lub tick_size ({tick_size}) dla {symbol}")
        return vol_min

    sl_ticks = sl_distance / tick_size
    loss_per_lot = sl_ticks * tick_value

    if loss_per_lot <= 0:
        logging.error(f"❌ loss_per_lot <= 0 dla {symbol}. sl_ticks={sl_ticks}, tick_value={tick_value}")
        return vol_min

    # --- 3. Base lot = ryzyko / strata per lot ---
    base_lot = risk_money / loss_per_lot

    # --- 4. Skalowanie wg confidence ---
    # confidence na progu (0.75) → 75% base_lot
    # confidence 1.0 → 100% base_lot
    # Liniowa interpolacja between [0.75, 1.0]
    conf_min = 0.75
    conf_max = 1.0
    conf_clamped = max(PREDICT_PROBA_THRESHOLD, min(confidence, 1.0))
    conf_scale = conf_min + (conf_max - conf_min) * ((conf_clamped - PREDICT_PROBA_THRESHOLD) / (1.0 - PREDICT_PROBA_THRESHOLD))
    scaled_lot = base_lot * conf_scale

    # --- 5. Margin safety check (max 70% wolnego marginu) ---
    price = symbol_info.ask if symbol_info.ask > 0 else symbol_info.bid
    if price > 0 and contract_size > 0 and leverage > 0:
        margin_per_lot = contract_size * price / leverage
        if margin_per_lot > 0:
            max_margin_lot = (margin_free * 0.70) / margin_per_lot
            scaled_lot = min(scaled_lot, max_margin_lot)

    # --- 6. Clamp do limitów brokera ---
    scaled_lot = max(vol_min, min(scaled_lot, vol_max))

    # Zaokrąglij do volume_step
    if vol_step > 0:
        scaled_lot = math.floor(scaled_lot / vol_step) * vol_step
        scaled_lot = max(vol_min, round(scaled_lot, 2))

    # --- 7. Minimalny lot per-symbol (LOT_MIN_SYMBOL lub globalny LOT_MIN) ---
    # Jeśli use_min_lot=True (sygnał 0.60-0.75), zawsze użyj LOT_MIN
    if use_min_lot:
        effective_min = LOT_MIN_SYMBOL.get(symbol, LOT_MIN)
        scaled_lot = effective_min
        logging.info(f"📊 LOT CALC {symbol}: WEAK signal confidence={confidence:.2f} → LOT_MIN={effective_min:.2f}")
    else:
        effective_min = LOT_MIN_SYMBOL.get(symbol, LOT_MIN)
        if scaled_lot < effective_min:
            logging.info(f"📊 LOT CALC {symbol}: lot={scaled_lot:.2f} ponizej min={effective_min:.2f} → wymuszam min")
            scaled_lot = effective_min

    logging.info(
        f"📊 LOT CALC {symbol}: equity={equity:.0f}, risk={risk_money:.0f} ({risk_percent}%), "
        f"SL_dist={sl_distance:.5f}, loss/lot={loss_per_lot:.2f}, "
        f"base_lot={base_lot:.2f}, conf={confidence:.2f}→scale={conf_scale:.2f}, "
        f"final={scaled_lot:.2f}, min={effective_min:.2f}, margin_free={margin_free:.0f}, leverage={leverage}"
    )
    return scaled_lot

def calculate_fibo_tp(df, action, fibo_level=TP_ATR_MULTIPLIER, window=CANDLES):
    # Wybierz ostatnie N świec
    recent = df.tail(window)
    high = recent['high'].max()
    low = recent['low'].min()
    if action == 0: # BUY
        tp = high - (high - low) * (1 - fibo_level)
    else: # SELL
        tp = low + (high - low) * (1 - fibo_level)
    return tp

def place_order(symbol, action, atr, pred_proba, use_min_lot=False):
    if not mt5.symbol_select(symbol, True):
        logging.warning(f"⚠️ Nie udało się aktywować symbolu {symbol}")
        return

    account_info = mt5.account_info()
    if account_info is None:
        logging.error("❌ Brak zalogowanego konta!")
        reconnect_mt5()
        return

    tick = mt5.symbol_info_tick(symbol)
    symbol_info = mt5.symbol_info(symbol)
    if tick is None or symbol_info is None:
        logging.error(f"⚠️ Brak ticka lub info dla {symbol}")
        return

    if pred_proba is None:
        logging.warning(f"⚠️ Brak wartości predykcji – pominięto zlecenie dla {symbol}")
        return

    price = tick.ask if action == 0 else tick.bid
    sl = price - atr * SL_ATR_MULTIPLIER if action == 0 else price + atr * SL_ATR_MULTIPLIER

    # Pobierz dane do wyliczenia Fibo TP (większe okno!)
    df = get_data(symbol)
    tp = calculate_fibo_tp(df, action, fibo_level=TP_ATR_MULTIPLIER, window=CANDLES_MAX)

    # --- WALIDACJA MINIMALNEGO DYSTANSU SL/TP ---
    stops_level = symbol_info.trade_stops_level
    tick_size = symbol_info.trade_tick_size
    min_stop_distance = stops_level * tick_size

    # Zwiększ minimalny ATR i dystans
    min_atr = max(atr, min_stop_distance * 5)

    if action == 0:  # BUY
        sl = min(sl, price - min_stop_distance * 5)
        tp = max(tp, price + min_stop_distance * 10, price + min_atr * 3)
        if abs(tp - price) < min_stop_distance * 5:
            tp = price + min_stop_distance * 5
    else:  # SELL
        sl = max(sl, price + min_stop_distance * 5)
        tp = min(tp, price - min_stop_distance * 10, price - min_atr * 3)
        if abs(tp - price) < min_stop_distance * 5:
            tp = price - min_stop_distance * 5

    # Jeśli TP == price, ustaw TP dalej!
    if abs(tp - price) < min_stop_distance * 5:
        if action == 0:
            tp = price + min_stop_distance * 10
        else:
            tp = price - min_stop_distance * 10

    # Nie otwieraj pozycji, jeśli ATR jest zbyt niski
    if atr < ATR_MIN:
        logging.info(f"⚠️ ATR zbyt niski ({atr:.5f}) dla {symbol}, pomijam sygnał.")
        try:
            mssql.insert_diagnostic(event_type="FILTER_ATR", symbol=symbol,
                                    ml_decision=action, ml_confidence=pred_proba,
                                    filter_blocked=True,
                                    filter_reason=f"ATR={atr:.5f} < ATR_MIN={ATR_MIN}",
                                    atr=atr, action_taken="SKIP")
        except Exception as e:
            logging.warning(f"[diagnostic] Błąd zapisu FILTER_ATR: {e}")
        return
    
    # --- Variant C: Filtr R:R (min TP/SL ratio) ---
    sl_distance = abs(price - sl)
    tp_distance = abs(tp - price)
    if sl_distance > 0:
        rr_ratio = tp_distance / sl_distance
        if rr_ratio < MIN_RR_RATIO:
            logging.info(
                f"⛔ R:R za niski ({rr_ratio:.2f} < {MIN_RR_RATIO}) dla {symbol}, "
                f"TP_dist={tp_distance:.5f}, SL_dist={sl_distance:.5f}. Blokuję."
            )
            try:
                mssql.insert_diagnostic(event_type="FILTER_RR", symbol=symbol,
                                        ml_decision=action, ml_confidence=pred_proba,
                                        filter_blocked=True,
                                        filter_reason=f"RR={rr_ratio:.2f} < {MIN_RR_RATIO}",
                                        atr=atr, rr_ratio=rr_ratio, action_taken="SKIP")
            except Exception as e:
                logging.warning(f"[diagnostic] Błąd zapisu FILTER_RR: {e}")
            return

    # --- Variant C: Filtr spreadu (spread > 20% SL → block) ---
    spread_points = abs(tick.ask - tick.bid)
    if sl_distance > 0 and spread_points / sl_distance > SPREAD_FILTER_PCT:
        logging.info(
            f"⛔ Spread za duży ({spread_points:.5f} = {spread_points/sl_distance*100:.1f}% SL) "
            f"dla {symbol}. Limit={SPREAD_FILTER_PCT*100:.0f}%. Blokuję."
        )
        try:
            mssql.insert_diagnostic(event_type="FILTER_SPREAD", symbol=symbol,
                                    ml_decision=action, ml_confidence=pred_proba,
                                    filter_blocked=True,
                                    filter_reason=(
                                        f"spread={spread_points:.5f} "
                                        f"={spread_points/sl_distance*100:.1f}%SL"
                                    ),
                                    atr=atr, action_taken="SKIP")
        except Exception:
            pass
        return
    
    # 🔢 Oblicz dynamicznie maksymalny możliwy lot (80% wolnej marży)
    # margin_per_lot = symbol_info.margin_initial
    # if margin_per_lot is None or margin_per_lot == 0:
    #     logging.warning(f"⚠️ Nie można pobrać margin_initial dla {symbol} — używam domyślnej wartości 1000.0")
    #     margin_per_lot = 1000.0

    # margin_available = account_info.margin_free
    # max_possible_lot = margin_available / margin_per_lot * 0.70
    # lot = round(min(max_possible_lot, symbol_info.volume_max), 1)

    # if lot < symbol_info.volume_min:
    #     logging.warning(f"⚠️ Wolumen {lot} < minimalny ({symbol_info.volume_min}) dla {symbol} — pominięto.")
    #     return

    sl_distance = abs(price - sl)
    lot = calculate_lot_size(symbol, sl_distance, risk_percent=2.0, confidence=pred_proba, use_min_lot=use_min_lot)

    # WALIDACJA I LOGOWANIE
    logging.info(
        f"🟢 {symbol} | price={price:.5f}, SL={sl:.5f}, TP={tp:.5f}, SL_dist={sl_distance:.5f}, ATR={atr:.5f}, lot={lot}"
    )

    if action == 0:  # BUY
        if sl > price - min_stop_distance * 2:
            sl = price - min_stop_distance * 2
        if tp < price + min_stop_distance * 2:
            tp = price + min_stop_distance * 2
    else:  # SELL
        if sl < price + min_stop_distance * 2:
            sl = price + min_stop_distance * 2
        if tp > price - min_stop_distance * 2:
            tp = price - min_stop_distance * 2

    if abs(tp - price) < min_stop_distance * 2:
        if action == 0:
            tp = price + min_stop_distance * 3
        else:
            tp = price - min_stop_distance * 3

    # Teraz tworzysz request i wysyłasz zlecenie
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": mt5.ORDER_TYPE_BUY if action == 0 else mt5.ORDER_TYPE_SELL,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 10,
        "magic": MAGIC,
        "comment": f"AI Forex Bot {VERSION}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_FOK,
    }

    result = mt5.order_send(request)

    if result is None:
        logging.error(f"❌ order_send() zwrócił None dla {symbol}. Sprawdź połączenie z MT5. {request}")
        print(f"[ERROR] order_send() zwrócił None dla {symbol}. Sprawdź połączenie z MT5. {request}")
        reconnect_mt5()
        return
    
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        logging.warning(f"⚠️ Zlecenie nie doszło do skutku: {result}")

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        logging.info(f"✅ Zlecenie: {result.order}, {symbol}, {'BUY' if action==0 else 'SELL'}, lot={lot}, prob={pred_proba:.2f}, atr={atr}, price={price:.5f}, SL={sl:.5f}, TP={tp:.5f}, comment={result.comment}")
        log_trade(
            symbol=symbol,
            direction="BUY" if action == 0 else "SELL",
            price=price,
            sl=sl,
            tp=tp,
            volume=lot,
            prediction=pred_proba,
            retcode="OK",
            result=result.order if hasattr(result, "order") else "-",
            confidence=pred_proba,
            ud='S',
            done='Nie',
            atr=atr,
            profit=0.00
        )
        return

    elif result.retcode == 10019:  # No money
        logging.warning(f"⚠️ Brak środków: {symbol}, lot={lot:.2f}. Zmniejszam i próbuję ponownie...")
        # lot = round(lot - 0.01, 2)
        # attempt += 1
    else:
        logging.error(f"❌ Błąd zlecenia {symbol}: {result.retcode} — {result.comment}")
        print(f"[ERROR] Błąd zlecenia {symbol}: {result.retcode} - {result.comment}")

    logging.error(f"❌ Nie udało się zrealizować zlecenia dla {symbol}.")

def should_close_negative_position(df, pos, model=None, scaler=None, feature_columns=None):

    # Zaawansowana analiza minusowej pozycji:
    # - Trend (EMA, ADX)
    # - Korekta (RSI, Fibo)
    # - Formacje świecowe (np. engulfing, hammer)
    # - Predykcja ML (jeśli model podany)
    # Zwraca True jeśli należy zamknąć, False jeśli warto dać szansę.

    # 1. Trend
    ema_fast = talib.EMA(df['close'], timeperiod=20).iloc[-1]
    ema_slow = talib.EMA(df['close'], timeperiod=50).iloc[-1]
    adx = talib.ADX(df['high'], df['low'], df['close'], timeperiod=14).iloc[-1]
    trend_up = ema_fast > ema_slow and adx > 20
    trend_down = ema_fast < ema_slow and adx > 20

    # 2. Korekta (RSI, Fibo)
    rsi = talib.RSI(df['close'], timeperiod=14).iloc[-1]
    fibo_382 = df['low'].min() + 0.382 * (df['high'].max() - df['low'].min())
    fibo_618 = df['low'].min() + 0.618 * (df['high'].max() - df['low'].min())
    price = df['close'].iloc[-1]
    near_fibo = abs(price - fibo_382) < abs(price - fibo_618)

    # 3. Formacje świecowe
    engulfing = talib.CDLENGULFING(df['open'], df['high'], df['low'], df['close']).iloc[-1]
    hammer = talib.CDLHAMMER(df['open'], df['high'], df['low'], df['close']).iloc[-1]
    reversal_signal = engulfing != 0 or hammer != 0

    # 4. Predykcja ML (jeśli model podany)
    ml_signal = None
    if model is not None and scaler is not None and feature_columns is not None:
        try:
            features_df = generate_features(df)
            formations_df = detect_candle_formations(df)
            for col in formations_df.columns:
                if col not in features_df.columns:
                    features_df[col] = formations_df[col]
            features_df.columns = features_df.columns.astype(str)
            missing = set(feature_columns) - set(features_df.columns)
            for col in missing:
                features_df[col] = 0.0
            X = features_df[feature_columns].iloc[[-1]]
            X_scaled = scaler.transform(X)
            pred_proba = model.predict_proba(X_scaled)[0]
            decision = int(np.argmax(pred_proba))
            confidence = float(pred_proba[decision])
            ml_signal = (decision, confidence)
        except Exception as e:
            logging.error(f"❌ ML analiza błędna: {e}")

    # Decyzja: zamknij jeśli...
    # - Trend przeciwny do pozycji i nie ma sygnału odbicia
    # - RSI skrajne (np. >70 dla SELL, <30 dla BUY)
    # - ML model wskazuje niską szansę na odbicie
    # - Brak formacji odwrócenia

    close_decision = False
    if pos.type == 0:  # BUY
        if trend_down and not reversal_signal and rsi < 40:
            close_decision = True
        if ml_signal and ml_signal[0] == 1 and ml_signal[1] < PREDICT_PROBA_THRESHOLD:
            close_decision = True
    else:  # SELL
        if trend_up and not reversal_signal and rsi > 60:
            close_decision = True
        if ml_signal and ml_signal[0] == 0 and ml_signal[1] < PREDICT_PROBA_THRESHOLD:
            close_decision = True

    # Jeśli cena blisko Fibo, daj szansę na odbicie
    if near_fibo and not reversal_signal:
        close_decision = False

    return close_decision


def calculate_npm_score(df, pos, r_multiple, duration_hours):
    """Negative Position Manager — oblicz NPM Score (0-100).

    Składniki:
    - Momentum H1 (20%): EMA(9) vs EMA(21) — czy momentum wraca na korzyść?
    - RSI extremum (15%): RSI w strefie sprzyjającej odwróceniu
    - ATR contraction (15%): maleje impet ruchu przeciwnego
    - Odległość do S/R (20%): cena przy kluczowym poziomie fibo
    - Czas w stracie (15%): kara rosnąca z czasem
    - Koszt utrzymania (15%): swap penalty
    """
    score = 0.0
    is_buy = (pos.type == 0)

    # --- 1. Momentum (20 pkt max) ---
    ema9 = talib.EMA(df['close'], timeperiod=9).iloc[-1]
    ema21 = talib.EMA(df['close'], timeperiod=21).iloc[-1]
    if is_buy:
        # Dla BUY: momentum wraca jeśli EMA9 > EMA21 lub się zbliża
        mom_ratio = (ema9 - ema21) / ema21 * 100 if ema21 != 0 else 0
    else:
        mom_ratio = (ema21 - ema9) / ema21 * 100 if ema21 != 0 else 0
    # mom_ratio > 0 = korzystny momentum, scale 0-20
    score_momentum = max(0, min(20, (mom_ratio + 0.5) * 20))
    score += score_momentum

    # --- 2. RSI extremum (15 pkt max) ---
    rsi = talib.RSI(df['close'], timeperiod=14).iloc[-1]
    if is_buy:
        # BUY: niskie RSI = szansa na odbicie (oversold)
        score_rsi = max(0, min(15, (50 - rsi) / 50 * 15)) if rsi < 50 else 0
    else:
        # SELL: wysokie RSI = szansa na spadek (overbought)
        score_rsi = max(0, min(15, (rsi - 50) / 50 * 15)) if rsi > 50 else 0
    score += score_rsi

    # --- 3. ATR contraction (15 pkt max) ---
    atr5 = talib.ATR(df['high'], df['low'], df['close'], timeperiod=5).iloc[-1]
    atr14 = talib.ATR(df['high'], df['low'], df['close'], timeperiod=14).iloc[-1]
    if atr14 > 0:
        atr_ratio = atr5 / atr14
        # atr_ratio < 1 = ruch zwalnia (korzystne), scale: 0.5→15, 1.5→0
        score_atr = max(0, min(15, (1.5 - atr_ratio) * 15))
    else:
        score_atr = 7.5
    score += score_atr

    # --- 4. Odległość do S/R — fibo (20 pkt max) ---
    high_swing = df['high'].max()
    low_swing = df['low'].min()
    fibo_382 = low_swing + 0.382 * (high_swing - low_swing)
    fibo_618 = low_swing + 0.618 * (high_swing - low_swing)
    price = df['close'].iloc[-1]
    # Bliskość do poziomu fibo = szansa na reakcję
    dist_382 = abs(price - fibo_382) / (high_swing - low_swing) if (high_swing - low_swing) > 0 else 1
    dist_618 = abs(price - fibo_618) / (high_swing - low_swing) if (high_swing - low_swing) > 0 else 1
    min_fibo_dist = min(dist_382, dist_618)
    # Blisko fibo (<5%) = max punkty, daleko (>20%) = 0
    score_sr = max(0, min(20, (0.20 - min_fibo_dist) / 0.20 * 20))
    score += score_sr

    # --- 5. Czas w stracie (15 pkt max, kara rosnąca) ---
    # 0h = 15 pkt, 48h+ = 0 pkt
    score_time = max(0, min(15, 15 - (duration_hours / 48) * 15))
    score += score_time

    # --- 6. Swap cost penalty (15 pkt max) ---
    swap = abs(pos.swap) if hasattr(pos, 'swap') else 0
    loss = abs(pos.profit) if pos.profit < 0 else 1
    swap_ratio = swap / loss if loss > 0 else 0
    # swap < 1% straty = 15 pkt, swap > 10% = 0
    score_swap = max(0, min(15, 15 - (swap_ratio / 0.10) * 15))
    score += score_swap

    return round(min(100, max(0, score)), 1)


def get_npm_escalation(r_multiple, npm_score):
    """Wyznacz poziom eskalacji NPM.

    Returns: 'WATCH', 'ALERT', lub 'CRITICAL'
    """
    if r_multiple <= NPM_CRITICAL_R or npm_score < NPM_CRITICAL_NPM:
        return 'CRITICAL'
    if r_multiple <= NPM_ALERT_R or npm_score < NPM_ALERT_NPM:
        return 'ALERT'
    return 'WATCH'


def is_weekend_recovery_window():
    """Sprawdź czy jesteśmy w oknie weekend recovery.

    Piątek od NPM_WEEKEND_BLOCK_HOUR UTC do niedzieli 23:59 UTC.
    W tym oknie nie zamykamy pozycji ujemnych (chyba że hard cap).
    """
    if not NPM_WEEKEND_RECOVERY:
        return False
    now_utc = datetime.utcnow()
    weekday = now_utc.weekday()  # 0=Mon, 4=Fri, 5=Sat, 6=Sun
    if weekday == 4 and now_utc.hour >= NPM_WEEKEND_BLOCK_HOUR:
        return True  # Piątek wieczór
    if weekday in (5, 6):
        return True  # Sobota/Niedziela
    return False


def update_trailing_sl():
    """4-stopniowy mechanizm ochrony zysku oparty na R-multiple.

    R = |current_price - entry_price| / |entry_price - initial_sl|

    Stage 0 (R < 1.0): oryginalny SL — normalny risk
    Stage 1 (R >= 1.0): SL → break-even (entry + spread buffer) — zero risk
    Stage 2 (R >= 1.5): SL → entry + 0.5R — gwarantowany zysk
    Stage 3 (R >= 2.0): SL = extreme_price − 1.0 ATR — trailing za ceną
    Stage 4 (R >= 3.0): SL = extreme_price − 0.5 ATR — ciasny trailing
    """
    global extreme_price_dict, open_time_dict

    try:
        with open("extreme_price_dict.pkl", "rb") as f:
            extreme_price_dict = pickle.load(f)
    except Exception:
        pass

    positions = mt5.positions_get()
    if not positions:
        return

    for pos in positions:
        symbol = pos.symbol
        ticket = pos.ticket
        profit = pos.profit
        is_buy = (pos.type == 0)

        # --- Czas otwarcia ---
        if ticket not in open_time_dict:
            open_time_dict[ticket] = pos.time

        # --- Śledzenie ekstremalnej ceny (najkorzystniejszej) ---
        current_price = pos.price_current
        if ticket not in extreme_price_dict:
            extreme_price_dict[ticket] = current_price
        else:
            if is_buy:
                extreme_price_dict[ticket] = max(extreme_price_dict[ticket], current_price)
            else:
                extreme_price_dict[ticket] = min(extreme_price_dict[ticket], current_price)

        # Persystencja extreme_price_dict
        try:
            with open("extreme_price_dict.pkl", "wb") as f:
                pickle.dump(extreme_price_dict, f)
        except Exception:
            pass

        # --- Oblicz 1R (Initial Risk w jednostkach cenowych) ---
        entry_price = pos.price_open
        initial_sl = pos.sl
        symbol_info = mt5.symbol_info(symbol)
        digits = symbol_info.digits if symbol_info else 5
        spread_buffer = symbol_info.spread * symbol_info.point * 2 if symbol_info else 0.0

        one_r = abs(entry_price - initial_sl) if initial_sl and initial_sl != 0 else None
        if one_r is None or one_r < symbol_info.point * 10:
            # Fallback: jeśli SL nie ustawiony lub za blisko, użyj ATR
            data = get_data(symbol)
            if data is not None:
                one_r = calculate_atr(data) * SL_ATR_MULTIPLIER
            else:
                continue

        # --- Oblicz R-multiple ---
        if is_buy:
            r_multiple = (current_price - entry_price) / one_r
        else:
            r_multiple = (entry_price - current_price) / one_r

        extreme = extreme_price_dict[ticket]

        logging.info(
            f"ℹ️ #{ticket} ({symbol}) {'BUY' if is_buy else 'SELL'}: "
            f"R={r_multiple:.2f}, profit={profit:.2f}, "
            f"entry={entry_price:.{digits}f}, current={current_price:.{digits}f}, "
            f"extreme={extreme:.{digits}f}, SL={initial_sl:.{digits}f}, 1R={one_r:.{digits}f}, "
            f"duration={common.format_time(open_time_dict[ticket] - time.time())}"
        )

        # --- Inkubator: nie ruszaj przez MIN_HOLD_SECONDS ---
        if abs(open_time_dict[ticket] - time.time()) < MIN_HOLD_SECONDS:
            continue

        # --- Variant C: Time-based exit — zamknij ujemną pozycję po TIME_EXIT_HOURS ---
        _pos_duration_h = abs(open_time_dict[ticket] - time.time()) / 3600

        # === NPM: Negative Position Manager ===
        if r_multiple < 0 and profit < 0:

            # --- Fix B: Timeout fallback — działa bez get_data() ---
            if _pos_duration_h >= TIME_EXIT_HOURS and r_multiple <= NPM_ALERT_R:
                logging.warning(
                    f"⏰ TIME_EXIT FALLBACK #{ticket} ({symbol}): "
                    f"{_pos_duration_h:.1f}h >= {TIME_EXIT_HOURS}h, R={r_multiple:.2f} <= {NPM_ALERT_R}. "
                    f"Zamykam blisko SL zamiast market price."
                )
                # FIX: Zamiast zamykać na market price, zamknij limit order blisko SL
                _close_position_at_sl(pos)
                continue

            data = get_data(symbol)
            if data is None:
                # Fix A: loguj błąd zamiast cichego continue
                logging.error(
                    f"❌ NPM #{ticket} ({symbol}): get_data() zwróciło None — "
                    f"NPM pominięty. R={r_multiple:.2f}, profit={profit:.2f}, "
                    f"duration={_pos_duration_h:.1f}h"
                )
                continue

            # --- NPM Score ---
            npm_score = calculate_npm_score(data, pos, r_multiple, _pos_duration_h)
            escalation = get_npm_escalation(r_multiple, npm_score)
            direction_str = "BUY" if is_buy else "SELL"
            weekend_window = is_weekend_recovery_window()

            # --- Recovery Probability ---
            recovery_stats = mssql.get_recovery_stats(symbol, r_multiple - 0.3, r_multiple + 0.3)
            recovery_pct = recovery_stats['recovery_pct'] if recovery_stats else -1

            # --- Swap cost dzienny (szacunek) ---
            swap_daily = abs(pos.swap) / max(_pos_duration_h / 24, 0.01) if pos.swap != 0 else 0

            logging.info(
                f"📊 NPM #{ticket} ({symbol}) {direction_str}: "
                f"NPM={npm_score:.0f}, R={r_multiple:.2f}, esc={escalation}, "
                f"recovery={recovery_pct:.0f}%, swap/d={swap_daily:.2f}, "
                f"duration={_pos_duration_h:.1f}h, weekend={weekend_window}"
            )

            # --- Loguj do bazy ---
            action_taken = "MONITOR"
            try:
                # === HARD CAP: bezwzględne zamknięcie ===
                if r_multiple <= NPM_HARD_CAP_R:
                    action_taken = "HARD_CAP_CLOSE"
                    logging.critical(
                        f"🔴 NPM HARD CAP #{ticket} ({symbol}): R={r_multiple:.2f} <= {NPM_HARD_CAP_R}. "
                        f"Zamykam 100% — bezwzględny limit."
                    )
                    _close_position(pos)

                # === Weekend recovery window: nie zamykaj (chyba że hard cap powyżej) ===
                elif weekend_window and escalation in ('ALERT', 'CRITICAL'):
                    action_taken = "WEEKEND_HOLD"
                    logging.info(
                        f"🌅 NPM #{ticket} ({symbol}): Weekend recovery window. "
                        f"Wstrzymuję zamknięcie (R={r_multiple:.2f}, NPM={npm_score:.0f}). "
                        f"Szansa na poniedziałkowy gap."
                    )

                # === Time-based exit (zachowane z Variant C, ale podlega weekend window) ===
                elif _pos_duration_h >= TIME_EXIT_HOURS and escalation == 'CRITICAL':
                    action_taken = "TIME_EXIT"
                    logging.warning(
                        f"⏰ TIME_EXIT #{ticket} ({symbol}): R={r_multiple:.2f}, {_pos_duration_h:.1f}h, "
                        f"NPM={npm_score:.0f} CRITICAL + time limit. Zamykam blisko SL."
                    )
                    # FIX: Zamiast zamykać na market, zamknij blisko SL
                    _close_position_at_sl(pos)

                # === CRITICAL: skalowane zamknięcie ===
                elif escalation == 'CRITICAL':
                    if r_multiple <= NPM_SCALED_100_R and npm_score < 20:
                        # Zamknij 100%
                        action_taken = "CRITICAL_CLOSE_100"
                        logging.warning(
                            f"🔴 NPM CRITICAL #{ticket} ({symbol}): R={r_multiple:.2f}, NPM={npm_score:.0f}. "
                            f"Zamykam 100%."
                        )
                        _close_position(pos)
                    elif r_multiple <= NPM_SCALED_50_R and npm_score < NPM_CRITICAL_NPM \
                            and ticket not in npm_scaled_exit_tickets:
                        # Zamknij 50%
                        _vol = pos.volume
                        _close_vol = round(_vol * 0.5, 2)
                        _min_vol = symbol_info.volume_min if symbol_info else 0.01
                        if _close_vol >= _min_vol and (_vol - _close_vol) >= _min_vol:
                            _close_type = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
                            _tick = mt5.symbol_info_tick(symbol)
                            _close_price = _tick.bid if is_buy else _tick.ask
                            _partial_req = {
                                "action": mt5.TRADE_ACTION_DEAL,
                                "symbol": symbol,
                                "volume": _close_vol,
                                "type": _close_type,
                                "position": ticket,
                                "price": _close_price,
                                "deviation": 10,
                                "magic": pos.magic,
                                "comment": f"NPM CritExit R{r_multiple:.1f} {VERSION}",
                                "type_time": mt5.ORDER_TIME_GTC,
                                "type_filling": mt5.ORDER_FILLING_FOK,
                            }
                            _partial_result = mt5.order_send(_partial_req)
                            if _partial_result and _partial_result.retcode == mt5.TRADE_RETCODE_DONE:
                                npm_scaled_exit_tickets.add(ticket)
                                action_taken = "CRITICAL_CLOSE_50"
                                logging.warning(
                                    f"🔴 NPM CRITICAL #{ticket} ({symbol}): zamknięto {_close_vol}/{_vol} lot. "
                                    f"R={r_multiple:.2f}, NPM={npm_score:.0f}."
                                )
                            else:
                                action_taken = "CRITICAL_CLOSE_50_FAIL"
                        else:
                            action_taken = "CRITICAL_MONITOR"
                    else:
                        action_taken = "CRITICAL_MONITOR"
                        # Sprawdź ML/TA jako dodatkowy sygnał
                        try:
                            should_close = should_close_negative_position(
                                data, pos,
                                model=joblib.load(f"{MODEL_PATH}/{symbol}_model.pkl"),
                                scaler=joblib.load(f"{MODEL_PATH}/{symbol}_scaler.pkl"),
                                feature_columns=joblib.load(f"{MODEL_PATH}/{symbol}_feature_columns.pkl")
                            )
                            if should_close:
                                action_taken = "CRITICAL_ML_CLOSE"
                                logging.warning(
                                    f"🔴 NPM CRITICAL + ML #{ticket} ({symbol}): R={r_multiple:.2f}, NPM={npm_score:.0f}. "
                                    f"ML potwierdza zamknięcie."
                                )
                                _close_position(pos)
                        except Exception as e:
                            logging.error(f"❌ NPM ML analysis error #{ticket}: {e}")

                # === ALERT: ściągnij SL, monitoruj uważnie ===
                elif escalation == 'ALERT':
                    action_taken = "ALERT_TIGHTEN"
                    # Ściągnij SL do -NPM_TIGHTEN_SL_FACTOR * 1R od entry
                    tighter_sl = entry_price - one_r * NPM_TIGHTEN_SL_FACTOR if is_buy \
                        else entry_price + one_r * NPM_TIGHTEN_SL_FACTOR
                    tighter_sl = round(tighter_sl, digits)
                    current_sl = pos.sl
                    # Tylko jeśli tighter_sl jest bliżej ceny niż obecny SL
                    sl_tighter = (is_buy and (current_sl == 0 or tighter_sl > current_sl)) or \
                                 (not is_buy and (current_sl == 0 or tighter_sl < current_sl))
                    if sl_tighter:
                        modify_req = {
                            "action": mt5.TRADE_ACTION_SLTP,
                            "position": ticket,
                            "sl": tighter_sl,
                            "tp": pos.tp,
                            "symbol": symbol,
                            "magic": pos.magic,
                            "comment": f"NPM Alert SL {VERSION}",
                        }
                        result = mt5.order_send(modify_req)
                        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                            logging.info(
                                f"🟡 NPM ALERT #{ticket} ({symbol}): SL ściągnięty "
                                f"{current_sl:.{digits}f} → {tighter_sl:.{digits}f} "
                                f"(limit -{NPM_TIGHTEN_SL_FACTOR}R)"
                            )
                        else:
                            _rc = result.retcode if result else "None"
                            logging.warning(f"⚠️ NPM ALERT SL modify fail #{ticket}: {_rc}")

                # === WATCH: tylko monitorowanie ===
                else:
                    action_taken = "WATCH"

            except Exception as npm_e:
                logging.error(f"❌ NPM error #{ticket} ({symbol}): {npm_e}")
                action_taken = f"ERROR: {npm_e}"

            # --- Zapisz do tabeli NPM ---
            try:
                mssql.insert_npm_log(
                    ticket=ticket, symbol=symbol, direction=direction_str,
                    npm_score=npm_score, r_multiple=r_multiple,
                    escalation=escalation, recovery_prob=recovery_pct,
                    action_taken=action_taken, swap_cost_daily=swap_daily,
                    entry_price=entry_price, current_price=current_price,
                    duration_hours=_pos_duration_h, profit=profit,
                    weekend_window=weekend_window
                )
            except Exception as log_e:
                logging.error(f"❌ NPM log error #{ticket}: {log_e}")

            continue

        # --- Variant C: Częściowe zamknięcie 50% pozycji przy R >= PARTIAL_CLOSE_R ---
        if r_multiple >= PARTIAL_CLOSE_R and ticket not in partial_closed_tickets:
            _vol = pos.volume
            _close_vol = round(_vol * PARTIAL_CLOSE_PCT, 2)
            _min_vol = symbol_info.volume_min if symbol_info else 0.01
            if _close_vol >= _min_vol and (_vol - _close_vol) >= _min_vol:
                _close_type = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
                _close_price = mt5.symbol_info_tick(symbol)
                _close_price = _close_price.bid if is_buy else _close_price.ask
                _partial_req = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": symbol,
                    "volume": _close_vol,
                    "type": _close_type,
                    "position": ticket,
                    "price": _close_price,
                    "deviation": 10,
                    "magic": pos.magic,
                    "comment": f"PartClose R{r_multiple:.1f} {VERSION}",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_FOK,
                }
                _partial_result = mt5.order_send(_partial_req)
                if _partial_result and _partial_result.retcode == mt5.TRADE_RETCODE_DONE:
                    partial_closed_tickets.add(ticket)
                    logging.info(
                        f"✂️ Częściowe zamknięcie #{ticket} ({symbol}): {_close_vol}/{_vol} lot "
                        f"przy R={r_multiple:.2f}. Zostaje {_vol - _close_vol} lot."
                    )
                else:
                    _rc = _partial_result.retcode if _partial_result else "None"
                    logging.warning(f"⚠️ Partial close fail #{ticket} ({symbol}): {_rc}")

        # --- Stage 0 / Negative Trailing: R < TRAIL_BE_R
        if r_multiple < TRAIL_BE_R:
            # === NEGATIVE TRAILING: Dynamiczny trailing stop dla strat ===
            # Gdy R pada poniżej TRAIL_NEG_ACTIVE_R (np. -0.5), aktywuj dynamic loss trailing
            # Śledź najgorszą cenę i ograniczaj nią do max TRAIL_NEG_MAX_LOSS_R (np. -2.0R)
            
            if r_multiple <= TRAIL_NEG_ACTIVE_R and r_multiple > TRAIL_NEG_MAX_LOSS_R:
                data = get_data(symbol)
                if data is not None:
                    atr = calculate_atr(data)
                    
                    # Nowy SL: najgorsza cena + buffer (TRAIL_NEG_FACTOR * ATR)
                    if is_buy:
                        neg_sl = extreme + atr * TRAIL_NEG_FACTOR  # dla SELL (short), extreme to min cena
                    else:
                        neg_sl = extreme - atr * TRAIL_NEG_FACTOR  # dla BUY (long), extreme to max cena
                    
                    neg_sl = round(neg_sl, digits)
                    current_sl = pos.sl
                    
                    # Sprawdzenie czy SL poprawia się (zbliża do entry, tzn. zmniejsza stratę)
                    sl_improves_loss = (
                        (is_buy and (current_sl is None or current_sl == 0 or neg_sl > current_sl)) or
                        (not is_buy and (current_sl is None or current_sl == 0 or neg_sl < current_sl))
                    )
                    
                    if sl_improves_loss:
                        # Dodatkowa ochrona: nie pozwól gorsze niż TRAIL_NEG_MAX_LOSS_R
                        hard_limit_sl = entry_price - one_r * abs(TRAIL_NEG_MAX_LOSS_R) if is_buy \
                                       else entry_price + one_r * abs(TRAIL_NEG_MAX_LOSS_R)
                        
                        # Wybierz lepszy (bliższy entry) z dwóch opcji
                        if is_buy:
                            neg_sl = max(neg_sl, hard_limit_sl)
                        else:
                            neg_sl = min(neg_sl, hard_limit_sl)
                        
                        logging.info(
                            f"🔴 DynNegTrail | #{ticket} ({symbol}): R={r_multiple:.2f}, "
                            f"SL: {current_sl:.{digits}f} → {neg_sl:.{digits}f}, "
                            f"worst={extreme:.{digits}f}, ATR={atr:.{digits}f}"
                        )
                        
                        modify_request = {
                            "action": mt5.TRADE_ACTION_SLTP,
                            "position": ticket,
                            "sl": neg_sl,
                            "tp": pos.tp,
                            "symbol": symbol,
                            "magic": pos.magic,
                            "comment": f"DynNegTrail R{r_multiple:.1f} {VERSION}",
                        }
                        result = mt5.order_send(modify_request)
                        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                            logging.info(
                                f"✅ DynNegTrail #{ticket} ({symbol}): SL zaktualizowany. "
                                f"R={r_multiple:.2f}, max loss limit={TRAIL_NEG_MAX_LOSS_R}R"
                            )
                        else:
                            _rc = result.retcode if result else "None"
                            logging.warning(f"⚠️ DynNegTrail SL modify fail #{ticket}: {_rc}")
            
            continue

        # --- Oblicz ATR dla trailing ---
        data = get_data(symbol)
        if data is None:
            continue
        atr = calculate_atr(data)

        # --- Wyznacz nowy SL na podstawie stage'a ---
        new_sl = None

        if r_multiple >= TRAIL_TIGHT_R:
            # Stage 4: Ciasny trailing — 0.5 ATR od extremum
            if is_buy:
                new_sl = extreme - atr * TRAIL_TIGHT_FACTOR
            else:
                new_sl = extreme + atr * TRAIL_TIGHT_FACTOR
            stage = 4
        elif r_multiple >= TRAIL_ATR_R:
            # Stage 3: Trailing — 1.0 ATR od extremum
            if is_buy:
                new_sl = extreme - atr * TRAIL_ATR_FACTOR
            else:
                new_sl = extreme + atr * TRAIL_ATR_FACTOR
            stage = 3
        elif r_multiple >= TRAIL_LOCK_R:
            # Stage 2: Lock profit — entry + 0.5R
            if is_buy:
                new_sl = entry_price + one_r * TRAIL_LOCK_FRAC
            else:
                new_sl = entry_price - one_r * TRAIL_LOCK_FRAC
            stage = 2
        elif r_multiple >= TRAIL_BE_R:
            # Stage 1: Break-even — entry + spread buffer
            if is_buy:
                new_sl = entry_price + spread_buffer
            else:
                new_sl = entry_price - spread_buffer
            stage = 1

        if new_sl is None:
            continue

        new_sl = round(new_sl, digits)
        current_sl = pos.sl

        # --- Sprawdź czy nowy SL jest lepszy niż obecny ---
        sl_improves = (
            (is_buy and (current_sl is None or current_sl == 0 or new_sl > current_sl)) or
            (not is_buy and (current_sl is None or current_sl == 0 or new_sl < current_sl))
        )

        if not sl_improves:
            continue

        logging.info(
            f"🔒 Stage {stage} | #{ticket} ({symbol}): R={r_multiple:.2f}, "
            f"SL: {current_sl:.{digits}f} → {new_sl:.{digits}f}, "
            f"extreme={extreme:.{digits}f}, ATR={atr:.{digits}f}"
        )

        modify_request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "sl": new_sl,
            "tp": pos.tp,
            "symbol": symbol,
            "magic": pos.magic,
            "comment": f"Trail S{stage} R{r_multiple:.1f} {VERSION}",
        }
        result = mt5.order_send(modify_request)
        if result is None:
            logging.error(f"❌ order_send() None przy trailing SL {ticket} ({symbol}). {modify_request}")
            reconnect_mt5()
            continue
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            logging.info(f"✅ SL Stage {stage}: {symbol} | SL: {new_sl:.{digits}f}")
        else:
            logging.warning(f"⚠️ Trailing SL fail {symbol}: {result.retcode} — {result.comment}")


def _close_position_at_sl(pos):
    """Zamknij pozycję limit order blisko SL zamiast na market price.
    Unika dramatycznych strat z powodu zmian ceny między decyzją a wykonaniem."""
    is_buy = (pos.type == 0)
    symbol_info = mt5.symbol_info(pos.symbol)
    tick = mt5.symbol_info_tick(pos.symbol)
    if tick is None or symbol_info is None:
        logging.error(f"❌ Brak danych dla {pos.symbol} przy zamykaniu #{pos.ticket} na SL")
        # Fallback: zamknij na market price
        _close_position(pos)
        return
    
    # Limit order 5 pips poniżej SL dla SELL, 5 pips powyżej dla BUY
    sl_limit = float(pos.sl) if pos.sl else tick.bid if is_buy else tick.ask
    offset_pips = 0.00005 if symbol_info.digits == 5 else 0.0005  # 5 pips offset
    
    if is_buy:
        limit_price = sl_limit + offset_pips
    else:
        limit_price = sl_limit - offset_pips
    
    close_request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "position": pos.ticket,
        "symbol": pos.symbol,
        "volume": pos.volume,
        "type": mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY,
        "price": limit_price,
        "deviation": 5,
        "magic": pos.magic,
        "comment": f"Close at SL {VERSION}",
    }
    result = mt5.order_send(close_request)
    if result is None:
        logging.error(f"❌ Nie udało się wysłać close order #{pos.ticket}. Fallback do market.")
        _close_position(pos)
        return
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        logging.info(f"✅ Zamknięto #{pos.ticket} ({pos.symbol}) blisko SL za {limit_price:.5f}.")
    else:
        logging.warning(f"⚠️ Close order #{pos.ticket} ma status {result.retcode} — {result.comment}. Retry market close.")
        _close_position(pos)

def _close_position(pos):
    """Pomocnicza: zamknij pozycję MT5 na market price."""
    is_buy = (pos.type == 0)
    tick = mt5.symbol_info_tick(pos.symbol)
    if tick is None:
        logging.error(f"❌ Brak ticka dla {pos.symbol} przy zamykaniu #{pos.ticket}")
        return
    close_request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "position": pos.ticket,
        "symbol": pos.symbol,
        "volume": pos.volume,
        "type": mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY,
        "price": tick.bid if is_buy else tick.ask,
        "deviation": 10,
        "magic": pos.magic,
        "comment": f"Close by analysis {VERSION}",
    }
    result = mt5.order_send(close_request)
    if result is None:
        logging.error(f"❌ order_send() None przy zamykaniu #{pos.ticket} ({pos.symbol}). {close_request}")
        reconnect_mt5()
        return
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        logging.info(f"✅ Zamknięto #{pos.ticket} ({pos.symbol}).")
    else:
        logging.error(f"❌ Nie zamknięto #{pos.ticket} ({pos.symbol}): {result.retcode} — {result.comment}")

# Sprawdza, czy istnieje już otwarta pozycja na symbol w danym kierunku
# oraz czy nie była zamknięta transakcja w tym samym kierunku tego samego dnia

def is_not_duplicate_trade(sym, direction):

    # Zwraca True jeśli w historii zamkniętych transakcji z bieżącego dnia NIE było transakcji
    # dla danego symbolu i kierunku (direction), False jeśli taka transakcja była.
    try:
        today = datetime.now().date()
        from_time = datetime.combine(today, datetime.min.time())
        to_time = datetime.combine(today, datetime.max.time())
        deals = mt5.history_deals_get(from_time, to_time)
        if deals:
            for deal in deals:
                if deal.symbol == sym and deal.type == direction:
                    # Znaleziono zamkniętą transakcję dla symbolu i kierunku
                    logging.info(f"📦 Znaleziono zamkniętą transakcję {sym} typ={direction} w historii dzisiaj - nie otwieramy nowej.")
                    return False
    except Exception as e:
        logging.error(f"Błąd sprawdzania duplikatu transakcji: {e}")
        return False
    # Nie znaleziono takiej transakcji
    return True

def is_trade_symbol(sym):
    # Sprawdzenie otwartej pozycji dla symbolu
    positions = mt5.positions_get(symbol=sym)
    if not positions:
        return True # Brak otwartych pozycji, więc nie jest duplikatem
    else:
        return False # Istnieje otwarta pozycja, więc jest duplikatem

def is_trading_time():
    now = datetime.now(TIMEZONE)
    if now.weekday() == 0 and now.hour < 1:
        return False
    if now.weekday() == 4 and now.hour == 23:
        return False
    return now.weekday() < 5

def update_closed_positions_status(days_back=5, last_update=None):
    """Aktualizuje status transakcji w MS SQL na podstawie historii MT5."""
    now = datetime.now()

    updated = False

    # ================== 1. Zamknięte transakcje z historii ==================
    if last_update is None or last_update.hour < now.hour:
        time_from = datetime.now() - timedelta(days=days_back)
        time_to = datetime.now()
        deals = mt5.history_deals_get(time_from, time_to)

        if deals:
            for deal in deals:
                try:
                    # Tylko DEAL_ENTRY_OUT = zamknięcie pozycji
                    if deal.entry != mt5.DEAL_ENTRY_OUT:
                        continue
                    close_time = datetime.fromtimestamp(deal.time)
                    # Używamy deal.position_id (= ticket pozycji w DB),
                    # NIE deal.order (= numer zlecenia zamykającego)
                    mssql.update_trade_status(
                        order_id=deal.position_id,
                        done='Tak',
                        close_time=close_time,
                        profit=float(deal.profit),
                        result='Z' if deal.profit >= 0 else 'S'
                    )
                    # Zapisz wynik zamkniętej transakcji do trade_outcomes
                    try:
                        direction = "SELL" if deal.type == 0 else "BUY"
                        wisdom.record_trade_outcome(
                            trade_id=deal.position_id,
                            symbol=deal.symbol,
                            direction=direction,
                            profit_money=float(deal.profit),
                        )
                    except Exception as _toe:
                        logging.error(f"[trade_outcomes] Błąd zapisu: {_toe}")
                    updated = True
                except Exception:
                    pass

    # ================== 2. Otwarte pozycje ==================
    positions = mt5.positions_get()
    if positions:
        for pos in positions:
            try:
                open_time_ts = datetime.fromtimestamp(pos.time)
                duration_h = round((datetime.now() - open_time_ts).total_seconds() / 3600.0, 2)
                mssql.update_trade_status(
                    order_id=pos.ticket,
                    profit=float(pos.profit),
                    result='Z' if pos.profit >= 0 else 'S',
                    done='Nie',
                    sl=float(pos.sl),
                    tp=float(pos.tp),
                    current_price=float(pos.price_current),
                    swap=float(pos.swap),
                    duration_hours=duration_h
                )
                updated = True
            except Exception:
                pass

    if updated:
        logging.info("💾 Zaktualizowano status transakcji w MS SQL.")
    else:
        logging.info("ℹ️ Nie znaleziono żadnych transakcji do aktualizacji.")


# === GŁÓWNA PĘTLA ===
   
initialize_mt5()
logging.info(f"📈 Bot AI version: {VERSION} uruchomiony")
print(f"[START] Bot AI version: {VERSION} uruchomiony")

# === WISDOM AGGREGATOR (v1.4) + MS SQL ===
mssql = MSSQLWriter()
mssql.ensure_npm_table()          # NPM: utwórz tabelę jeśli nie istnieje
mssql.ensure_diagnostics_table()  # DiagLog: utwórz tabelę jeśli nie istnieje
mssql.purge_old_logs(days=14)     # Wyczyść logi starsze niż 2 tygodnie
set_mssql_writer(mssql)  # Połącz tran_logs z bazą MS SQL
# Przekieruj WARNING+ do tabeli bot_logs
_db_log_handler = DBLogHandler(mssql, min_level=logging.INFO)
logging.getLogger().addHandler(_db_log_handler)
wisdom = WisdomAggregator(db=mssql)
logging.info(f"🧠 Wisdom Aggregator aktywny (MS SQL). Obserwacje w bazie: {wisdom.count_observations()}")
print(f"[WISDOM] Wisdom Aggregator aktywny (MS SQL). Obserwacje w bazie: {wisdom.count_observations()}")

# === SYNCHRONIZACJA MT5 → DB przy starcie ===
try:
    _sync_positions = mt5.positions_get()
    _sync_count = mssql.sync_open_positions_from_mt5(_sync_positions)
    _sync_time_from = datetime.now() - timedelta(days=7)
    _sync_deals = mt5.history_deals_get(_sync_time_from, datetime.now())
    _sync_count += mssql.sync_deals_from_mt5(_sync_deals)
    if _sync_count > 0:
        logging.info(f"🔄 Synchronizacja MT5→DB: {_sync_count} rekordów uzupełnionych.")
        print(f"[SYNC] Synchronizacja MT5->DB: {_sync_count} rekordów uzupełnionych.")
    else:
        logging.info("🔄 Synchronizacja MT5→DB: baza aktualna.")
except Exception as _se:
    logging.error(f"❌ Błąd synchronizacji MT5→DB: {_se}")

_wisdom_last_outcome_update = datetime.now()
_wisdom_last_aggregation = datetime.now()
_bot_start_time = time.time()

# === INITIAL CONFIG LOAD FROM DATABASE ===
reload_cfg()  # Załaduj config z DB na samym starcie, aby uzyskać świeży blacklist

try:
    last_check = {sym: None for sym in SYMBOLS}
    tran_log_last_update = None

    while True:
        reload_cfg()  # Odswież konfigurację z DB na początku każdej iteracji
        check_and_rotate_logs()  # Sprawdź czy zmienił się dzień - jeśli tak, zarotuj log file
        
        # ⚠️ CLOSE BLACKLISTED POSITIONS: Check if any open positions are on blacklist
        if len(BLACKLIST_SYMBOLS) > 0:
            try:
                _open_pos = mt5.positions_get()
                if _open_pos:
                    for pos in _open_pos:
                        if pos.symbol in BLACKLIST_SYMBOLS:
                            logging.warning(f"🛑 Zamykam pozycję na blacklist'owanym symbolu: {pos.symbol} (ticket: {pos.ticket})")
                            _close_position(pos)
            except Exception as e:
                logging.error(f"Błąd przy zamykaniu pozycji blacklist'owanych: {e}")
        
        # 🔍 DEBUG: Log current SYMBOLS and BLACKLIST on every iteration
        if len(BLACKLIST_SYMBOLS) > 0:
            logging.info(f"🚫 BLACKLIST aktywny: {BLACKLIST_SYMBOLS}, SYMBOLS count after filter: {len(SYMBOLS)}")
        
        # 👉 Sprawdź czy jest 23:59:00 lub później
        now = datetime.now()
        if now.hour == 23 and now.minute == 59:
            logging.info("🕛 Jest 23:59:00 - kończę działanie bota.")
            sys.exit()

        # Aktualizacja statusów zamkniętych pozycji (MS SQL)
        update_closed_positions_status(days_back=7, last_update=tran_log_last_update)
        tran_log_last_update = datetime.now()

        # 🔄 Synchronizacja MT5 → DB (uzupełnij brakujące rekordy)
        try:
            _s_pos = mt5.positions_get()
            mssql.sync_open_positions_from_mt5(_s_pos)
            _s_from = datetime.now() - timedelta(days=3)
            _s_deals = mt5.history_deals_get(_s_from, datetime.now())
            mssql.sync_deals_from_mt5(_s_deals)
        except Exception as _sync_e:
            logging.error(f"❌ Sync MT5→DB error: {_sync_e}")

        # Poza godzinami handlu
        if not is_trading_time():
            logging.info("🌙 Poza godzinami handlu, czekam 5 minut...")
            print("🌙 Poza godzinami handlu — pauza 5 minut...")
            # Wymuszone retreny z flagi DB — dzialaj rowniez poza godzinami handlu
            try:
                _forced = mssql.pop_retrain_symbols()
                if _forced:
                    logging.info(f"⚡ Wymuszony retrain poza godzinami handlu: {_forced}")
                    retrain_models()
                    initialize_mt5()
            except Exception as _frt_e:
                logging.error(f"❌ Forced retrain (poza godzinami) error: {_frt_e}")
            # Heartbeat (MS SQL)
            try:
                account = mt5.account_info()
                positions = mt5.positions_get()
                mssql.write_heartbeat(
                    status="PAUSED", mode="OBSERVER", version=VERSION,
                    equity=account.equity if account else None,
                    balance=account.balance if account else None,
                    open_positions=len(positions) if positions else 0,
                    uptime_seconds=int(time.time() - _bot_start_time),
                    observations_count=wisdom.count_observations(),
                    message="Poza godzinami handlu"
                )
            except Exception as e:
                logging.error(f"❌ Heartbeat error (paused): {e}")
            time.sleep(300)
            continue
        # Uruchom ponowne trenowanie modeli
        retrain_models()
        # Reconnect MT5 (trening zamyka połączenie)
        initialize_mt5()

        # --- Variant C: Reset dzienny licznik strat ---
        today_str = datetime.now().strftime('%Y-%m-%d')
        if daily_loss_date != today_str:
            daily_loss_count = 0
            daily_loss_date = today_str

        # --- Variant C: Aktualizuj straty z historii MT5 (od początku dnia kalendarzowego) ---
        try:
            _midnight = datetime.combine(datetime.now().date(), datetime.min.time())
            _loss_deals = mt5.history_deals_get(_midnight, datetime.now())
            if _loss_deals:
                _today_losses = 0
                for _d in _loss_deals:
                    if _d.entry == 1 and _d.profit < 0:  # entry=1 → close, profit<0 → loss
                        _d_time = datetime.fromtimestamp(_d.time)
                        if _d_time >= _midnight:  # tylko od północy bieżącego dnia
                            _today_losses += 1
                            # Zaktualizuj cooldown symbolu
                            if _d.symbol not in symbol_last_loss or _d_time > symbol_last_loss[_d.symbol]:
                                symbol_last_loss[_d.symbol] = _d_time
                daily_loss_count = _today_losses
        except Exception as _loss_e:
            logging.error(f"❌ Loss tracker error: {_loss_e}")

        # --- Variant C: Blokada po przekroczeniu dziennego limitu strat ---
        if daily_loss_count >= MAX_DAILY_LOSSES:
            logging.warning(
                f"⛔ Dzienny limit strat osiągnięty ({daily_loss_count}/{MAX_DAILY_LOSSES}). "
                f"Stop handlu — czekam do następnej iteracji."
            )
            # Nadal wykonuj trailing SL + heartbeat, ale nie otwieraj nowych pozycji
            update_trailing_sl()
            time.sleep(TRAILING_UPDATE_SEC)
            continue

        # --- Variant C: Blokada w oknie niskiej płynności (00:00-04:00 UTC) ---
        _utc_hour = datetime.utcnow().hour
        if VOL_BLOCK_START <= _utc_hour < VOL_BLOCK_END:
            logging.info(
                f"⛔ Okno niskiej płynności ({VOL_BLOCK_START}:00-{VOL_BLOCK_END}:00 UTC). "
                f"Aktualnie {_utc_hour}:00 UTC — pomijam nowe zlecenia, trailing SL aktywny."
            )
            update_trailing_sl()
            time.sleep(TRAILING_UPDATE_SEC)
            continue

        for symbol in SYMBOLS:
            try:
                # 🚫 SAFETY CHECK: Double-verify blacklist
                if BLACKLIST_SYMBOLS and symbol in BLACKLIST_SYMBOLS:
                    logging.error(f"🚨 KRITICAL: {symbol} on BLACKLIST but in SYMBOLS loop! Skipping.")
                    continue
                
                LOG_FILE = get_global_cfg("log_file")  # Pobierz ścieżkę do pliku loga
                # print(f"\n⏰ [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] — {symbol} analiza...")
                
                is_trade = is_trade_symbol(symbol)
                if not is_trade:
                    logging.info(f"ℹ️ {symbol} — Istnieje otwarta pozycja, pomijam analizę.")
                    continue

                # --- Variant C: Cooldown symbolu po stracie ---
                if symbol in symbol_last_loss:
                    _hours_since_loss = (datetime.now() - symbol_last_loss[symbol]).total_seconds() / 3600
                    if _hours_since_loss < SYMBOL_COOLDOWN_H:
                        logging.info(
                            f"⛔ {symbol} — cooldown po stracie ({_hours_since_loss:.1f}h / {SYMBOL_COOLDOWN_H}h). Pomijam."
                        )
                        continue

                logging.info(f"⏰ [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] — {symbol} analiza...")
                # Załaduj model i skalery
                # print(f"🔍 Załadowano model dla {MODEL_PATH}/{symbol}_model.pkl")
                model = joblib.load(f"{MODEL_PATH}/{symbol}_model.pkl")

                # print(f"🔍 Załadowano scaler dla {symbol} {MODEL_PATH}/{symbol}_scaler.pkl")
                scaler = joblib.load(f"{MODEL_PATH}/{symbol}_scaler.pkl")

                # print(f"🔍 Załadowano model i skalery dla {symbol} {MODEL_PATH}/{symbol}_feature_columns.pkl")
                feature_columns = joblib.load(f"{MODEL_PATH}/{symbol}_feature_columns.pkl")
                # logging.info(f"🔍 Załadowano modele: {MODEL_PATH}/{symbol}_model.pkl, {MODEL_PATH}/{symbol}_scaler.pkl, {MODEL_PATH}/{symbol}_feature_columns.pkl")

                if model is None:
                    logging.warning(f"⚠️ Model not found for {symbol}")
                    continue
                
                df = get_data(symbol)
                if df is None:
                    logging.warning(f"⚠️ No data for {symbol}")
                    continue

                last_time = df['time'].iloc[-1]
                # if last_check[symbol] == last_time:
                #     logging.info(f"⚠️ Skipping {symbol}, no new data")
                #     continue

                last_check[symbol] = last_time
                atr = calculate_atr(df)
                decision, prob = should_trade(df, model, scaler, feature_columns)
                logging.info(f"🔍 {symbol} — ATR: {atr}, Decyzja: {decision}, Prawdopodobieństwo: {prob}")

                # 🧠 Wisdom: zapisz obserwację niezależnie od decyzji
                try:
                    action_str = "NONE"
                    if decision is not None and prob is not None and prob > PREDICT_PROBA_THRESHOLD:
                        action_str = "BUY" if decision == 0 else "SELL"
                    wisdom.record_observation(
                        symbol=symbol,
                        ml_prediction=decision,
                        ml_confidence=prob,
                        action_taken=action_str
                    )
                except Exception as we:
                    logging.error(f"❌ Wisdom observation error for {symbol}: {we}")

                # --- Filtr confidence z progami: MIN (0.60), NORMAL (0.75) ---
                # <0.60 → SKIP (zbyt słaby)
                # 0.60-0.75 → LOT_MIN (mały lot)
                # >=0.75 → LOT normalny (silny sygnał)
                _eff_threshold = CONF_THRESHOLD_SYMBOL.get(symbol, CONF_THRESHOLD_NORMAL)
                _use_min_lot = False
                
                if decision is not None and prob is not None:
                    if prob < CONF_THRESHOLD_MIN:
                        # ❌ SKIP - za słaby sygnał
                        logging.info(f"ℹ️ Confidence {prob:.2f} < MIN threshold {CONF_THRESHOLD_MIN} — SKIP")
                        try:
                            mssql.insert_diagnostic(
                                event_type="FILTER_CONFIDENCE",
                                symbol=symbol,
                                ml_decision=decision,
                                ml_confidence=prob,
                                filter_blocked=True,
                                filter_reason=f"conf={prob:.3f} < MIN={CONF_THRESHOLD_MIN:.3f}",
                                atr=atr,
                                action_taken="SKIP"
                            )
                        except Exception as e:
                            logging.warning(f"[diagnostic] Error writing FILTER_CONFIDENCE: {e}")
                    elif prob < _eff_threshold:
                        # 🟡 WEAK - użyj LOT_MIN (0.60-0.75)
                        logging.info(f"🟡 Weak confidence {prob:.2f} ({CONF_THRESHOLD_MIN}-{_eff_threshold}) → LOT_MIN")
                        _use_min_lot = True
                    else:
                        # ✅ STRONG - użyj normalny LOT (>=0.75)
                        logging.info(f"✅ Strong confidence {prob:.2f} >= {_eff_threshold} → normalny LOT")
                        _use_min_lot = False

                if atr is not None and decision is not None and prob is not None and prob >= CONF_THRESHOLD_MIN:
                    # 🧭 Filtr HTF W1→D1: zrelaksowany — blokuj tylko gdy W1 PRZECIWNY do ML.
                    # D1 neutralny (FLAT) jest dozwolony — blokada = D1 PRZECIWNY + W1 w tym samym kierunku.
                    htf = wisdom.get_higher_tf_trend(symbol)
                    ml_direction = "BUY" if decision == 0 else "SELL"

                    w1 = htf['w1_trend']  # UP | DOWN | FLAT
                    d1 = htf['d1_trend']  # UP | DOWN | FLAT
                    w1_dir = "BUY" if w1 == "UP" else ("SELL" if w1 == "DOWN" else None)
                    d1_dir = "BUY" if d1 == "UP" else ("SELL" if d1 == "DOWN" else None)

                    htf_blocked = False
                    htf_block_reason = None

                    if w1_dir is not None and w1_dir != ml_direction:
                        # W1 wyraźnie PRZECIWNY do ML → blokada
                        htf_blocked = True
                        htf_block_reason = f"W1={w1} sprzeczny z ML={ml_direction}"
                    elif w1_dir is None and d1_dir is not None and d1_dir != ml_direction:
                        # W1 FLAT, D1 PRZECIWNY → blokada
                        htf_blocked = True
                        htf_block_reason = f"W1=FLAT, D1={d1} sprzeczny z ML={ml_direction}"
                    elif w1_dir is None and d1_dir is None:
                        # Zarówno W1 jak i D1 FLAT — brak trendu nadrzędnego
                        htf_blocked = True
                        htf_block_reason = "W1=FLAT, D1=FLAT — brak trendu"

                    if htf_blocked:
                        logging.info(
                            f"⛔ {symbol} — HTF blokada: {htf_block_reason} "
                            f"(W1={w1}, D1={d1}). Pomijam."
                        )
                        try:
                            mssql.insert_diagnostic(
                                event_type="HTF_BLOCK",
                                symbol=symbol,
                                ml_decision=decision,
                                ml_confidence=prob,
                                filter_blocked=True,
                                filter_reason=htf_block_reason,
                                htf_w1=w1, htf_d1=d1, htf_aligned=False,
                                atr=atr, action_taken="SKIP"
                            )
                        except Exception as e:
                            logging.warning(f"[diagnostic] Error writing HTF_BLOCK: {e}")
                    else:
                        logging.info(
                            f"✅ {symbol} — ML={ml_direction} OK vs HTF "
                            f"(W1={w1}, D1={d1}). Wchodzę."
                        )
                        try:
                            mssql.insert_diagnostic(
                                event_type="HTF_PASS",
                                symbol=symbol,
                                ml_decision=decision,
                                ml_confidence=prob,
                                filter_blocked=False,
                                htf_w1=w1, htf_d1=d1, htf_aligned=True,
                                atr=atr, action_taken="ENTER"
                            )
                        except Exception:
                            pass
                        is_not_duplicate = is_not_duplicate_trade(symbol, decision)
                        if is_not_duplicate:
                            # --- Limit otwartych pozycji ---
                            _open_positions = mt5.positions_get()
                            _open_count = len(_open_positions) if _open_positions else 0
                            if _open_count >= MAX_OPEN_POSITIONS:
                                logging.info(
                                    f"⛔ {symbol} — limit pozycji osiągnięty "
                                    f"({_open_count}/{MAX_OPEN_POSITIONS}). Pomijam."
                                )
                            else:
                                place_order(symbol, decision, atr, prob, use_min_lot=_use_min_lot)
                else:
                    logging.info(f"ℹ️ Brak decyzji dla {symbol}, predykcja: {prob}")

            except Exception as e:
                logging.error(f"❌ Error on symbol {symbol}: {e}")
                reconnect_mt5()
        update_trailing_sl()

        # 💓 Heartbeat (MS SQL)
        try:
            account = mt5.account_info()
            positions = mt5.positions_get()
            mssql.write_heartbeat(
                status="RUNNING", mode="OBSERVER", version=VERSION,
                equity=account.equity if account else None,
                balance=account.balance if account else None,
                open_positions=len(positions) if positions else 0,
                uptime_seconds=int(time.time() - _bot_start_time),
                observations_count=wisdom.count_observations(),
                message="Aktywny cykl handlowy"
            )
        except Exception as he:
            logging.error(f"❌ Heartbeat error: {he}")

        # 🧠 Wisdom: uzupełnianie outcome co 15 min, agregacja formacji co 24h
        try:
            if (datetime.now() - _wisdom_last_outcome_update).total_seconds() >= 900:
                wisdom.update_outcomes()
                _wisdom_last_outcome_update = datetime.now()
            if (datetime.now() - _wisdom_last_aggregation).total_seconds() >= 86400:
                wisdom.aggregate_formation_effectiveness()
                _wisdom_last_aggregation = datetime.now()
                logging.info(f"🧠 Wisdom: obserwacji w bazie: {wisdom.count_observations()}")
        except Exception as we:
            logging.error(f"❌ Wisdom cycle error: {we}")

        logging.info(f"💤 Czekam {TRAILING_UPDATE_SEC} sekund przed kolejną iteracją...")
        # print(f"💤 Czekam {TRAILING_UPDATE_SEC} sekund przed kolejną iteracją...\n")
        time.sleep(TRAILING_UPDATE_SEC)
except KeyboardInterrupt:
    logging.info("🛑 Bot zatrzymany przez użytkownika.")
    print("🛑 Bot zatrzymany przez użytkownika.")
except Exception as e:
    logging.critical(f"❌ Fatal error: {e}", exc_info=True)
    print(f"[FATAL] Fatal error: {e}")
finally:
    shutdown_mt5()
