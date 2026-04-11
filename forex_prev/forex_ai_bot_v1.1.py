import csv
import MetaTrader5 as mt5  # type: ignore
import pandas as pd
from ta import add_all_ta_features
import time
import joblib
from datetime import datetime
import pytz
import os
import warnings
import numpy as np
from ta.volatility import AverageTrueRange
from ta.momentum import RSIIndicator
import matplotlib.pyplot as plt # type: ignore
import json

warnings.filterwarnings("ignore", category=FutureWarning)

# ======== PARAMETRY ========
# SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF"]
SYMBOLS = ["EURDKK", "EURHKD", "EURHUF", "EURNOK", "EURUSD", "EURPLN", "EURSEK", "EURTRY", "EURZAR", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "NZDUSD", "USDCAD", "EURGBP", "EURJPY", "EURCHF", "GBPCHF", "AUDJPY", "AUDCHF", "NZDJPY", "NZDCHF", "CADJPY", "CADCHF", "AUDCAD", "AUDNZD", "EURCAD", "GBPNZD", "USDSEK", "USDNOK", "USDPLN", "USDZAR", "USDHKD", "USDTRY", "USDMXN", "USDCNH", "USDPLN", "USDNOK", "USDTRY", "USDZAR", "GOLD", "SILVER"]
VOLUME = 1
MODEL_PATH = "forex_model_xgb.pkl"
LOG_FILE = "trades_log.csv"
EXPECTED_FEATURES = ['open', 'high', 'low', 'close', 'tick_volume', 'spread']
TIMEZONE = pytz.timezone("Etc/UTC")
INTERVAL_MINUTES = 60
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
MAGIC = 123456
DEFAULT_MIN_STOP_LEVEL = 90
ATR_PERIOD = 14
ATR_MULTIPLIER_SL = 1.5
ATR_MULTIPLIER_TP = 3.0
DECISION_THRESHOLD = 0.85
TRAILING_STOP_POINTS = 400
LAST_BARS_FILE = "last_bars.json"

model = joblib.load(MODEL_PATH)

def get_atr_value(symbol):
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, 100)
    if rates is None or len(rates) < ATR_PERIOD:
        raise ValueError(f"Nie udało się pobrać danych dla ATR dla {symbol}")
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    atr = AverageTrueRange(
        high=df["high"], low=df["low"], close=df["close"],
        window=ATR_PERIOD, fillna=True
    )
    return atr.average_true_range().iloc[-1]

def get_dynamic_sl_tp(symbol):
    info = mt5.symbol_info(symbol)
    if not info:
        print(f"⚠️ Brak informacji o symbolu {symbol}, używam wartości domyślnych.")
        return DEFAULT_MIN_STOP_LEVEL, TRAILING_STOP_POINTS

    point = info.point
    min_points = info.trade_stops_level
    if min_points <= 0:
        print(f"⚠️ trade_stops_level dla {symbol} to 0 lub brak, ustawiam wartości domyślne.")
        return DEFAULT_MIN_STOP_LEVEL, TRAILING_STOP_POINTS

    try:
        atr = get_atr_value(symbol)
        if atr is None or atr <= 0:
            raise ValueError("ATR jest nieprawidłowy")
        sl_points = max(int((atr * ATR_MULTIPLIER_SL) / point), int(min_points * 1.5))
        tp_points = max(int((atr * ATR_MULTIPLIER_TP) / point), int(min_points * 4.5))
        return sl_points, tp_points
    except Exception as e:
        print(f"⚠️ Błąd ATR dla {symbol}: {e} — używam wartości awaryjnych")
        return int(min_points * 1.5), int(min_points * 4.5)

def calculate_sl_tp(price, direction, stop_loss_pips, take_profit_pips, symbol):
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        raise ValueError(f"Nie można pobrać informacji o symbolu {symbol}")

    point = symbol_info.point
    min_stop_level = symbol_info.trade_stops_level
    effective_stop_level = min_stop_level if min_stop_level > 0 else DEFAULT_MIN_STOP_LEVEL
    min_stop_distance = effective_stop_level * point
    required_sl_distance = max(stop_loss_pips * point, min_stop_distance)
    required_tp_distance = max(take_profit_pips * point, min_stop_distance)

    if direction == 1:
        sl = price - required_sl_distance
        tp = price + required_tp_distance
    elif direction == 0:
        sl = price + required_sl_distance
        tp = price - required_tp_distance
    else:
        raise ValueError("Direction musi być 1 lub 0")

    if abs(tp - price) < 1.5 * abs(price - sl):
        print(f"⚠️ RR < 1.5 dla {symbol}, pomijam zlecenie")
        return None, None

    return sl, tp

def get_latest_features(symbol):
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, 100)
    if rates is None or len(rates) < 100:
        raise ValueError(f"Nie udało się pobrać wystarczającej liczby świec dla {symbol}")
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    df = add_all_ta_features(df, open="open", high="high", low="low", close="close", volume="tick_volume", fillna=True)
    FEATURES = [col for col in df.columns if col.startswith(('volume_', 'trend_', 'momentum_', 'volatility_'))]
    return df[FEATURES].iloc[-1:], df

