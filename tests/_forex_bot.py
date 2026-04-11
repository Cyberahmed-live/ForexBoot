import MetaTrader5 as mt5
import pandas as pd
import time
from datetime import datetime

# === Konfiguracja ===
SYMBOL = "EURUSD"
LOT = 0.1
MAGIC = 123456

SL_PIPS = 10
TP_PIPS = 20
DIGITS = 5  # Dla EURUSD najczęściej 5

INTERVAL_MINUTES = 15  # Co ile minut działa bot


# === Funkcja pomocnicza do przeliczania pipsów na cenę ===
def pips_to_price(pips):
    return pips * 10 ** (-DIGITS)


# === Przykładowa funkcja predykcji (tu: losowa decyzja) ===
def predict_price_direction():
    # W prawdziwej wersji tutaj możesz dodać AI lub wskaźniki
    # 1 = BUY, 0 = SELL, -1 = brak decyzji
    from random import choice
    return choice([1, 0, -1])


# === Funkcja składania zlecenia z SL/TP ===
def place_order(action):
    print(f"📤 Składam zlecenie: {action.upper()}")

    symbol_info = mt5.symbol_info(SYMBOL)
    if symbol_info is None or not symbol_info.visible:
        if not mt5.symbol_select(SYMBOL, True):
            print(f"❌ Nie udało się wybrać symbolu {SYMBOL}")
            return

    tick = mt5.symbol_info_tick(SYMBOL)
    sl_p = pips_to_price(SL_PIPS)
    tp_p = pips_to_price(TP_PIPS)

    if action == "buy":
        price = tick.ask
        sl = round(price - sl_p, DIGITS)
        tp = round(price + tp_p, DIGITS)
        order_type = mt5.ORDER_TYPE_BUY
    else:
        price = tick.bid
        sl = round(price + sl_p, DIGITS)
        tp = round(price - tp_p, DIGITS)
        order_type = mt5.ORDER_TYPE_SELL

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": LOT,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 10,
        "magic": MAGIC,
        "comment": "AI Forex Bot",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_RETURN,
    }

    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print("❌ Błąd zlecenia:", result.retcode, result.comment)
    else:
        print("✅ Zlecenie złożone:", result)


# === Inicjalizacja MetaTrader 5 ===
if not mt5.initialize():
    print("❌ Nie udało się połączyć z MetaTrader 5:", mt5.last_error())
    quit()

print(f"🤖 Bot wystartował o {datetime.now().strftime('%H:%M:%S')} — działa co {INTERVAL_MINUTES} minut")

# === Główna pętla działania bota ===
try:
    while True:
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"\n⏰ [{now}] Analiza rynku...")

        prediction = predict_price_direction()
        if prediction == 1:
            place_order("buy")
        elif prediction == 0:
            place_order("sell")
        else:
            print("🟡 Brak sygnału — czekam.")

        print(f"💤 Oczekiwanie {INTERVAL_MINUTES} minut...\n")
        time.sleep(INTERVAL_MINUTES * 60)
except KeyboardInterrupt:
    print("🛑 Bot zatrzymany przez użytkownika.")

# === Zakończenie ===
mt5.shutdown()
print("✅ Połączenie z MetaTrader 5 zakończone.")
# === Zakończenie działania bota ===