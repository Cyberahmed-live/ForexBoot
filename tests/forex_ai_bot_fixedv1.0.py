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
warnings.filterwarnings("ignore", category=FutureWarning)
import numpy as np  # dodaj na górze, jeśli jeszcze nieimportowane
from ta.volatility import AverageTrueRange
from ta.momentum import RSIIndicator
import ta

# ======== PARAMETRY ========
SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF"]
VOLUME = 1
MODEL_PATH = "forex_model_xgb.pkl"
LOG_FILE = "trades_log.csv"
EXPECTED_FEATURES = ['open', 'high', 'low', 'close', 'tick_volume', 'spread']
TIMEZONE = pytz.timezone("Etc/UTC")
# Interwał działania bota w minutach
INTERVAL_MINUTES = 60
# Automatyczne dopasowanie timeframe do interwału działania
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
DEFAULT_MIN_STOP_LEVEL = 20
ATR_PERIOD = 14
ATR_MULTIPLIER_SL = 1.5
ATR_MULTIPLIER_TP = 3.0
DECISION_THRESHOLD = 0.6
TRAILING_STOP_POINTS = 200  # np. 20 pipsów (dla brokerów 5-cyfrowych)

# === Wczytaj model AI ===
model = joblib.load(MODEL_PATH)

# === Sprawdzenie zgodności cech modelu ===
def get_atr_value(symbol):
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, 100)
    if rates is None or len(rates) < ATR_PERIOD:
        raise ValueError(f"Nie udało się pobrać danych dla ATR dla {symbol}")

    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)

    atr = AverageTrueRange(
        high=df["high"],
        low=df["low"],
        close=df["close"],
        window=ATR_PERIOD,
        fillna=True
    )
    return atr.average_true_range().iloc[-1]

# === Dynamiczne SL/TP w punktach ===
def get_dynamic_sl_tp(symbol):
    info = mt5.symbol_info(symbol)
    if not info:
        print(f"⚠️ Brak informacji o symbolu {symbol}, używam wartości domyślnych.")
        return DEFAULT_MIN_STOP_LEVEL, TRAILING_STOP_POINTS  # domyślnie: SL 10 pipsów, TP 30 pipsów (zakładamy 5-cyfrowy broker)

    point = info.point
    min_points = info.trade_stops_level

    if min_points <= 0:
        print(f"⚠️ trade_stops_level dla {symbol} to 0 lub brak, ustawiam wartości domyślne.")
        return DEFAULT_MIN_STOP_LEVEL, TRAILING_STOP_POINTS

    try:
        atr = get_atr_value(symbol)
        if atr is None or atr <= 0:
            raise ValueError("ATR jest nieprawidłowy")
        
        # Przelicz ATR na punkty (liczone wg punktu, np. 0.00001 dla EURUSD)
        sl_points = max(int((atr * ATR_MULTIPLIER_SL) / point), int(min_points * 1.5))
        tp_points = max(int((atr * ATR_MULTIPLIER_TP) / point), int(min_points * 4.5))

        return sl_points, tp_points
    except Exception as e:
        print(f"⚠️ Błąd ATR dla {symbol}: {e} — używam wartości awaryjnych")
        return int(min_points * 1.5), int(min_points * 4.5)

# === Obliczanie SL/TP na podstawie punktów ===
# === Obliczanie poziomów SL i TP na podstawie ceny, kierunku i pipsów ===
def calculate_sl_tp(price, direction, stop_loss_pips, take_profit_pips, symbol):
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        raise ValueError(f"Nie można pobrać informacji o symbolu {symbol}")

    if (tp - price) < 1.5 * abs(price - sl):
        print(f"⚠️ RR < 1.5 dla {symbol}, pomijam zlecenie")
        return None, None

    point = symbol_info.point
    min_stop_level = symbol_info.trade_stops_level  # minimalny odstęp w punktach

    # Ustaw wartość domyślną, jeśli broker nie ustawia stop level

    effective_stop_level = min_stop_level if min_stop_level > 0 else DEFAULT_MIN_STOP_LEVEL
    min_stop_distance = effective_stop_level * point

    print(f"ℹ️ {symbol} trade_stops_level: {min_stop_level}, używam: {effective_stop_level} punktów (odległość {min_stop_distance:.5f})")

    # SL i TP — nie mniejsze niż wymagane minimum
    required_sl_distance = max(stop_loss_pips * point, min_stop_distance)
    required_tp_distance = max(take_profit_pips * point, min_stop_distance)

    if direction == 1 or direction == "buy":
        sl = price - required_sl_distance
        tp = price + required_tp_distance
        if sl >= price:
            sl = price - min_stop_distance  # dodatkowe zabezpieczenie
    elif direction == 0 or direction == "sell":
        sl = price + required_sl_distance
        tp = price - required_tp_distance
        if sl <= price:
            sl = price + min_stop_distance
    else:
        raise ValueError("Direction musi być 1/'buy' lub 0/'sell'")

    return sl, tp


