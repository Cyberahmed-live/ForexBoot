import pyodbc

conn = pyodbc.connect('DRIVER={ODBC Driver 17 for SQL Server};SERVER=appdbpri;DATABASE=ForexBotDB;Trusted_Connection=yes')
cur = conn.cursor()
tickets = [3146821, 3144165, 3145496, 3144696, 3144164]
placeholders = ','.join(['?' for _ in tickets])

cols_trades = ['id','open_time','symbol','direction','price','sl','tp','lot','prediction','status','order_id','confidence','atr','result','profit','done','close_time','current_price','swap','duration_hours']

cur.execute(f'SELECT * FROM trades WHERE order_id IN ({placeholders}) ORDER BY open_time', tickets)
rows = cur.fetchall()
print(f'=== TRADES ({len(rows)} rekordow) ===')
for r in rows:
    d = dict(zip(cols_trades, r))
    price = d['price'] or 0
    sl = d['sl'] or 0
    tp = d['tp'] or 0
    risk = abs(sl - price)
    reward = abs(tp - price)
    rr = round(reward / risk, 2) if risk > 0 else 'N/A'
    print(f"ticket/order_id={d['order_id']} | {d['symbol']} {d['direction']} | open={d['open_time']} close={d['close_time']}")
    print(f"  price={price} sl={sl} tp={tp} lot={d['lot']}")
    print(f"  profit={d['profit']} result={d['result']} status={d['status']} confidence={d['confidence']}")
    print(f"  atr={d['atr']} rr={rr} swap={d['swap']} duration_h={d['duration_hours']}")
    print()

# Sprawdz bot_diagnostics
cur.execute('SELECT TOP 1 * FROM bot_diagnostics WHERE 1=0')
dcols = [x[0] for x in cur.description]

print('=== BOT_DIAGNOSTICS (okolo open_time +/-30min) ===')
cur.execute(f'SELECT * FROM trades WHERE order_id IN ({placeholders}) ORDER BY open_time', tickets)
trade_rows = cur.fetchall()
for r in trade_rows:
    d = dict(zip(cols_trades, r))
    sym = d['symbol']
    ot = d['open_time']
    oid = d['order_id']
    cur2 = conn.cursor()
    cur2.execute(
        'SELECT TOP 5 * FROM bot_diagnostics WHERE symbol=? AND timestamp BETWEEN DATEADD(minute,-60,?) AND DATEADD(minute,60,?) ORDER BY timestamp',
        sym, ot, ot
    )
    diag_rows = cur2.fetchall()
    print(f'--- {sym} order_id={oid} open={ot} ---')
    for dr in diag_rows:
        dd = dict(zip(dcols, dr))
        print(f"  ts={dd.get('timestamp')} event={dd.get('event_type')} ml_dec={dd.get('ml_decision')} conf={dd.get('ml_confidence'):.3f}" if dd.get('ml_confidence') else f"  ts={dd.get('timestamp')} event={dd.get('event_type')} ml_dec={dd.get('ml_decision')} conf={dd.get('ml_confidence')}")
        print(f"  filter_blocked={dd.get('filter_blocked')} reason={dd.get('filter_reason')}")
        print(f"  htf_w1={dd.get('htf_w1')} htf_d1={dd.get('htf_d1')} aligned={dd.get('htf_aligned')} atr={dd.get('atr')} rr={dd.get('rr_ratio')} npm={dd.get('npm_score')}")
        print(f"  action={dd.get('action_taken')} extra={dd.get('extra_json')}")
    if not diag_rows:
        print('  (brak diagnostyk w bot_diagnostics)')
    print()

# Sprawdz tez trade_outcomes jesli istnieje
try:
    cur.execute(f'SELECT * FROM trade_outcomes WHERE order_id IN ({placeholders})', tickets)
    tocols = [x[0] for x in cur.description]
    to_rows = cur.fetchall()
    if to_rows:
        print('=== TRADE_OUTCOMES ===')
        for r in to_rows:
            print(dict(zip(tocols, r)))
except Exception as e:
    print(f'trade_outcomes: {e}')

# Sprawdz negative_position_log
try:
    cur.execute(f'SELECT * FROM negative_position_log WHERE order_id IN ({placeholders})', tickets)
    npcols = [x[0] for x in cur.description]
    np_rows = cur.fetchall()
    if np_rows:
        print('=== NEGATIVE_POSITION_LOG ===')
        for r in np_rows:
            print(dict(zip(npcols, r)))
except Exception as e:
    print(f'negative_position_log: {e}')

conn.close()
