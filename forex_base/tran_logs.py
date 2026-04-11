
from datetime import datetime
import logging
from forex_base.globalcfg           import get_global_cfg

# MS SQL writer (ustawiany z zewnątrz)
_mssql_writer = None

def set_mssql_writer(writer):
    """Ustawia MSSQLWriter do zapisu transakcji do bazy MS SQL."""
    global _mssql_writer
    _mssql_writer = writer


def log_trade(symbol, direction, price, sl, tp, volume, prediction, retcode, result, confidence, ud, done, atr, profit):
    if _mssql_writer is None:
        logging.error("[tran_logs] MSSQLWriter nie ustawiony — transakcja nie zapisana!")
        return

    try:
        _mssql_writer.insert_trade(
            symbol=symbol,
            direction="BUY" if direction == 1 else "SELL",
            price=price, sl=sl, tp=tp, lot=volume,
            prediction=str(prediction), status=str(retcode),
            order_id=result if isinstance(result, int) else 0,
            confidence=confidence, atr=atr,
            result=ud, profit=profit, done=done
        )
    except Exception as e:
        logging.error(f"[MSSQL] Błąd zapisu transakcji: {e}")