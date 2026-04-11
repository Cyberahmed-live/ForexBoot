import MetaTrader5 as mt5

# Próba połączenia z MetaTrader 5
if not mt5.initialize():
    print("❌ Nie udało się połączyć z MetaTrader 5.")
    print("Kod błędu:", mt5.last_error())
else:
    print("✅ Połączenie z MetaTrader 5 nawiązane!")
    # Pobieranie podstawowych informacji
    info = mt5.terminal_info()
    print("Wersja MT5:", info.version)
    print("Ścieżka instalacji:", info.path)
    mt5.shutdown()