# forex_base/globalcfg.py
import pytz
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime

# --- KONFIGURACJA ---
INTERVAL_MINUTES = 240  # Interwał w minutach, domyślnie 240 minut (4 godziny)

def get_timeframe(interval=30):
    # Inicjalizuje i zwraca połączenie z MetaTrader 5.
    if not mt5.initialize():
        raise RuntimeError(f"MetaTrader 5 initialization failed: {mt5.last_error()}")

    TIMEFRAME_MAP = {
        1: mt5.TIMEFRAME_M1,
        5: mt5.TIMEFRAME_M5,
        15: mt5.TIMEFRAME_M15,
        30: mt5.TIMEFRAME_M30,
        60: mt5.TIMEFRAME_H1,
        240: mt5.TIMEFRAME_H4,
        1440: mt5.TIMEFRAME_D1
    }
    timeframe = TIMEFRAME_MAP.get(interval, mt5.TIMEFRAME_H1)
    return timeframe

global_cfg = {
    # Poprzedni broker (.pro):
    # "symbols": ['AUDUSD.pro', 'AUDCAD.pro', ... 'GOLD.pro', 'SILVER.pro'],
    # Capital.com (bez sufiksu, zloto=XAUUSD, srebro=XAGUSD):
    "symbols": ['AUDUSD', 'AUDCAD', 'AUDCHF', 'AUDJPY', 'AUDNZD', 'EURUSD', 'EURCHF', 'EURJPY', 'EURPLN', 'EURCAD', 'EURNZD', 'EURAUD', 'GBPUSD', 'GBPJPY', 'GBPCAD', 'GBPCHF', 'GBPAUD', 'GBPNZD', 'CHFPLN', 'USDJPY', 'USDCHF', 'USDCAD', 'USDPLN', 'NZDUSD', 'NZDCAD', 'CADJPY', 'XAUUSD', 'XAGUSD'],  # Capital.com demo
    "interval_minutes": INTERVAL_MINUTES,           # Interwał w minutach
    "timeframe": get_timeframe(INTERVAL_MINUTES),   # Pobierz odpowiedni timeframe
    "tran_incubator_sec": (INTERVAL_MINUTES * 60) * 5, # Minimalny czas w sekundach trzymania pozycji (5 interwału)
    "candles": 60,                                  # Liczba świec do analizy  
    "candles_max": 120,                             # Liczba świec do analizy większe okno
    "bars": 100000,                                 # Liczba świec do pobrania
    "model_path": "forex_models",                   # Katalog do zapisywania modeli
    "output_dir": "forex_data",                     # Katalog do zapisywania danych
    "magic": 123456,                                # Magic number dla transakcji
    "lot": 1.0,                                     # Wielkość lota dla transakcji
    "min_lot": 0.33,                                # Minimalna wielkość lota dla transakcji
    "tp_atr_multiplier": 1.618,                     # Mnożnik Take Profit na podstawie ATR (fibo)
    "sl_atr_multiplier": 1.3,                       # Mnożnik Stop Loss na podstawie ATR
    "atr_min": 0.001,                               # Minimalny ATR do wejścia na rynek
    # --- 4-stopniowy trailing SL (R-multiple) ---
    "trail_breakeven_r": 0.7,                       # Stage 1: przesunięcie SL na break-even po osiągnięciu 0.7R
    "trail_lock_r": 1.5,                            # Stage 2: zamknij min. 0.5R zysku
    "trail_lock_fraction": 0.5,                     # Stage 2: jaka część R jest gwarantowana (0.5 = 0.5R)
    "trail_atr_r": 2.0,                             # Stage 3: trailing 1.0 ATR od maximum
    "trail_atr_factor": 1.0,                        # Stage 3: ile ATR od extremum ceny
    "trail_tight_r": 3.0,                           # Stage 4: ciasny trailing 0.5 ATR od maximum
    "trail_tight_factor": 0.5,                      # Stage 4: ile ATR od extremum ceny
    "trade_timeout": 300,                            # Limit czasu dla iteracji w sekundach (5 min)
    "predict_proba_threshold": 0.75,                # Próg prawdopodobieństwa do otwarcia transakcji (Variant C: 0.6→0.75)
    # --- Variant C: filtry wejścia ---
    "min_rr_ratio": 2.0,                            # Minimalny stosunek R:R (TP/SL) do otwarcia pozycji
    "spread_filter_pct": 0.20,                      # Spread > 20% dystansu SL → blokada
    "volatility_block_start": 0,                    # Blokada handlu od godziny UTC (00:00)
    "volatility_block_end": 4,                      # Blokada handlu do godziny UTC (04:00)
    "symbol_cooldown_hours": 24,                    # Cooldown na symbol po stracie (godziny)
    "max_daily_losses": 3,                          # Max strat dziennie → stop handlu na dzień
    "max_open_positions": 5,                        # Max jednoczesnych otwartych pozycji (limit marginu)
    # --- Variant C: ochrona pozycji ---
    "partial_close_r": 1.5,                         # Częściowe zamknięcie pozycji przy R>=1.5
    "partial_close_pct": 0.5,                       # Procent pozycji do zamknięcia (50%)
    "time_exit_hours": 16,                          # Zamknij pozycję ujemną po 16h (4 świece H4)
    # --- NPM: Negative Position Manager ---
    "npm_alert_r": -0.5,                            # Próg ALERT (R <= -0.5)
    "npm_critical_r": -1.0,                         # Próg CRITICAL (R <= -1.0)
    "npm_hard_cap_r": -2.5,                         # Hard cap: zamknij 100% niezależnie
    "npm_alert_npm_threshold": 50,                  # NPM score < 50 → ALERT
    "npm_critical_npm_threshold": 30,               # NPM score < 30 → CRITICAL
    "npm_scaled_exit_50_r": -1.0,                   # Zamknij 50% przy R <= -1.0 AND NPM < 30
    "npm_scaled_exit_100_r": -1.5,                  # Zamknij resztę przy R <= -1.5 AND NPM < 20
    "npm_tighten_sl_r_factor": 1.5,                 # ALERT: ściągnij SL do -1.5R od entry
    "npm_weekend_block_hour": 20,                   # Piątek po 20:00 UTC: nie zamykaj (weekend window)
    "npm_weekend_recovery": True,                   # Włącz weekend recovery window
    "timezone": pytz.timezone("Etc/UTC"),           # Strefa czasowa dla aplikacji
    "max_drawdown": 0.1,                            # Maksymalny dopuszczalny obsunięcie kapitału (jako ułamek kapitału)
    "risk_per_trade": 0.09,                         # Ryzyko na transakcję (jako ułamek kapitału)
    "log_level": "INFO",                            # Poziom logowania dla aplikacji
    "logs_dir": "forex_logs",                       # Katalog na pliki logów
    "log_file": f"forex_logs/forex_bot_{datetime.now().strftime('%Y-%m-%d')}.log",  # Ścieżka do pliku logów
    "version": "1.3.0",                             # Wersja AI Bota
}

