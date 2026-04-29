import MetaTrader5 as mt5

# Inicjalizacja MT5
if not mt5.initialize():
    print("Nie można zainicjalizować MT5")
    print("Sprawdź, czy terminal MT5 jest uruchomiony i dostępny")
    exit()

print("Połączenie z MT5: OK")

# Sprawdź status konta
account_info = mt5.account_info()
if account_info:
    print(f"Account: {account_info.name}")
    print(f"Saldo: {account_info.balance}")
    print(f"Equity: {account_info.equity}")
else:
    print("Nie można pobrać informacji o koncie")

# Spróbuj pobrać pozycje
positions = mt5.positions_get()
print(f"\nOtwarte pozycje: {len(positions) if positions else 0}")

if positions:
    for pos in positions:
        print(f"  Ticket: {pos.ticket}, Symbol: {pos.symbol}, Profit: {pos.profit}")

# Spróbuj pobrać ostatnią transakcję
last_deal = mt5.history_deals_get(position_id=0)
print(f"\nOstatnie transakcje: {len(last_deal) if last_deal else 0}")

mt5.shutdown()
