import csv
import MetaTrader5 as mt5  # type: ignore
import pandas as pd
from ta import add_all_ta_features
import time
import joblib
from datetime import datetime, timedelta
import pytz
import os
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)
import numpy as np
from ta.volatility import AverageTrueRange
from ta.momentum import RSIIndicator
import ta

# ======== PARAMETRY ========
SYMBOLS = ["CHFSGT", "EURDKK", "EURHKD", "EURHUF", "EURNOK", "EURUSD", "EURPLN", "EURSEK", "EURSGT", "EURTRY", "EURZAR", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "NZDUSD", "USDCAD", "EURGBP", "EURJPY", "EURCHF", "GBPJPY", "GBPCHF", "AUDJPY", "AUDCHF", "NZDJPY", "NZDCHF", "CADJPY", "CADCHF", "AUDCAD", "AUDNZD", "EURAUD", "GBPAUD", "EURCAD", "GBPCAD", "EURNZD", "GBPNZD", "AUDSGD", "EURSGD", "GBPSGD", "USDSEK", "USDAUD", "USDNOK", "USDPLN", "USDZAR", "USDHKD", "USDTRY", "USDMXN", "USDCNH", "USDILS", "USDINR", "USDPHP", "USDKRW", "USDTWD", "USDBRL", "USDTHB", "USDSGD"]
MODEL_PATH = "forex_model_xgb.pkl"
LOG_FILE = "trades_log.csv"
EXPECTED_FEATURES = ['open', 'high', 'low', 'close', 'tick_volume', 'spread']
TIMEZONE = pytz.timezone("Etc/UTC")

MAGIC = 123456
DEFAULT_MIN_STOP_LEVEL = 10
SL_TRAINING_DISTANCE = 15  # minimalna odległość do pobrania danych historycznych
ATR_PERIOD = 14
ATR_MULTIPLIER_SL = 1.5
ATR_MULTIPLIER_TP = 3.0
DECISION_THRESHOLD = 0.6
MIN_TRADE_INTERVAL_MINUTES = 2 # minimalna przerwa między transakcjami na tym samym symbolu

model = joblib.load(MODEL_PATH)

def is_trading_time():
    now = datetime.now(TIMEZONE)
    if now.weekday() == 0 and now.hour < 1:
        return False
    if now.weekday() == 4 and now.hour == 23:
        return False
    return now.weekday() < 5

def update_trailing_stops():
    open_positions = mt5.positions_get()
    if open_positions is None or len(open_positions) == 0:
        # print("ℹ️ Brak otwartych pozycji do aktualizacji trailing stopów.")
        return
    
    for pos in open_positions:

        symbol = pos.symbol
        sl = pos.sl

        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            print(f"❌ Brak ticka dla {symbol}")
            continue

        current_price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
        trailing_distance = SL_TRAINING_DISTANCE * mt5.symbol_info(symbol).point  # 30 punktów
        digits = mt5.symbol_info(symbol).digits

        new_sl = (current_price - trailing_distance) if pos.type == mt5.ORDER_TYPE_BUY else (current_price + trailing_distance)
        new_sl = round(new_sl, digits)

        # Aktualizuj tylko jeśli nowy SL jest korzystniejszy
        if (pos.type == mt5.ORDER_TYPE_BUY and new_sl > sl) or (pos.type == mt5.ORDER_TYPE_SELL and new_sl < sl):
            modify_request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "position": pos.ticket,
                "sl": new_sl,
                "tp": pos.tp,
                "symbol": symbol,
                "magic": MAGIC
            }
            result = mt5.order_send(modify_request)
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                print(f"🔄 [{now.strftime('%H:%M')}] — SL zaktualizowany dla {symbol} na {new_sl:.{digits}f}")
            else:
                print(f"⚠️ Błąd aktualizacji SL {symbol}: {result.retcode}")


if not mt5.initialize():
    print("❌ Nie udało się połączyć z MetaTrader 5:", mt5.last_error())
    quit()

print(f"🤖 AI Forex Bot działa co {MIN_TRADE_INTERVAL_MINUTES} min.")

try:
    # Ustawienie początkowych wartości trailing stopów
    next_trade_time = datetime.now()
    next_trailing_time = datetime.now()
    while True:
        now = datetime.now()

        if not is_trading_time():
            print("🌙 Poza godzinami handlu — pauza 5 minut...")
            time.sleep(300)
            continue

        if now >= next_trailing_time:
            # print(f"🔁 [{now.strftime('%H:%M')}] — Aktualizacja trailing stopów")
            update_trailing_stops()
            next_trailing_time = now + pd.Timedelta(minutes = MIN_TRADE_INTERVAL_MINUTES)

        time.sleep(5)  # krótki sleep, by nie obciążać CPU


except KeyboardInterrupt:
    print("🛑 Bot zatrzymany przez użytkownika.")

mt5.shutdown()
