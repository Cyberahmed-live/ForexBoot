import MetaTrader5 as mt5
import pandas as pd
import os
from datetime import datetime
from forex_base.globalcfg import get_global_cfg

# --- Ustawienia ---
symbols = get_global_cfg("symbols")         # Pobierz listę symboli z konfiguracji
timeframe = get_global_cfg("timeframe")     # Pobierz interwał z konfiguracji
bars = get_global_cfg("bars")               # Pobierz liczbę świec do pobrania z konfiguracji
output_dir = get_global_cfg("output_dir")   # Katalog do zapisywania danych

# --- Inicjalizacja MT5 ---
if not mt5.initialize():
    print("[ERROR] Nie udało się połączyć z MetaTrader 5:", mt5.last_error())
    quit()

# --- Tworzenie folderu jeśli nie istnieje ---
os.makedirs(output_dir, exist_ok=True)

# --- Pobieranie danych i zapis CSV ---
for symbol in symbols:
    print(f"[INFO] Eksport danych dla: {symbol}")
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)

    if rates is None or len(rates) == 0:
        print(f"[WARNING] Brak danych dla {symbol}, pomiń")
        continue

    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')

    file_path = os.path.join(output_dir, f"{symbol}.csv")
    df.to_csv(file_path, index=False)
    print(f"[OK] Zapisano do: {file_path}")

# --- Zamknięcie połączenia ---
mt5.shutdown()
print("[DONE] Zakończono eksport danych.")