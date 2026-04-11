import csv
import MetaTrader5 as mt5 # type: ignore
import pandas as pd
from ta import add_all_ta_features
import time
import joblib
from datetime import datetime
import pytz
import logging
import os

# ======== PARAMETRY ========
SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "EURSGT", "USDCHF"]  # Lista symboli , "EURSGT", "EURPLN", "EURPLN", "USDCHF"
SL = 10  # w punktach
TP = 50  # w punktach
VOLUME = 0.5
MODEL_PATH = "forex_model_xgb.pkl"
LOG_FILE = "trades_log.csv"
EXPECTED_FEATURES = ['open', 'high', 'low', 'close', 'tick_volume', 'spread']
TIMEZONE = pytz.timezone("Etc/UTC")
INTERVAL_MINUTES = 15
TIMEFRAME = mt5.TIMEFRAME_M15
MAGIC = 123456
DIGITS = 5  # ilość miejsc po przecinku w cenie (np. 5 dla EURUSD)

# Funkcje pomocnicze
# === Wczytaj model AI ===
model = joblib.load("forex_model_xgb.pkl")

# === Pomocnicza: przeliczenie pipsów na wartość ceny ===
def pips_to_price(pips):
    return pips * 10 ** (-DIGITS)

# === Obliczanie poziomów SL i TP na podstawie ceny, kierunku i pipsów ===
def calculate_sl_tp(price, direction, stop_loss_pips, take_profit_pips, symbol):
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        raise ValueError(f"Nie można pobrać informacji o symbolu {symbol}")

    point = symbol_info.point
    min_stop_level = symbol_info.trade_stops_level  # minimalny odstęp w punktach

    # Zamiana minimalnego poziomu na wartość w cenie
    min_stop_distance = min_stop_level * point

    # Minimalny wymagany stop loss w punktach
    required_sl_distance = max(stop_loss_pips * point, min_stop_distance)
    required_tp_distance = max(take_profit_pips * point, min_stop_distance)

    if direction.lower() == "buy":
        sl = price - required_sl_distance
        tp = price + required_tp_distance
        # Sprawdź poprawność: SL musi być poniżej ceny
        if sl >= price:
            sl = price - min_stop_distance
    elif direction.lower() == "sell":
        sl = price + required_sl_distance
        tp = price - required_tp_distance
        # Sprawdź poprawność: SL musi być powyżej ceny
        if sl <= price:
            sl = price + min_stop_distance
    else:
        raise ValueError("Direction musi być 'buy' lub 'sell'")

    return sl, tp

# === Pobranie najnowszych cech do predykcji ===
def get_latest_features(symbol):
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, 50)
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)

    df = add_all_ta_features(
        df, open="open", high="high", low="low",
        close="close", volume="tick_volume", fillna=True
    )

    FEATURES = [col for col in df.columns if col.startswith(('volume_', 'trend_', 'momentum_', 'volatility_'))]
    return df[FEATURES].iloc[-1:]

# === Predykcja kierunku ceny: 1 = BUY, 0 = SELL ===
def predict_price_direction(symbol):
    try:
        latest_features = get_latest_features(symbol)
        prediction = model.predict(latest_features)[0]
        return int(prediction)
    except Exception as e:
        print("❌ Błąd predykcji:", e)
        return -1

# === Składanie zlecenia BUY/SELL z SL/TP ===
def place_order(direction, symbol):
    lot = VOLUME
    tick = mt5.symbol_info_tick(symbol)
    if direction == 1:  # BUY
        price = tick.ask
    elif direction == 0:  # SELL
        price = tick.bid
    else:
        print("❌ Błąd predykcji: Kierunek musi być 1 (BUY) lub 0 (SELL)")
        return

    stop_loss_pips = SL  # zmień jeśli chcesz inną wartość
    take_profit_pips = TP  # zmień jeśli chcesz inną wartość

    sl, tp = calculate_sl_tp(price, direction, stop_loss_pips, take_profit_pips, symbol)

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": mt5.ORDER_TYPE_BUY if direction == 1 else mt5.ORDER_TYPE_SELL,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 10,
        "magic": 123456,
        "comment": "Forex bot order",
        "type_filling": mt5.ORDER_FILLING_FOK, # ORDER_FILLING_RETURNlub ORDER_FILLING_IOC
    }

    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"❌ Błąd zlecenia: {result.retcode}")
    else:
        print(f"✅ Zlecenie złożone: {direction} {lot} {symbol} @ {price:.5f}")
        
    print(f"{symbol}, Zlecenie: {direction}, PRICE: {price:.5f}, SL: {sl:.5f}, TP: {tp:.5f}")
    # Logowanie transakcji
    log_trade(symbol, direction, price, sl, tp, VOLUME, prediction=1 if direction == "buy" else 0, result=result)

def log_trade(symbol, direction, price, sl, tp, volume, prediction, result):
    filename = "trades_log.csv"
    file_exists = os.path.isfile(filename)

    with open(filename, mode="a", newline="") as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(["time", "symbol", "type", "price", "sl", "tp", "volume", "prediction", "status", "order_id"])

        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            symbol,
            direction.upper(),
            price,
            sl,
            tp,
            volume,
            prediction,
            "OK" if result.retcode == mt5.TRADE_RETCODE_DONE else f"ERR {result.retcode}",
            result.order if hasattr(result, "order") else "-"
        ])

# === Inicjalizacja MT5 ===
if not mt5.initialize():
    print("❌ Nie udało się połączyć z MetaTrader 5:", mt5.last_error())
    quit()

print(f"🤖 AI Forex Bot działa, co {INTERVAL_MINUTES} min")

# ======== SPRAWDŹ CZY JEST GODZINA HANDLU ========
def is_trading_time():
    now = datetime.now(TIMEZONE)
    if now.weekday() == 0 and now.hour < 1:
        return False
    if now.weekday() == 4 and now.hour == 23:
        return False
    return now.weekday() < 5

# ======== GŁÓWNA PĘTLA ========
print("Start trading loop...")
try:
    while True:
        if not is_trading_time():
            print("Poza godzinami handlu, śpię 5 minut...")
            time.sleep(300)
            continue

        for symbol in SYMBOLS:
            try:
                print(f"\n⏰ [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] — {symbol} analiza...")
                prediction = predict_price_direction(symbol)
            except Exception as e:
                print(f"[{symbol}] Błąd predykcji: {e}")
                continue

            if prediction in [0, 1]:
                order_result = place_order(symbol, prediction)
            else:
                print(f"🟡 [{symbol}] Brak sygnału lub błąd predykcji")
                continue

        # Po zakończeniu iteracji przez wszystkie symbole, czekaj przed kolejną iteracją
        print(f"💤 Oczekiwanie {INTERVAL_MINUTES} minut...\n")
        time.sleep(INTERVAL_MINUTES * 60)  # Czekaj x minut przed kolejną iteracją

except KeyboardInterrupt:
    print("🛑 Bot zatrzymany przez użytkownika.")

mt5.shutdown()