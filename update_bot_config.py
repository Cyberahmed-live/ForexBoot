"""Aktualizacja bot_config: daily_loss_usd_limit + max_open_positions=3"""
import pyodbc

conn = pyodbc.connect(
    'DRIVER={ODBC Driver 17 for SQL Server};SERVER=appdbpri;DATABASE=ForexBotDB;Trusted_Connection=yes'
)
cur = conn.cursor()

# Sprawdz aktualna wartosc max_open_positions
cur.execute("SELECT key_name, value FROM bot_config WHERE key_name IN ('max_open_positions','daily_loss_usd_limit')")
rows = cur.fetchall()
print("Stan przed:")
for r in rows:
    print(f"  {r[0]} = {r[1]}")

# Ustaw max_open_positions = 3
cur.execute("UPDATE bot_config SET value='3' WHERE key_name='max_open_positions'")
print(f"  UPDATE max_open_positions → {cur.rowcount} row(s) affected")

# Dodaj daily_loss_usd_limit jesli nie istnieje
cur.execute("SELECT COUNT(*) FROM bot_config WHERE key_name='daily_loss_usd_limit'")
if cur.fetchone()[0] == 0:
    cur.execute("INSERT INTO bot_config (key_name, value) VALUES ('daily_loss_usd_limit', '1000')")
    print("  INSERT daily_loss_usd_limit = 1000")
else:
    cur.execute("UPDATE bot_config SET value='1000' WHERE key_name='daily_loss_usd_limit'")
    print(f"  UPDATE daily_loss_usd_limit → {cur.rowcount} row(s) affected")

conn.commit()

# Weryfikacja
cur.execute("SELECT key_name, value FROM bot_config WHERE key_name IN ('max_open_positions','daily_loss_usd_limit')")
rows = cur.fetchall()
print("\nStan po:")
for r in rows:
    print(f"  {r[0]} = {r[1]}")

conn.close()
print("\nOK — bot_config zaktualizowany.")
