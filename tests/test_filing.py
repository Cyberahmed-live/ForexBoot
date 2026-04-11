import MetaTrader5 as mt5

mt5.initialize()

symbol = "EURUSD"
info = mt5.symbol_info(symbol)
if info is not None:
    print(f"Obsługiwany tryb filling dla {symbol}: {info.filling_mode}")
else:
    print("Nie udało się pobrać informacji o symbolu.")

mt5.shutdown()
