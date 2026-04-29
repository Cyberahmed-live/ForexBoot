import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime

# Inicjalizacja MT5
if not mt5.initialize():
    print("Nie można zainicjalizować MT5")
    exit()

# Pobierz CAŁĄ historię transakcji bez ograniczenia daty
deals = mt5.history_deals_total()
print(f"Całkowita liczba transakcji: {deals}")

# Pobierz wszystkie transakcje
all_deals = mt5.history_deals_get(0, None)

if all_deals:
    # Konwertuj na DataFrame
    data = [
        {
            'ticket': d.ticket,
            'symbol': d.symbol,
            'type': d.type,
            'profit': d.profit,
            'commission': d.commission,
            'volume': d.volume,
            'time': datetime.fromtimestamp(d.time)
        }
        for d in all_deals
    ]
    df = pd.DataFrame(data)
    
    # Szukaj transakcji 2997158
    result = df[df['ticket'] == 2997158]
    
    if len(result) > 0:
        print("\n" + "="*80)
        print("ZNALEZIONA TRANSAKCJA 2997158")
        print("="*80)
        row = result.iloc[0]
        for col in result.columns:
            print(f"{col:20s}: {row[col]}")
    else:
        print(f"\nTransakcja 2997158 nie znaleziona.")
        print(f"Dostępne numery ticketów od {df['ticket'].min()} do {df['ticket'].max()}")
        
        # Spróbuj znaleźć ostatnie transakcje z dużym minusem
        df['profit'] = pd.to_numeric(df['profit'], errors='coerce')
        big_losses = df[df['profit'] < -100].sort_values('profit', ascending=True).tail(15)
        
        if len(big_losses) > 0:
            print("\n" + "="*80)
            print("OSTATNIE TRANSAKCJE Z DUŻYMI STRATAMI (< -100)")
            print("="*80)
            print(big_losses[['ticket', 'symbol', 'type', 'profit', 'volume', 'time']])
else:
    print("Brak historii transakcji")

mt5.shutdown()
