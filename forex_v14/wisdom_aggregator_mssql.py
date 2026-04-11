# forex_v14/wisdom_aggregator.py
"""
Wisdom Aggregator — moduł pasywnej obserwacji rynku 24/7.
Zbiera spostrzeżenia (observations) per symbol co cykl analizy,
uzupełnia outcome po 1h/4h/24h i agreguje skuteczność formacji.

Baza: MS SQL Server (ForexBotDB) via db_writer.MSSQLWriter.
"""

import logging
from datetime import datetime, timedelta

import MetaTrader5 as mt5
import numpy as np
import pandas as pd
import talib

from forex_base.globalcfg import get_global_cfg
from forex_v14.db_writer import MSSQLWriter

# ---------------------------------------------------------------------------
# Konfiguracja
# ---------------------------------------------------------------------------
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
# Klasa główna
# ---------------------------------------------------------------------------

class WisdomAggregator:
    """Zbiera obserwacje rynkowe i buduje bazę wiedzy per symbol."""

    def __init__(self, db=None):
        self._db = db or MSSQLWriter()
        logging.info(f"[WisdomAggregator] Połączony z MS SQL (ForexBotDB)")

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
                strength = min(abs(val) / 100.0, 1.0)
                detections[name] = strength

        if not detections:
            return "none", 0.0

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

        if ema20 > ema50:
            trend = "UP"
        elif ema20 < ema50:
            trend = "DOWN"
        else:
            trend = "FLAT"

        scores = []
        scores.append(min(adx_val / 50.0, 1.0))
        rsi_extremity = abs(rsi_val - 50.0) / 50.0
        scores.append(rsi_extremity)
        scores.append(0.8 if trend != "FLAT" else 0.2)

        macro = round(float(np.mean(scores)), 4)
        return macro, trend, round(float(rsi_val), 2), round(float(adx_val), 2)

    # ------------------------------------------------------------------
    # Zapis obserwacji
    # ------------------------------------------------------------------
    def record_observation(self, symbol, ml_prediction=None, ml_confidence=None,
                           action_taken="NONE"):
        """Główna metoda wywoływana co cykl analizy per symbol."""
        interval = get_global_cfg("interval_minutes") or 240
        df = self._get_rates(symbol, interval, 120)
        if df is None:
            return

        candle_sc = self._candle_score(df)
        formation_name, formation_sc = self._detect_formations(df)
        macro_sc, trend, rsi_val, adx_val = self._macro_score(df)

        atr_val = float(talib.ATR(df['high'], df['low'], df['close'], timeperiod=14).iloc[-1])

        tick = mt5.symbol_info_tick(symbol)
        spread = round(tick.ask - tick.bid, 6) if tick else 0.0
        price = float(df['close'].iloc[-1])

        vol_ratio = 1.0
        if 'tick_volume' in df.columns:
            avg_v = df['tick_volume'].rolling(20).mean().iloc[-1]
            cur_v = df['tick_volume'].iloc[-1]
            vol_ratio = round(cur_v / avg_v, 4) if avg_v > 0 else 1.0

        ml_conf = ml_confidence if ml_confidence is not None else 0.0
        ccs = round(0.20 * candle_sc + 0.25 * formation_sc + 0.25 * macro_sc + 0.30 * ml_conf, 4)

        self._db.insert_observation(
            symbol=symbol, timeframe=interval,
            candle_score=candle_sc, formation_type=formation_name,
            formation_score=formation_sc, macro_score=macro_sc,
            ml_prediction=ml_prediction, ml_confidence=ml_confidence, ccs=ccs,
            atr=round(atr_val, 6), spread=spread,
            ema_trend=trend, rsi=rsi_val, adx=adx_val, volume_ratio=vol_ratio,
            action_taken=action_taken, price_at_obs=price
        )

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

        total_updated = 0
        for col, cutoff in cutoffs.items():
            rows = self._db.get_pending_outcomes(col, cutoff)
            for obs_id, symbol, entry_price, obs_ts in rows:
                if entry_price is None or entry_price == 0:
                    continue
                tick = mt5.symbol_info_tick(symbol)
                if tick is None:
                    continue
                current_price = (tick.bid + tick.ask) / 2.0
                diff_pips = round((current_price - entry_price) * 10000, 2)
                self._db.update_outcome(obs_id, col, diff_pips)
                total_updated += 1

            if col == 'outcome_24h':
                rows24 = self._db.get_pending_max_favorable()
                for obs_id, symbol, entry_price in rows24:
                    if entry_price is None:
                        continue
                    df = self._get_rates(symbol, 15, 96)
                    if df is None:
                        continue
                    highs = df['high'].values
                    lows = df['low'].values
                    max_fav = round((max(highs) - entry_price) * 10000, 2)
                    max_adv = round((entry_price - min(lows)) * 10000, 2)
                    self._db.update_max_favorable_adverse(obs_id, max_fav, max_adv)
                    total_updated += 1

        if total_updated > 0:
            logging.info(f"[Wisdom] Uzupełniono {total_updated} outcome'ów.")

    # ------------------------------------------------------------------
    # Rejestracja wyniku transakcji
    # ------------------------------------------------------------------
    def record_trade_outcome(self, trade_id, symbol, direction, **kwargs):
        self._db.insert_trade_outcome(trade_id, symbol, direction, **kwargs)

    # ------------------------------------------------------------------
    # Agregacja skuteczności formacji (co 24h)
    # ------------------------------------------------------------------
    def aggregate_formation_effectiveness(self):
        self._db.aggregate_formation_effectiveness()

    # ------------------------------------------------------------------
    # Zapytania analityczne
    # ------------------------------------------------------------------
    def get_formation_winrate(self, symbol, formation_type):
        return self._db.get_formation_winrate(symbol, formation_type)

    def get_observation_stats(self, symbol, days=7):
        return self._db.get_observation_stats(symbol, days)

    def get_best_formations(self, symbol, min_occurrences=10, min_winrate=0.55):
        return self._db.get_best_formations(symbol, min_occurrences, min_winrate)

    def count_observations(self):
        return self._db.count_observations()
