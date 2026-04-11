import MetaTrader5 as mt5 # type: ignore
import pandas as pd
from ta import add_all_ta_features
import joblib
import time
from datetime import datetime
import csv
import os

# === Konfiguracja ===
SYMBOL = "USDJPY"
TIMEFRAME = mt5.TIMEFRAME_M15
DIGITS = 5  # ilość miejsc po przecinku w cenie (np. 5 dla EURUSD)
LOT = 0.5
MAGIC = 123456

SL_PIPS = 20
TP_PIPS = 40

INTERVAL_MINUTES = 30  # jak często bot działa

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
    required_sl_distance = max(stop_loss_pips * point, min_stop_distance) + (point * 10)  # dodajemy dodatkowy margines
    required_tp_distance = max(take_profit_pips * point, min_stop_distance) + (point * 20) # zwiększamy TP

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
def get_latest_features():
    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, 50)
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
def predict_price_direction():
    try:
        X = get_latest_features()
        prediction = model.predict(X)[0]
        return int(prediction)
    except Exception as e:
        print("❌ Błąd predykcji:", e)
        return -1

# === Składanie zlecenia BUY/SELL z SL/TP ===
def place_order(direction):
    symbol = SYMBOL
    lot = LOT

    tick = mt5.symbol_info_tick(symbol)
    if direction == "buy":
        price = tick.ask
    else:
        price = tick.bid

    stop_loss_pips = 10  # zmień jeśli chcesz inną wartość
    take_profit_pips = 20

    sl, tp = calculate_sl_tp(price, direction, stop_loss_pips, take_profit_pips, symbol)

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": mt5.ORDER_TYPE_BUY if direction == "buy" else mt5.ORDER_TYPE_SELL,
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
        
    print(f"{SYMBOL}, Zlecenie: {direction}, PRICE: {price:.5f}, SL: {sl:.5f}, TP: {tp:.5f}")
    # Logowanie transakcji
    log_trade(SYMBOL, direction, price, sl, tp, LOT, prediction=1 if direction == "buy" else 0, result=result)

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

print(f"🤖 AI Forex Bot działa — {SYMBOL}, co {INTERVAL_MINUTES} min")

# === Główna pętla ===
try:
    while True:
        print(f"\n⏰ [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] — analiza...")

        decision = predict_price_direction()
        if decision == 1:
            place_order("buy")
        elif decision == 0:
            place_order("sell")
        else:
            print("🟡 Brak sygnału lub błąd predykcji")

        print(f"💤 Oczekiwanie {INTERVAL_MINUTES} minut...\n")
        time.sleep(INTERVAL_MINUTES * 60)

except KeyboardInterrupt:
    print("🛑 Bot zatrzymany przez użytkownika.")

mt5.shutdown()