def filter_by_trend_rsi(df, direction):
    ema_50 = df['trend_ema_fast']
    ema_200 = df['trend_ema_slow']
    rsi = df['momentum_rsi']
    if ema_50.isnull().any() or ema_200.isnull().any() or rsi.isnull().any():
        print("⚠️ Brak wymaganych danych EMA lub RSI")
        return False
    ema_50_latest = ema_50.iloc[-1]
    ema_200_latest = ema_200.iloc[-1]
    rsi_latest = rsi.iloc[-1]
    if direction == 1:
        return ema_50_latest > ema_200_latest and rsi_latest > 50
    elif direction == 0:
        return ema_50_latest < ema_200_latest and rsi_latest < 50
    return False

def predict_price_direction(symbol):
    try:
        df_row, df_full = get_latest_features(symbol)
        probas = model.predict_proba(df_row)[0]
        prediction = int(np.argmax(probas))
        confidence = float(np.max(probas))
        if not filter_by_trend_rsi(df_full, prediction):
            print(f"🟡 {symbol}: Sygnał {prediction} odrzucony — brak zgodności z trendem (EMA/RSI)")
            return -1, 0.0
        return prediction, confidence
    except Exception as e:
        print(f"❌ [{symbol}] Błąd predykcji: {e}")
        return -1, 0.0

def place_order(symbol, direction, confidence):
    info = mt5.symbol_info(symbol)
    if not info:
        print(f"❌ Brak informacji o symbolu {symbol}")
        return

    # Ustal poprawny wolumen w zależności od wymagań brokera
    lot = max(info.volume_min, min(VOLUME, info.volume_max))
    lot = round(lot / info.volume_step) * info.volume_step

    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        print(f"❌ Nie można pobrać ticka dla {symbol}")
        return

    price = tick.ask if direction == 1 else tick.bid
    sl_points, tp_points = get_dynamic_sl_tp(symbol)
    sl, tp = calculate_sl_tp(price, direction, sl_points, tp_points, symbol)
    if sl is None or tp is None:
        return

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": mt5.ORDER_TYPE_BUY if direction == 1 else mt5.ORDER_TYPE_SELL,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 10,
        "magic": MAGIC,
        "comment": "AI Forex Bot",
        "type_filling": mt5.ORDER_FILLING_FOK,
    }

    print(f"📤 Wysyłam zlecenie: {request}")
    result = mt5.order_send(request)
    if result is None:
        print(f"❌ [{symbol}] Nie udało się wysłać zlecenia. Błąd MT5: {mt5.last_error()}")
        return

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"❌ [{symbol}] Błąd zlecenia: {result.retcode}")
    else:
        print(f"✅ Zlecenie {symbol}: {'BUY' if direction == 1 else 'SELL'} {lot} @ {price:.5f}")
    
    log_trade(symbol, direction, price, sl, tp, lot, direction, result, confidence)


# Sprawdza, czy istnieje już otwarta pozycja na symbol w danym kierunku
def is_duplicate_trade(symbol, direction):
    positions = mt5.positions_get(symbol=symbol)
    if positions is None:
        return False
    for pos in positions:
        if pos.type == (0 if direction == 1 else 1):
            return True
    return False

# Logging trades to CSV
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

def is_trading_time():
    now = datetime.now(TIMEZONE)
    if now.weekday() == 0 and now.hour < 1:
        return False
    if now.weekday() == 4 and now.hour == 23:
        return False
    return now.weekday() < 5

def plot_equity_curve(log_file):
    df = pd.read_csv(log_file)
    df['time'] = pd.to_datetime(df['time'])
    df['profit'] = df['tp'] - df['price']
    df['cumsum'] = df['profit'].cumsum()
    plt.figure(figsize=(12, 6))
    plt.plot(df['time'], df['cumsum'], label='Equity Curve')
    plt.xlabel("Time")
    plt.ylabel("Cumulative Profit")
    plt.title("Equity Curve")
    plt.legend()
    plt.grid()
    plt.show()

# Inicjalizacja MetaTrader 5
if not mt5.initialize():
    print("❌ Nie udało się połączyć z MetaTrader 5:", mt5.last_error())
    quit()

print(f"🤖 AI Forex Bot działa co {INTERVAL_MINUTES} min.")
# load_last_processed_bars()  # <- Na starcie

try:
    while True:
        if not is_trading_time():
            print("🌙 Poza godzinami handlu — pauza 5 minut...")
            time.sleep(300)
            continue

        for symbol in SYMBOLS:
            print(f"\n⏰ [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] — {symbol} analiza...")
            # === Decyzja AI ===
            prediction, confidence = predict_price_direction(symbol)
            if prediction == -1 or confidence < DECISION_THRESHOLD:
                continue
            if prediction in [0, 1]:
                if is_duplicate_trade(symbol, prediction):
                    print(f"⚠️ {symbol}: Pozycja {['SELL','BUY'][prediction]} już otwarta — pomijam.")
                    continue
                place_order(symbol, prediction, confidence)
            else:
                print(f"🟡 [{symbol}] Pominięto — zbyt niska pewność ({confidence:.2f})")

        print(f"💤 Oczekiwanie {INTERVAL_MINUTES} minut...\n")
        time.sleep(INTERVAL_MINUTES * 60)
except KeyboardInterrupt:
    print("🛑 Bot zatrzymany przez użytkownika.")
    plot_equity_curve(LOG_FILE)
mt5.shutdown()
