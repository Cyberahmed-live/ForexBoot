import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import pytz
from datetime import datetime, timedelta
import joblib
import time
import os
import logging
import talib
import csv

# === Parametry ===
MODEL_PATH = 'forex_model_xgb.pkl'
SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF"]
VOLUME = 1
INTERVAL_MINUTES = 30
TIMEFRAME_MAP = {
       1: mt5.TIMEFRAME_M1,
       5: mt5.TIMEFRAME_M5,
      15: mt5.TIMEFRAME_M15,
      30: mt5.TIMEFRAME_M30,
      60: mt5.TIMEFRAME_H1,
     240: mt5.TIMEFRAME_H4,
    1440: mt5.TIMEFRAME_D1
}
TIMEFRAME = TIMEFRAME_MAP.get(INTERVAL_MINUTES, mt5.TIMEFRAME_H1)
CANDLE_WINDOW = 60
ATR_PERIOD = 14
TP_MULTIPLIER = 2.0
SL_PIPS = 100
DECISION_THRESHOLD = 0.6
MAGIC = 123456
LOG_FILE = "trades_log.csv"
TRAILING_CHECK_INTERVAL = 60  # seconds
MINUTES_BETWEEN_TRADES_PER_SYMBOL = 60

# === Logging ===
logging.basicConfig(filename='trading_bot.log', level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(message)s')

# === Inicjalizacja MetaTrader5 ===
if not mt5.initialize():
    print("initialize() failed")
    mt5.shutdown()

# === Model ===
model = joblib.load(MODEL_PATH)
model_features = model.feature_names_in_.tolist()

# === Historia ostatnich transakcji per symbol ===
last_trade_time = {}

def get_data(symbol, n):
    utc_from = datetime.utcnow() - timedelta(minutes=n*30)
    rates = mt5.copy_rates_from(symbol, TIMEFRAME, utc_from, n)
    if rates is None:
        return None
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df

def calculate_indicators(df):
    df['ema_50'] = df['close'].ewm(span=50).mean()
    df['ema_200'] = df['close'].ewm(span=200).mean()
    df['rsi'] = talib.RSI(df['close'], timeperiod=14)
    df['atr'] = talib.ATR(df['high'], df['low'], df['close'], timeperiod=ATR_PERIOD)
    return df

def predict_price_direction(df):
    df = calculate_indicators(df)
    df = df.dropna()
    if df.empty:
        return -1, 0.0

    # Zachowanie kolumn zgodnych z modelem
    missing_cols = [c for c in model_features if c not in df.columns]
    for col in missing_cols:
        df[col] = 0.0
    X = df[model_features]

    proba = model.predict_proba([X.iloc[-1]])[0][1]
    direction = 1 if proba > 0.5 else 0

    # Filtrowanie EMA + RSI
    if direction == 1 and not (df['ema_50'].iloc[-1] > df['ema_200'].iloc[-1] and df['rsi'].iloc[-1] > 50):
        return -1, 0.0
    if direction == 0 and not (df['ema_50'].iloc[-1] < df['ema_200'].iloc[-1] and df['rsi'].iloc[-1] < 50):
        return -1, 0.0

    return direction, proba

def calculate_sl_tp(price, atr, direction):
    sl = price - SL_PIPS * 0.0001 if direction == 1 else price + SL_PIPS * 0.0001
    tp = price + TP_MULTIPLIER * atr if direction == 1 else price - TP_MULTIPLIER * atr
    return round(sl, 5), round(tp, 5)

def log_trade(symbol, direction, price, sl, tp, volume, prediction, result, confidence):
    file_exists = os.path.isfile(LOG_FILE)
    with open(LOG_FILE, mode="a", newline="") as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(["time", "symbol", "type", "price", "sl", "tp", "volume", "prediction", "status", "order_id", "confidence"])
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"), symbol,
            "BUY" if direction == 1 else "SELL", price, sl, tp, volume,
            prediction,
            "OK" if result.retcode == mt5.TRADE_RETCODE_DONE else f"ERR {result.retcode}",
            result.order if hasattr(result, "order") else "-",
            f"{confidence:.2f}"
        ])

def apply_trailing_stop(symbol):
    positions = mt5.positions_get(symbol=symbol)
    for pos in positions:
        if pos.profit <= 0 or pos.magic != MAGIC:
            continue
        atr = talib.ATR(np.array([pos.price_open]*ATR_PERIOD),
                        np.array([pos.price_open]*ATR_PERIOD),
                        np.array([pos.price_current]*ATR_PERIOD),
                        timeperiod=ATR_PERIOD)[-1]
        if pos.type == mt5.ORDER_TYPE_BUY:
            new_sl = pos.price_current - atr
            if new_sl > pos.sl:
                mt5.order_modify(pos.ticket, pos.price_open, round(new_sl, 5), pos.tp, 0, mt5.ORDER_TIME_GTC)
        else:
            new_sl = pos.price_current + atr
            if new_sl < pos.sl:
                mt5.order_modify(pos.ticket, pos.price_open, round(new_sl, 5), pos.tp, 0, mt5.ORDER_TIME_GTC)

# === Główna pętla ===
while True:
    now = datetime.utcnow()
    if now.weekday() >= 5 or not (1 <= now.hour < 23):
        time.sleep(60)
        continue

    for symbol in SYMBOLS:
        # Pomijaj jeśli ostatnia transakcja była < 60 min temu
        if symbol in last_trade_time and (now - last_trade_time[symbol]).total_seconds() < MINUTES_BETWEEN_TRADES_PER_SYMBOL * 60:
            continue

        df = get_data(symbol, CANDLE_WINDOW)
        if df is None or df.empty:
            continue
        direction, proba = predict_price_direction(df)
        if direction == -1 or proba < DECISION_THRESHOLD:
            continue

        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            continue
        price = tick.ask if direction == 1 else tick.bid
        atr = df['atr'].iloc[-1]
        sl, tp = calculate_sl_tp(price, atr, direction)

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": VOLUME,
            "type": mt5.ORDER_TYPE_BUY if direction == 1 else mt5.ORDER_TYPE_SELL,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 20,
            "magic": MAGIC,
            "comment": "AI Trade",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        log_trade(symbol, direction, price, sl, tp, VOLUME, direction, result, proba)
        last_trade_time[symbol] = now

    # Trailing SL co minutę
    for symbol in SYMBOLS:
        apply_trailing_stop(symbol)

    time.sleep(TRAILING_CHECK_INTERVAL)
