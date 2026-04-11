# forex_v14/wisdom_aggregator.py
"""
Wisdom Aggregator — moduł pasywnej obserwacji rynku 24/7.
Zbiera spostrzeżenia (observations) per symbol co cykl analizy,
uzupełnia outcome po 1h/4h/24h i agreguje skuteczność formacji.

Działa obok istniejącego bota v1.3 bez zmiany logiki handlowej.
Baza: SQLite (jeden plik .db).
"""

import os
import sqlite3
import logging
import time
import threading
from datetime import datetime, timedelta

import MetaTrader5 as mt5
import numpy as np
import pandas as pd
import talib

from forex_base.globalcfg import get_global_cfg

# ---------------------------------------------------------------------------
# Konfiguracja
# ---------------------------------------------------------------------------
_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "forex_data")
DB_PATH = os.path.join(_DB_DIR, "observations.db")

_TIMEFRAME_MAP = {
    1: mt5.TIMEFRAME_M1,
    5: mt5.TIMEFRAME_M5,
    15: mt5.TIMEFRAME_M15,
    30: mt5.TIMEFRAME_M30,
    60: mt5.TIMEFRAME_H1,
    240: mt5.TIMEFRAME_H4,
    1440: mt5.TIMEFRAME_D1,
}

# Timeframe'y używane w analizie multi-TF (minuty)
ANALYSIS_TFS = [15, 60, 240, 1440]

# ---------------------------------------------------------------------------
# Schema bazy
# ---------------------------------------------------------------------------
_SCHEMA_OBSERVATIONS = """
CREATE TABLE IF NOT EXISTS observations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT    NOT NULL,
    symbol          TEXT    NOT NULL,
    timeframe       TEXT    NOT NULL,
    candle_score    REAL,
    formation_type  TEXT    DEFAULT 'none',
    formation_score REAL    DEFAULT 0.0,
    macro_score     REAL    DEFAULT 0.0,
    ml_prediction   INTEGER,
    ml_confidence   REAL,
    ccs             REAL    DEFAULT 0.0,
    atr             REAL,
    spread          REAL,
    ema_trend       TEXT,
    rsi             REAL,
    adx             REAL,
    volume_ratio    REAL,
    action_taken    TEXT    DEFAULT 'NONE',
    price_at_obs    REAL,
    outcome_1h      REAL,
    outcome_4h      REAL,
    outcome_24h     REAL,
    outcome_max_favorable  REAL,
    outcome_max_adverse    REAL
);
"""

_SCHEMA_TRADE_OUTCOMES = """
CREATE TABLE IF NOT EXISTS trade_outcomes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id            INTEGER,
    symbol              TEXT    NOT NULL,
    direction           TEXT,
    entry_ccs           REAL,
    entry_candle_score  REAL,
    entry_formation     TEXT,
    entry_macro_score   REAL,
    profit_pips         REAL,
    profit_money        REAL,
    duration_hours      REAL,
    max_drawdown        REAL,
    sl_hit              INTEGER DEFAULT 0,
    tp_hit              INTEGER DEFAULT 0,
    timestamp           TEXT
);
"""

_SCHEMA_FORMATION_EFF = """
CREATE TABLE IF NOT EXISTS formation_effectiveness (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT    NOT NULL,
    formation_type  TEXT    NOT NULL,
    occurrences     INTEGER DEFAULT 0,
    win_rate        REAL    DEFAULT 0.0,
    avg_move_pips   REAL    DEFAULT 0.0,
    best_timeframe  TEXT,
    last_updated    TEXT,
    UNIQUE(symbol, formation_type)
);
"""

_INDEX_STMTS = [
    "CREATE INDEX IF NOT EXISTS idx_obs_ts      ON observations(timestamp);",
    "CREATE INDEX IF NOT EXISTS idx_obs_sym     ON observations(symbol);",
    "CREATE INDEX IF NOT EXISTS idx_obs_sym_ts  ON observations(symbol, timestamp);",
    "CREATE INDEX IF NOT EXISTS idx_fe_sym      ON formation_effectiveness(symbol);",
]

# ---------------------------------------------------------------------------
# Klasa główna
# ---------------------------------------------------------------------------

