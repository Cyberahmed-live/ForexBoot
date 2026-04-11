import MetaTrader5 as mt5 # type: ignore
import pandas as pd
import time
import joblib
import datetime
import pytz
import logging
import os

# ======== PARAMETRY ========
SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "EURSGT", "EURPLN", "USDCHF"]  # Lista symboli , "EURSGT", "EURPLN", "USDCHF"
SL = 10  # w punktach
TP = 50  # w punktach
VOLUME = 0.5
MODEL_PATH = "forex_model_xgb.pkl"
LOG_FILE = "trades_log.csv"
EXPECTED_FEATURES = ['open', 'high', 'low', 'close', 'tick_volume', 'spread']
TIMEZONE = pytz.timezone("Etc/UTC")
INTERVAL_MINUTES = 30

# ======== KONFIGURACJA LOGGOWANIA ========
if not os.path.exists(LOG_FILE):
    pd.DataFrame(columns=["time", "symbol", "type", "price", "sl", "tp", "volume", "prediction", "status", "order_id"]).to_csv(LOG_FILE, index=False)

def log_trade(data):
    df = pd.read_csv(LOG_FILE)
    df = pd.concat([df, pd.DataFrame([data])], ignore_index=True)
    df.to_csv(LOG_FILE, index=False)

# ======== INICJALIZACJA MT5 ========
if not mt5.initialize():
    raise RuntimeError("MetaTrader5 init error")

# ======== WCZYTAJ MODEL ========
model = joblib.load(MODEL_PATH)

# ======== FUNKCJE POMOCNICZE ========


def get_features(symbol, timeframe=mt5.TIMEFRAME_M30, bars=1):
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df = df[EXPECTED_FEATURES]
    if df.isnull().any().any():
        return None
    return df

def predict_signal(features_df):
    if list(features_df.columns) != EXPECTED_FEATURES:
        raise ValueError("Model feature mismatch")
    return model.predict(features_df)[0]

def place_order(symbol, action, sl_points, tp_points, volume):
    price = mt5.symbol_info_tick(symbol).ask if action == "buy" else mt5.symbol_info_tick(symbol).bid
    deviation = 20

    sl = price - sl_points * mt5.symbol_info(symbol).point if action == "buy" else price + sl_points * mt5.symbol_info(symbol).point
    tp = price + tp_points * mt5.symbol_info(symbol).point if action == "buy" else price - tp_points * mt5.symbol_info(symbol).point

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": mt5.ORDER_TYPE_BUY if action == "buy" else mt5.ORDER_TYPE_SELL,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": deviation,
        "magic": 123456,
        "comment": "AI_forex_bot",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    return {
        "status": result.retcode,
        "order_id": result.order if result.retcode == mt5.TRADE_RETCODE_DONE else None,
        "price": price,
        "sl": sl,
        "tp": tp
    }

# ======== SPRAWDŹ CZY JEST GODZINA HANDLU ========
def is_trading_time():
    now = datetime.datetime.now(TIMEZONE)
    if now.weekday() == 0 and now.hour < 1:
        return False
    if now.weekday() == 4 and now.hour == 23:
        return False
    return now.weekday() < 5

# ======== GŁÓWNA PĘTLA ========
print("Start trading loop...")
while True:
    if not is_trading_time():
        print("Poza godzinami handlu, śpię 5 minut...")
        time.sleep(300)
        continue

    for symbol in SYMBOLS:
        features = get_features(symbol)
        if features is None:
            print(f"[{symbol}] Brak danych")
            continue

        try:
            prediction = predict_signal(features)
        except Exception as e:
            print(f"[{symbol}] Błąd predykcji: {e}")
            continue

        if prediction not in [0, 1]:
            print(f"[{symbol}] Brak sygnału do otwarcia pozycji.")
            continue

        action = "buy" if prediction == 1 else "sell"
        print(f"[{symbol}] Sygnał: {action}")

        order_result = place_order(symbol, action, SL, TP, VOLUME)
        log_trade({
            "time": datetime.datetime.now(TIMEZONE),
            "symbol": symbol,
            "type": action,
            "price": order_result["price"],
            "sl": order_result["sl"],
            "tp": order_result["tp"],
            "volume": VOLUME,
            "prediction": prediction,
            "status": order_result["status"],
            "order_id": order_result["order_id"]
        })

    print("Czekam 30 minut...")
    time.sleep(INTERVAL_MINUTES * 60)  # Czekaj 30 minut przed kolejną iteracją
