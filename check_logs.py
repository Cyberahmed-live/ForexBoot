import pyodbc
import pandas as pd

try:
    conn = pyodbc.connect('Driver={ODBC Driver 17 for SQL Server};Server=appdbpri;Database=ForexBotDB;Trusted_Connection=yes;')
    
    # Szukaj wyników dla GBPCHF w tym czasie
    outcomes_query = '''
    SELECT *
    FROM trade_outcomes
    WHERE symbol = 'GBPCHF'
    AND timestamp BETWEEN '2026-04-27 20:00:00' AND '2026-04-28 12:00:00'
    ORDER BY timestamp DESC
    '''
    
    df_outcomes = pd.read_sql(outcomes_query, conn)
    
    print("\n" + "="*80)
    print("TRADE OUTCOMES - GBPCHF")
    print("="*80)
    
    if len(df_outcomes) > 0:
        for idx, outcome in df_outcomes.iterrows():
            print(f"\nID: {outcome['id']} | Trade ID: {outcome['trade_id']}")
            print(f"  Time: {outcome['timestamp']}")
            print(f"  Direction: {outcome['direction']}")
            print(f"  Profit (pips): {outcome['profit_pips']}")
            print(f"  Profit (money): {outcome['profit_money']}")
            print(f"  Duration: {outcome['duration_hours']} hours")
            print(f"  Max Drawdown: {outcome['max_drawdown']}")
            print(f"  SL Hit: {outcome['sl_hit']} | TP Hit: {outcome['tp_hit']}")
    else:
        print("Brak wyników transakcji")
    
    # Sprawdź wszystkie transakcje GBPCHF z ostatniego miesiąca
    all_gbpchf = '''
    SELECT TOP 20
        id, open_time, direction, price, sl, tp, lot, profit, result, done
    FROM trades
    WHERE symbol = 'GBPCHF'
    AND open_time > DATEADD(month, -1, GETDATE())
    ORDER BY open_time DESC
    '''
    
    df_all = pd.read_sql(all_gbpchf, conn)
    
    print("\n" + "="*80)
    print("OSTATNIE 20 TRANSAKCJI GBPCHF (ostatni miesiąc)")
    print("="*80)
    
    if len(df_all) > 0:
        for idx, trade in df_all.iterrows():
            status_emoji = "✅" if float(trade['profit']) > 0 else "❌"
            print(f"{status_emoji} ID:{trade['id']:3d} | {trade['open_time']} | {trade['direction']:4s} | Price:{trade['price']:.5f} | SL:{trade['sl']:.5f} | Profit:{trade['profit']:8.2f}")
    
    # Statystyka
    total_trades = len(df_all)
    wins = len(df_all[df_all['profit'].astype(float) > 0])
    losses = total_trades - wins
    total_profit = df_all['profit'].astype(float).sum()
    
    print(f"\n{'='*80}")
    print(f"STATYSTYKA GBPCHF (ostatnich {total_trades} transakcji):")
    print(f"  Wygrane: {wins} | Przegrane: {losses} | Win Rate: {wins/total_trades*100:.1f}%")
    print(f"  Łączny zysk/strata: {total_profit:.2f} pips")
    
    conn.close()
    
except Exception as e:
    print(f'Błąd: {e}')
