import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import talib
import datetime
import os

# Ustawienia użytkownika
SYMBOLS = ["EURUSD", "USDJPY", "GBPUSD"]
N_CANDLES = 1000
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

# Inicjalizacja MT5
if not mt5.initialize():
    print("MT5 initialization failed")
    quit()

# Formacje świecowe
CANDLE_PATTERNS = {
    'hammer': talib.CDLHAMMER,
    'shooting_star': talib.CDLSHOOTINGSTAR
}

# Funkcje wykrywania formacji

def detect_double_top(df):
    if len(df) < 10:
        return 0
    recent = df[-10:]
    high1 = recent['high'].iloc[2]
    high2 = recent['high'].iloc[6]
    if abs(high1 - high2) / high1 < 0.005:
        return 1
    return 0

def detect_double_bottom(df):
    if len(df) < 10:
        return 0
    recent = df[-10:]
    low1 = recent['low'].iloc[2]
    low2 = recent['low'].iloc[6]
    if abs(low1 - low2) / low1 < 0.005:
        return 1
    return 0

def detect_head_and_shoulders(df):
    if len(df) < 10:
        return 0
    hs = df[-10:]
    return int(hs['high'].iloc[1] < hs['high'].iloc[3] > hs['high'].iloc[5] and
               hs['high'].iloc[2] < hs['high'].iloc[3] and
               hs['high'].iloc[4] < hs['high'].iloc[3])

def detect_inverse_head_and_shoulders(df):
    if len(df) < 10:
        return 0
    hs = df[-10:]
    return int(hs['low'].iloc[1] > hs['low'].iloc[3] < hs['low'].iloc[5] and
               hs['low'].iloc[2] > hs['low'].iloc[3] and
               hs['low'].iloc[4] > hs['low'].iloc[3])

# Funkcja generująca cechy techniczne
def generate_features(df):
    df['rsi'] = talib.RSI(df['close'], timeperiod=14)
    df['ema_50'] = talib.EMA(df['close'], timeperiod=50)
    df['ema_200'] = talib.EMA(df['close'], timeperiod=200)
    df['atr'] = talib.ATR(df['high'], df['low'], df['close'], timeperiod=14)
    df['adx'] = talib.ADX(df['high'], df['low'], df['close'], timeperiod=14)
    df['macd'], _, _ = talib.MACD(df['close'], fastperiod=12, slowperiod=26, signalperiod=9)
    df['willr'] = talib.WILLR(df['high'], df['low'], df['close'], timeperiod=14)
    df['roc'] = talib.ROC(df['close'], timeperiod=10)
    df['cci'] = talib.CCI(df['high'], df['low'], df['close'], timeperiod=14)

    for name, func in CANDLE_PATTERNS.items():
        df[name] = func(df['open'], df['high'], df['low'], df['close'])

    df['double_top'] = df.apply(lambda x: detect_double_top(df), axis=1)
    df['double_bottom'] = df.apply(lambda x: detect_double_bottom(df), axis=1)
    df['head_and_shoulders'] = df.apply(lambda x: detect_head_and_shoulders(df), axis=1)
    df['inverse_hs'] = df.apply(lambda x: detect_inverse_head_and_shoulders(df), axis=1)

    return df

# Główna pętla
all_data = []
for symbol in SYMBOLS:
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, N_CANDLES)
    if rates is None or len(rates) == 0:
        print(f"Brak danych dla {symbol}")
        continue

    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    df = generate_features(df)
    df['symbol'] = symbol
    all_data.append(df)

# Zapis do CSV
if all_data:
    final_df = pd.concat(all_data)
    filename = f"features_{INTERVAL_MINUTES}min_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    final_df.to_csv(filename, index=True)
    print(f"Zapisano dane do pliku {filename}")
else:
    print("Brak danych do zapisania.")

mt5.shutdown()
