import MetaTrader5 as mt5 # type: ignore
import time
from datetime import datetime
import pytz

# ===== PARAMETRY =====
TIMEZONE = pytz.timezone("Etc/UTC")
TRAILING_DISTANCE_PIPS = 15  # trailing SL w pipsach
CHECK_INTERVAL_SECONDS = 30
MAGIC = 123456  # Magic number do filtrowania pozycji bota

# Inicjalizacja
if not mt5.initialize():
    print("❌ Nie udało się połączyć z MT5:", mt5.last_error())
    quit()

def is_trading_time():
    now = datetime.now(TIMEZONE)
    if now.weekday() == 0 and now.hour < 1:
        return False
    if now.weekday() == 4 and now.hour == 23:
        return False
    return now.weekday() < 5

def update_trailing_stops():
    positions = mt5.positions_get()
    if not positions:
        return

    for pos in positions:
        if pos.magic != MAGIC:
            continue

        profit = pos.profit
        if profit <= 0:
            continue  # Tylko dla zyskownych pozycji

        symbol = pos.symbol
        symbol_info = mt5.symbol_info(symbol)
        if not symbol_info:
            continue

        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            continue

        point = symbol_info.point
        digits = symbol_info.digits
        trailing_sl = TRAILING_DISTANCE_PIPS * point
        sl = pos.sl
        price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask

        new_sl = price - trailing_sl if pos.type == mt5.ORDER_TYPE_BUY else price + trailing_sl
        new_sl = round(new_sl, digits)

        # Warunek poprawy SL
        if (pos.type == mt5.ORDER_TYPE_BUY and (sl == 0 or new_sl > sl)) or \
           (pos.type == mt5.ORDER_TYPE_SELL and (sl == 0 or new_sl < sl)):
            
            modify = {
                "action": mt5.TRADE_ACTION_SLTP,
                "position": pos.ticket,
                "sl": new_sl,
                "tp": pos.tp,
                "symbol": symbol,
                "magic": MAGIC
            }
            result = mt5.order_send(modify)
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                print(f"🔄 [{datetime.now().strftime('%H:%M:%S')}] SL zaktualizowany dla {symbol} na {new_sl}")
            else:
                print(f"⚠️ Błąd SL {symbol}: {result.retcode}")

try:
    print("📈 Trailing SL watcher uruchomiony (co 30 sek)...")
    while True:
        if not is_trading_time():
            print("🌙 Poza godzinami handlu — pauza 5 minut.")
            time.sleep(300)
            continue

        update_trailing_stops()
        time.sleep(CHECK_INTERVAL_SECONDS)

except KeyboardInterrupt:
    print("🛑 Zatrzymano trailing stop bota.")

mt5.shutdown()