class WisdomAggregator:
    """Zbiera obserwacje rynkowe i buduje bazę wiedzy per symbol."""

    def __init__(self, db_path=None):
        self.db_path = db_path or DB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()
        self._lock = threading.Lock()
        logging.info(f"[WisdomAggregator] Baza: {self.db_path}")

    # ------------------------------------------------------------------
    # Inicjalizacja bazy
    # ------------------------------------------------------------------
    def _init_db(self):
        con = sqlite3.connect(self.db_path)
        cur = con.cursor()
        cur.execute(_SCHEMA_OBSERVATIONS)
        cur.execute(_SCHEMA_TRADE_OUTCOMES)
        cur.execute(_SCHEMA_FORMATION_EFF)
        for idx in _INDEX_STMTS:
            cur.execute(idx)
        con.commit()
        con.close()

    def _conn(self):
        return sqlite3.connect(self.db_path, timeout=10)

    # ------------------------------------------------------------------
    # Pobranie danych z MT5 dla dowolnego TF
    # ------------------------------------------------------------------
    @staticmethod
    def _get_rates(symbol, tf_minutes, count=120):
        tf = _TIMEFRAME_MAP.get(tf_minutes)
        if tf is None:
            return None
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
        if rates is None or len(rates) < 20:
            return None
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        return df

    # ------------------------------------------------------------------
    # Scoring świec (candle_score 0.0 – 1.0)
    # ------------------------------------------------------------------
    @staticmethod
    def _candle_score(df):
        """Ocenia siłę ostatnich świec: body/shadow ratio, konsekutywność, momentum."""
        if df is None or len(df) < 10:
            return 0.0

        scores = []

        # 1. Body vs shadow ratio ostatniej świecy
        last = df.iloc[-1]
        body = abs(last['close'] - last['open'])
        full_range = last['high'] - last['low']
        body_ratio = body / full_range if full_range > 0 else 0.0
        scores.append(min(body_ratio * 1.2, 1.0))

        # 2. Konsekutywne świece kierunkowe (max 5)
        directions = np.sign(df['close'].iloc[-5:].values - df['open'].iloc[-5:].values)
        consec = 0
        last_dir = directions[-1]
        for d in reversed(directions):
            if d == last_dir and d != 0:
                consec += 1
            else:
                break
        scores.append(min(consec / 5.0, 1.0))

        # 3. Body momentum: rosnące ciała ostatnich 3 świec
        bodies = [abs(df.iloc[i]['close'] - df.iloc[i]['open']) for i in range(-3, 0)]
        if len(bodies) == 3 and bodies[0] > 0:
            momentum = bodies[-1] / bodies[0]
            scores.append(min(momentum / 3.0, 1.0))
        else:
            scores.append(0.0)

        # 4. Volume ratio (tick_volume vs średnia 20)
        if 'tick_volume' in df.columns:
            avg_vol = df['tick_volume'].rolling(20).mean().iloc[-1]
            cur_vol = df['tick_volume'].iloc[-1]
            vol_ratio = cur_vol / avg_vol if avg_vol > 0 else 1.0
            scores.append(min(vol_ratio / 2.0, 1.0))
        else:
            scores.append(0.5)

        return round(float(np.mean(scores)), 4)

    # ------------------------------------------------------------------
    # Detekcja formacji + scoring
    # ------------------------------------------------------------------
    @staticmethod
    def _detect_formations(df):
        """Wykrywa formacje i zwraca (nazwa, score)."""
        if df is None or len(df) < 10:
            return "none", 0.0

        o, h, l, c = df['open'], df['high'], df['low'], df['close']
        detections = {}

        patterns = {
            'ENGULFING':    talib.CDLENGULFING(o, h, l, c),
            'MORNING_STAR': talib.CDLMORNINGSTAR(o, h, l, c),
            'EVENING_STAR': talib.CDLEVENINGSTAR(o, h, l, c),
            'HAMMER':       talib.CDLHAMMER(o, h, l, c),
            'SHOOTING_STAR': talib.CDLSHOOTINGSTAR(o, h, l, c),
            'DOJI':         talib.CDLDOJI(o, h, l, c),
            'HARAMI':       talib.CDLHARAMI(o, h, l, c),
            'PIERCING':     talib.CDLPIERCING(o, h, l, c),
            'DARK_CLOUD':   talib.CDLDARKCLOUDCOVER(o, h, l, c),
            'THREE_WHITE':  talib.CDL3WHITESOLDIERS(o, h, l, c),
            'THREE_BLACK':  talib.CDL3BLACKCROWS(o, h, l, c),
        }

        for name, series in patterns.items():
            val = int(series.iloc[-1])
            if val != 0:
                # Podstawowy score zależny od "siły" sygnału TA-Lib (100/-100 = silny)
                strength = min(abs(val) / 100.0, 1.0)
                detections[name] = strength

        if not detections:
            return "none", 0.0

        # Zwróć najsilniejszą formację
        best = max(detections, key=detections.get)
        return best, round(detections[best], 4)

    # ------------------------------------------------------------------
    # Kontekst makro-techniczny (macro_score 0.0 – 1.0)
    # ------------------------------------------------------------------
    @staticmethod
    def _macro_score(df):
        """EMA trend, ADX, RSI — zbiorczy wynik kontekstu."""
        if df is None or len(df) < 50:
            return 0.0, "FLAT", 50.0, 0.0

        close = df['close']
        high = df['high']
        low = df['low']

        ema20 = talib.EMA(close, timeperiod=20).iloc[-1]
        ema50 = talib.EMA(close, timeperiod=50).iloc[-1]
        adx_val = talib.ADX(high, low, close, timeperiod=14).iloc[-1]
        rsi_val = talib.RSI(close, timeperiod=14).iloc[-1]

        # Trend
        if ema20 > ema50:
            trend = "UP"
        elif ema20 < ema50:
            trend = "DOWN"
        else:
            trend = "FLAT"

        scores = []

        # ADX > 25 → silny trend → wyższy score
        scores.append(min(adx_val / 50.0, 1.0))

        # RSI w strefie 40–60 = neutralny; skrajności = silniejszy sygnał
        rsi_extremity = abs(rsi_val - 50.0) / 50.0
        scores.append(rsi_extremity)

        # Trend alignment: trend != FLAT → bonus
        scores.append(0.8 if trend != "FLAT" else 0.2)

        macro = round(float(np.mean(scores)), 4)
        return macro, trend, round(float(rsi_val), 2), round(float(adx_val), 2)

    # ------------------------------------------------------------------
    # Zapis obserwacji
    # ------------------------------------------------------------------
    def record_observation(self, symbol, ml_prediction=None, ml_confidence=None,
                           action_taken="NONE"):
        """Główna metoda wywoływana co cykl analizy per symbol."""
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        # Pobierz dane dla głównego TF (H4 — jak w v1.3)
        interval = get_global_cfg("interval_minutes") or 240
        df = self._get_rates(symbol, interval, 120)
        if df is None:
            return

        # Candle score
        candle_sc = self._candle_score(df)

        # Formacje
        formation_name, formation_sc = self._detect_formations(df)

        # Makro
        macro_sc, trend, rsi_val, adx_val = self._macro_score(df)

        # ATR
        atr_val = float(talib.ATR(df['high'], df['low'], df['close'], timeperiod=14).iloc[-1])

        # Spread
        tick = mt5.symbol_info_tick(symbol)
        spread = round(tick.ask - tick.bid, 6) if tick else 0.0
        price = float(df['close'].iloc[-1])

        # Volume ratio
        vol_ratio = 1.0
        if 'tick_volume' in df.columns:
            avg_v = df['tick_volume'].rolling(20).mean().iloc[-1]
            cur_v = df['tick_volume'].iloc[-1]
            vol_ratio = round(cur_v / avg_v, 4) if avg_v > 0 else 1.0

        # CCS tymczasowy (w v1.4 będzie pełny; tu prosta wersja)
        ml_conf = ml_confidence if ml_confidence is not None else 0.0
        ccs = round(0.20 * candle_sc + 0.25 * formation_sc + 0.25 * macro_sc + 0.30 * ml_conf, 4)

        row = (
            now_str, symbol, str(interval),
            candle_sc, formation_name, formation_sc, macro_sc,
            ml_prediction, ml_confidence, ccs,
            round(atr_val, 6), spread, trend, rsi_val, adx_val, vol_ratio,
            action_taken, price,
            None, None, None, None, None  # outcome_* — uzupełniane później
        )

        with self._lock:
            con = self._conn()
            try:
                con.execute("""
                    INSERT INTO observations
                        (timestamp, symbol, timeframe,
                         candle_score, formation_type, formation_score, macro_score,
                         ml_prediction, ml_confidence, ccs,
                         atr, spread, ema_trend, rsi, adx, volume_ratio,
                         action_taken, price_at_obs,
                         outcome_1h, outcome_4h, outcome_24h,
                         outcome_max_favorable, outcome_max_adverse)
                    VALUES (?,?,?, ?,?,?,?, ?,?,?, ?,?,?,?,?,?, ?,?, ?,?,?,?,?)
                """, row)
                con.commit()
            finally:
                con.close()

        logging.info(
            f"[Wisdom] {symbol} | candle={candle_sc:.2f} form={formation_name}({formation_sc:.2f}) "
            f"macro={macro_sc:.2f} ml={ml_confidence} ccs={ccs:.3f} trend={trend} "
            f"rsi={rsi_val} adx={adx_val} atr={atr_val:.5f}"
        )

    # ------------------------------------------------------------------
    # Uzupełnianie outcome (wywoływane okresowo)
    # ------------------------------------------------------------------
    def update_outcomes(self):
        """Uzupełnia outcome_1h/4h/24h dla obserwacji, które tego wymagają."""
        now = datetime.utcnow()
        cutoffs = {
            'outcome_1h':  now - timedelta(hours=1, minutes=5),
            'outcome_4h':  now - timedelta(hours=4, minutes=5),
            'outcome_24h': now - timedelta(hours=24, minutes=5),
        }

        con = self._conn()
        try:
            for col, cutoff in cutoffs.items():
                cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")
                rows = con.execute(f"""
                    SELECT id, symbol, price_at_obs, timestamp
                    FROM observations
                    WHERE {col} IS NULL AND timestamp <= ?
                    LIMIT 200
                """, (cutoff_str,)).fetchall()

                for obs_id, symbol, entry_price, obs_ts in rows:
                    if entry_price is None or entry_price == 0:
                        continue

                    tick = mt5.symbol_info_tick(symbol)
                    if tick is None:
                        continue

                    current_price = (tick.bid + tick.ask) / 2.0
                    diff_pips = round((current_price - entry_price) * 10000, 2)

                    con.execute(f"UPDATE observations SET {col} = ? WHERE id = ?",
                                (diff_pips, obs_id))

                # Dla outcome_24h — uzupełnij też max_favorable / max_adverse (przybliżone)
                if col == 'outcome_24h':
                    rows24 = con.execute("""
                        SELECT id, symbol, price_at_obs
                        FROM observations
                        WHERE outcome_24h IS NOT NULL
                          AND outcome_max_favorable IS NULL
                        LIMIT 200
                    """).fetchall()

                    for obs_id, symbol, entry_price in rows24:
                        if entry_price is None:
                            continue
                        # Pobierz świece M15 z ostatnich 24h (96 świec)
                        df = self._get_rates(symbol, 15, 96)
                        if df is None:
                            continue
                        highs = df['high'].values
                        lows = df['low'].values
                        max_fav = round((max(highs) - entry_price) * 10000, 2)
                        max_adv = round((entry_price - min(lows)) * 10000, 2)
                        con.execute("""
                            UPDATE observations
                            SET outcome_max_favorable = ?, outcome_max_adverse = ?
                            WHERE id = ?
                        """, (max_fav, max_adv, obs_id))

            con.commit()
            updated = con.total_changes
            if updated > 0:
                logging.info(f"[Wisdom] Uzupełniono {updated} outcome'ów.")
        finally:
            con.close()

    # ------------------------------------------------------------------
    # Rejestracja wyniku transakcji
    # ------------------------------------------------------------------
    def record_trade_outcome(self, trade_id, symbol, direction,
                             entry_ccs=0.0, entry_candle_score=0.0,
                             entry_formation="none", entry_macro_score=0.0,
                             profit_pips=0.0, profit_money=0.0,
                             duration_hours=0.0, max_drawdown=0.0,
                             sl_hit=False, tp_hit=False):
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            con = self._conn()
            try:
                con.execute("""
                    INSERT INTO trade_outcomes
                        (trade_id, symbol, direction,
                         entry_ccs, entry_candle_score, entry_formation, entry_macro_score,
                         profit_pips, profit_money, duration_hours, max_drawdown,
                         sl_hit, tp_hit, timestamp)
                    VALUES (?,?,?, ?,?,?,?, ?,?,?,?, ?,?,?)
                """, (trade_id, symbol, direction,
                      entry_ccs, entry_candle_score, entry_formation, entry_macro_score,
                      profit_pips, profit_money, duration_hours, max_drawdown,
                      int(sl_hit), int(tp_hit), now_str))
                con.commit()
            finally:
                con.close()
        logging.info(f"[Wisdom] Trade outcome: {symbol} {direction} profit={profit_pips:.1f} pips")

    # ------------------------------------------------------------------
    # Agregacja skuteczności formacji (co 24h)
    # ------------------------------------------------------------------
    def aggregate_formation_effectiveness(self):
        """Przelicza win_rate i avg_move per symbol+formation z outcome_24h."""
        con = self._conn()
        try:
            rows = con.execute("""
                SELECT symbol, formation_type, timeframe,
                       COUNT(*) as cnt,
                       AVG(CASE WHEN outcome_24h > 0 THEN 1.0 ELSE 0.0 END) as wr,
                       AVG(outcome_24h) as avg_mv
                FROM observations
                WHERE formation_type != 'none'
                  AND outcome_24h IS NOT NULL
                GROUP BY symbol, formation_type, timeframe
                HAVING cnt >= 5
            """).fetchall()

            now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            for symbol, form, tf, cnt, wr, avg_mv in rows:
                con.execute("""
                    INSERT INTO formation_effectiveness
                        (symbol, formation_type, occurrences, win_rate, avg_move_pips,
                         best_timeframe, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(symbol, formation_type) DO UPDATE SET
                        occurrences = excluded.occurrences,
                        win_rate = excluded.win_rate,
                        avg_move_pips = excluded.avg_move_pips,
                        best_timeframe = excluded.best_timeframe,
                        last_updated = excluded.last_updated
                """, (symbol, form, cnt, round(wr, 4), round(avg_mv, 2), tf, now_str))

            con.commit()
            logging.info(f"[Wisdom] Agregacja formacji: {len(rows)} rekordów zaktualizowanych.")
        finally:
            con.close()

    # ------------------------------------------------------------------
    # Zapytania analityczne
    # ------------------------------------------------------------------
    def get_formation_winrate(self, symbol, formation_type):
        """Zwraca win_rate danej formacji na danym symbolu (lub None)."""
        con = self._conn()
        try:
            row = con.execute("""
                SELECT win_rate, occurrences FROM formation_effectiveness
                WHERE symbol = ? AND formation_type = ?
            """, (symbol, formation_type)).fetchone()
            if row:
                return {"win_rate": row[0], "occurrences": row[1]}
            return None
        finally:
            con.close()

    def get_observation_stats(self, symbol, days=7):
        """Statystyki obserwacji z ostatnich N dni."""
        cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        con = self._conn()
        try:
            row = con.execute("""
                SELECT COUNT(*) as cnt,
                       AVG(candle_score) as avg_candle,
                       AVG(formation_score) as avg_form,
                       AVG(macro_score) as avg_macro,
                       AVG(ccs) as avg_ccs,
                       MAX(ccs) as max_ccs
                FROM observations
                WHERE symbol = ? AND timestamp >= ?
            """, (symbol, cutoff)).fetchone()
            if row:
                return {
                    "count": row[0], "avg_candle": row[1], "avg_formation": row[2],
                    "avg_macro": row[3], "avg_ccs": row[4], "max_ccs": row[5]
                }
            return None
        finally:
            con.close()

    def get_best_formations(self, symbol, min_occurrences=10, min_winrate=0.55):
        """Zwraca formacje o najwyższej skuteczności dla symbolu."""
        con = self._conn()
        try:
            rows = con.execute("""
                SELECT formation_type, win_rate, avg_move_pips, occurrences
                FROM formation_effectiveness
                WHERE symbol = ? AND occurrences >= ? AND win_rate >= ?
                ORDER BY win_rate DESC
            """, (symbol, min_occurrences, min_winrate)).fetchall()
            return [{"formation": r[0], "win_rate": r[1], "avg_move": r[2], "count": r[3]}
                    for r in rows]
        finally:
            con.close()

    def count_observations(self):
        """Łączna liczba obserwacji w bazie."""
        con = self._conn()
        try:
            return con.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        finally:
            con.close()
