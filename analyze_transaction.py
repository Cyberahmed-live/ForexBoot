import pyodbc
import pandas as pd
from datetime import datetime, timedelta

try:
    conn = pyodbc.connect('Driver={ODBC Driver 17 for SQL Server};Server=appdbpri;Database=ForexBotDB;Trusted_Connection=yes;')
    
    # Pobierz szczegóły transakcji
    trade_query = '''
    SELECT 
        id, open_time, symbol, direction, price, sl, tp, lot, 
        prediction, status, order_id, confidence, atr, result, 
        profit, done, close_time, current_price, swap, duration_hours
    FROM trades 
    WHERE order_id = 2997158
    '''
    
    df_trade = pd.read_sql(trade_query, conn)
    
    if len(df_trade) > 0:
        trade = df_trade.iloc[0]
        
        print("\n" + "="*80)
        print("ANALIZA TRANSAKCJI 2997158 - DUŻA STRATA")
        print("="*80)
        
        trade_open = trade['open_time']
        trade_close = trade['close_time']
        
        print("\n📊 PARAMETRY TRANSAKCJI:")
        print(f"  Symbol:        {trade['symbol']} ({trade['direction']})")
        print(f"  Open Time:     {trade_open}")
        print(f"  Close Time:    {trade_close}")
        print(f"  Duration:      {trade['duration_hours']:.2f} h")
        
        print("\n💰 CENOWE:")
        entry_price = float(trade['price'])
        sl_price = float(trade['sl'])
        tp_price = float(trade['tp'])
        current = float(trade['current_price'])
        
        print(f"  Entry Price:   {entry_price}")
        print(f"  Stop Loss:     {sl_price}")
        print(f"  Take Profit:   {tp_price}")
        print(f"  Current:       {current}")
        
        # Oblicz R i Risk/Reward
        risk_pips = abs(sl_price - entry_price) / 0.00001  # dla GBPCHF
        profit_pips = abs(entry_price - tp_price) / 0.00001
        rr_ratio = profit_pips / risk_pips if risk_pips > 0 else 0
        
        print(f"\n⚖️  RISK MANAGEMENT:")
        print(f"  Risk (SL):     {risk_pips:.1f} pips")
        print(f"  Target (TP):   {profit_pips:.1f} pips")
        print(f"  R:R Ratio:     1:{rr_ratio:.2f}")
        
        print(f"\n❌ WYNIK:")
        profit = float(trade['profit'])
        print(f"  Profit/Loss:   {profit:.2f} pips")
        print(f"  Lot Size:      {trade['lot']}")
        print(f"  Swap:          {trade['swap']}")
        print(f"  Status:        {trade['result']} (Strata)")
        print(f"  AI Confidence: {trade['confidence']*100:.2f}%")
        
        # Czemu tak duża strata?
        actual_loss_pips = profit
        expected_max_loss = -risk_pips * (float(trade['lot']) / 0.1)  # przybliżenie
        
        print(f"\n🔍 ANALIZA PROBLEMU:")
        print(f"  Oczekiwana max strata:  ~{risk_pips:.1f} pips (na minimalnym locie)")
        print(f"  Rzeczywista strata:     {actual_loss_pips:.1f} pips")
        print(f"  Lot size:               {trade['lot']} (duży lot!)")
        
        # Czy to był trailing SL?
        if trade['current_price'] < sl_price:
            print(f"\n  ⚠️  Current price ({current}) jest PONIŻEJ SL ({sl_price})")
            print(f"     Sugeruje to że SL został przesunięty lub zmieniony!")
        
        # Pobierz obserwacje wokół czasu transakcji
        obs_query = f'''
        SELECT TOP 30
            timestamp, candle_score, formation_type, formation_score,
            macro_score, ml_prediction, ml_confidence, ccs, atr, rsi, adx, ema_trend,
            price_at_obs
        FROM observations
        WHERE symbol = 'GBPCHF' 
        AND timestamp BETWEEN '{trade_open}' AND '{trade_close}'
        ORDER BY timestamp DESC
        '''
        
        df_obs = pd.read_sql(obs_query, conn)
        
        if len(df_obs) > 0:
            print("\n" + "="*80)
            print(f"OBSERWACJE RYNKOWE GBPCHF ({len(df_obs)} obserwacji)")
            print("="*80)
            for idx, obs in df_obs.iterrows():
                print(f"\n[{obs['timestamp']}]")
                print(f"  Form: {obs['formation_type']:12s} ({obs['formation_score']:.2f})")
                print(f"  ML: {obs['ml_prediction']:1.0f} ({obs['ml_confidence']:.2f}) | CCS: {obs['ccs']:.2f}")
                print(f"  ATR: {obs['atr']:.6f} | RSI: {obs['rsi']:.1f} | ADX: {obs['adx']:.1f} | Trend: {obs['ema_trend']}")
                print(f"  Price: {obs['price_at_obs']:.5f}")
    
    conn.close()
    
except Exception as e:
    print(f'Błąd: {e}')