def _load_cfg_from_db(defaults):
    """Laduje konfiguracje z tabeli bot_config w DB. Fallback do defaults."""
    try:
        from forex_v14.db_writer import MSSQLWriter
        w = MSSQLWriter()
        db_cfg = w.load_config_to_dict(defaults)
        # Odtwarz klucze Python-only (nie mozna ich przechowac jako string w DB)
        db_cfg["timezone"] = pytz.timezone("Etc/UTC")
        interval = int(db_cfg.get("interval_minutes", INTERVAL_MINUTES))
        db_cfg["timeframe"] = get_timeframe(interval)
        db_cfg["tran_incubator_sec"] = (interval * 60) * 5
        db_cfg["log_file"] = f"forex_logs/forex_bot_{datetime.now().strftime('%Y-%m-%d')}.log"
        # symbols z DB przechowywane jako CSV string -> przywroc liste
        symbols_raw = db_cfg.get("symbols", "")
        if isinstance(symbols_raw, str):
            db_cfg["symbols"] = [s.strip() for s in symbols_raw.split(",") if s.strip()]
        import logging
        logging.getLogger(__name__).info(
            f"[Config] Zaladowano {len(db_cfg)} kluczy z DB bot_config"
        )
        return db_cfg
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            f"[Config] Fallback na lokalny config (DB niedostepna): {e}"
        )
        return defaults


global_cfg = _load_cfg_from_db(global_cfg)


def get_global_cfg(name):
    # Funkcja zwraca wartość z konfiguracji globalnej o podanej nazwie.
    return global_cfg.get(name, None)

def get_global_cfg_as_dict():
    # Funkcja zwraca całą konfigurację jako tekstowy słownik.
    cfg_result = ""
    for key, value in global_cfg.items():
        cfg_result+=f"{key}: {str(value)}"+"\n"
    return cfg_result

# print(get_global_cfg_as_dict())  # Wyjście do debugowania konfiguracji