# === Pobranie najnowszych cech ===
def get_latest_features(symbol):
    # Pobierz więcej świec (np. 500) dla stabilnych wskaźników technicznych
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, 500)

    # Zabezpieczenie: brak danych lub za mało danych
    if rates is None or len(rates) < 100:
        raise ValueError(f"Nie udało się pobrać wystarczającej liczby świec dla {symbol}")

    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)

    # Dodaj cechy techniczne
    df = add_all_ta_features(
        df, open="open", high="high", low="low",
        close="close", volume="tick_volume", fillna=True
    )

    # Wybierz tylko kolumny z cechami do predykcji
    FEATURES = [col for col in df.columns if col.startswith(('volume_', 'trend_', 'momentum_', 'volatility_'))]
    return df[FEATURES].iloc[-1:]  # ostatni wiersz jako wektor predykcyjny

def filter_by_trend_rsi(df, direction):
    ema_50 = df['trend_ema_fast']  # EMA 50
    ema_200 = df['trend_ema_slow']  # EMA 200
    rsi = df['momentum_rsi']

    # Sprawdzenie, czy kolumny są dostępne
    if ema_50.isnull().any() or ema_200.isnull().any() or rsi.isnull().any():
        print("⚠️ Brak wymaganych danych EMA lub RSI")
        return False

    # Pobierz ostatnie wartości
    ema_50_latest = ema_50.iloc[-1]
    ema_200_latest = ema_200.iloc[-1]
    rsi_latest = rsi.iloc[-1]

    if direction == 1:  # BUY
        return ema_50_latest > ema_200_latest and rsi_latest > 50
    elif direction == 0:  # SELL
        return ema_50_latest < ema_200_latest and rsi_latest < 50
    return False
    
# === Predykcja kierunku ceny ===
def predict_price_direction(symbol):
    try:
        df = get_latest_features(symbol)
        probas = model.predict_proba(df)[0]
        prediction = int(np.argmax(probas))
        confidence = float(np.max(probas))

        if not filter_by_trend_rsi(df, prediction):
            print(f"🟡 {symbol}: Sygnał {prediction} odrzucony — brak zgodności z trendem (EMA/RSI)")
            return -1, 0.0

        return prediction, confidence
    except Exception as e:
        print(f"❌ [{symbol}] Błąd predykcji: {e}")
        return -1, 0.0


# === Składanie zlecenia ===
def place_order(symbol, direction, confidence):
    lot = VOLUME
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        print(f"❌ Nie można pobrać ticka dla {symbol}")
        return

    price = tick.ask if direction == 1 else tick.bid
    sl_points, tp_points = get_dynamic_sl_tp(symbol)
    sl, tp = calculate_sl_tp(price, direction, sl_points, tp_points, symbol)

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

    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"❌ [{symbol}] Błąd zlecenia: {result.retcode}")
    else:
        print(f"✅ Zlecenie {symbol}: {'BUY' if direction == 1 else 'SELL'} {lot} @ {price:.5f}")

    log_trade(
        symbol=symbol,
        direction="BUY" if direction == 1 else "SELL",
        price=price,
        sl=sl,
        tp=tp,
        volume=lot,
        prediction=prediction,
        result=result,
        confidence=confidence
    )


# === Logowanie transakcji ===
def log_trade(symbol, direction, price, sl, tp, volume, prediction, result, confidence):
    file_exists = os.path.isfile(LOG_FILE)
    with open(LOG_FILE, mode="a", newline="") as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(["time", "symbol", "type", "price", "sl", "tp", "volume", "prediction", "status", "order_id", "confidence"])
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            symbol,
            "BUY" if direction == 1 else "SELL",
            price,
            sl,
            tp,
            volume,
            prediction,
            "OK" if result.retcode == mt5.TRADE_RETCODE_DONE else f"ERR {result.retcode}",
            result.order if hasattr(result, "order") else "-",
            f"{confidence:.2f}"
        ])


# === Sprawdzenie godzin handlu ===
def is_trading_time():
    now = datetime.now(TIMEZONE)
    if now.weekday() == 0 and now.hour < 1:
        return False
    if now.weekday() == 4 and now.hour == 23:
        return False
    return now.weekday() < 5

# === Inicjalizacja MT5 ===
if not mt5.initialize():
    print("❌ Nie udało się połączyć z MetaTrader 5:", mt5.last_error())
    quit()

print(f"🤖 AI Forex Bot działa co {INTERVAL_MINUTES} min.")

# === Główna pętla ===
try:
    while True:
        if not is_trading_time():
            print("🌙 Poza godzinami handlu — pauza 5 minut...")
            time.sleep(300)
            continue

        for symbol in SYMBOLS:
            print(f"\n⏰ [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] — {symbol} analiza...")
            # prediction = predict_price_direction(symbol)
            prediction, confidence = predict_price_direction(symbol)
            if prediction == -1 or confidence < DECISION_THRESHOLD:
                continue  # pomiń symbol

            if prediction in [0, 1]:
                place_order(symbol, prediction, confidence)
            else:
                print(f"🟡 [{symbol}] Pominięto — zbyt niska pewność ({confidence:.2f})")

        print(f"💤 Oczekiwanie {INTERVAL_MINUTES} minut...\n")
        time.sleep(INTERVAL_MINUTES * 60)

except KeyboardInterrupt:
    print("🛑 Bot zatrzymany przez użytkownika.")

mt5.shutdown()

