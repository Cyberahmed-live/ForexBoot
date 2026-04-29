import pyodbc
import pandas as pd

try:
    conn = pyodbc.connect('Driver={ODBC Driver 17 for SQL Server};Server=appdbpri;Database=ForexBotDB;Trusted_Connection=yes;')
    
    # Szukamy transakcji z order_id = 2997158
    query = '''
    SELECT 
        id, open_time, symbol, direction, price, sl, tp, lot, 
        prediction, status, order_id, confidence, atr, result, 
        profit, done, close_time, current_price, swap, duration_hours
    FROM trades 
    WHERE order_id = 2997158 OR id = 2997158
    ORDER BY open_time DESC
    '''
    
    df = pd.read_sql(query, conn)
    
    if len(df) > 0:
        for idx, row in df.iterrows():
            print('\n' + '='*70)
            print(f'ID: {row["id"]} | Order ID: {row["order_id"]}')
            print(f'Symbol: {row["symbol"]} | Direction: {row["direction"]}')
            print(f'Open Time: {row["open_time"]}')
            print(f'Entry Price: {row["price"]} | SL: {row["sl"]} | TP: {row["tp"]}')
            print(f'Lot: {row["lot"]} | ATR: {row["atr"]}')
            print(f'Prediction: {row["prediction"]} | Confidence: {row["confidence"]}')
            print(f'Result: {row["result"]} | Profit: {row["profit"]} pips')
            print(f'Current Price: {row["current_price"]} | Swap: {row["swap"]}')
            print(f'Duration: {row["duration_hours"]} hours')
            print(f'Status: {row["status"]} | Done: {row["done"]}')
            print(f'Close Time: {row["close_time"]}')
    else:
        print('Transakcja nie znaleziona!')
    
    conn.close()
except Exception as e:
    print(f'Błąd: {e}')
