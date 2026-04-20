# forex_v14/db_writer.py
"""
Warstwa dostępu do MS SQL Server dla Forex AI Bot.
Używa pyodbc z Windows Authentication (Trusted_Connection).
Wszystkie tabele: observations, trade_outcomes, formation_effectiveness,
trades, bot_status, bot_logs.
"""

import logging
import logging.handlers
import threading
from datetime import datetime, timedelta

import pyodbc

# ---------------------------------------------------------------------------
# Konfiguracja połączenia
# ---------------------------------------------------------------------------
_DEFAULT_CONN_STR = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=appdbpri;"
    "DATABASE=ForexBotDB;"
    "Trusted_Connection=yes;"
)


def _connect(conn_str=None):
    """Tworzy nowe połączenie do MS SQL."""
    return pyodbc.connect(conn_str or _DEFAULT_CONN_STR, timeout=10)


class MSSQLWriter:
    """Centralny writer do bazy ForexBotDB na MS SQL Server."""

    def __init__(self, conn_str=None):
        self._conn_str = conn_str or _DEFAULT_CONN_STR
        self._lock = threading.Lock()
        # Test połączenia przy starcie
        try:
            con = _connect(self._conn_str)
            con.close()
            logging.info("[MSSQLWriter] Połączenie z ForexBotDB OK.")
        except Exception as e:
            logging.error(f"[MSSQLWriter] Błąd połączenia z MS SQL: {e}")
            raise

    def _conn(self):
        return _connect(self._conn_str)

    # ------------------------------------------------------------------
    # OBSERVATIONS (Wisdom Aggregator)
    # ------------------------------------------------------------------
    def insert_observation(self, symbol, timeframe, candle_score, formation_type,
                           formation_score, macro_score, ml_prediction, ml_confidence,
                           ccs, atr, spread, ema_trend, rsi, adx, volume_ratio,
                           action_taken, price_at_obs):
        """Zapisuje obserwację rynkową."""
        now = datetime.now()
        sql = """
            INSERT INTO observations
                (timestamp, symbol, timeframe, candle_score, formation_type,
                 formation_score, macro_score, ml_prediction, ml_confidence, ccs,
                 atr, spread, ema_trend, rsi, adx, volume_ratio,
                 action_taken, price_at_obs)
            VALUES (?,?,?,?,?, ?,?,?,?,?, ?,?,?,?,?,?, ?,?)
        """
        params = (now, symbol, str(timeframe), candle_score, formation_type,
                  formation_score, macro_score, ml_prediction, ml_confidence, ccs,
                  atr, spread, ema_trend, rsi, adx, volume_ratio,
                  action_taken, price_at_obs)
        with self._lock:
            con = self._conn()
            try:
                con.execute(sql, params)
                con.commit()
            finally:
                con.close()

    def get_pending_outcomes(self, col, cutoff):
        """Pobiera obserwacje bez uzupełnionego outcome."""
        sql = f"""
            SELECT TOP 200 id, symbol, price_at_obs, timestamp
            FROM observations
            WHERE {col} IS NULL AND timestamp <= ?
        """
        con = self._conn()
        try:
            rows = con.execute(sql, (cutoff,)).fetchall()
            return [(r.id, r.symbol, r.price_at_obs, r.timestamp) for r in rows]
        finally:
            con.close()

    def update_outcome(self, obs_id, col, value):
        """Aktualizuje pojedynczą kolumnę outcome."""
        sql = f"UPDATE observations SET {col} = ? WHERE id = ?"
        with self._lock:
            con = self._conn()
            try:
                con.execute(sql, (value, obs_id))
                con.commit()
            finally:
                con.close()

    def update_max_favorable_adverse(self, obs_id, max_fav, max_adv):
        """Aktualizuje max_favorable i max_adverse."""
        sql = """
            UPDATE observations
            SET outcome_max_favorable = ?, outcome_max_adverse = ?
            WHERE id = ?
        """
        with self._lock:
            con = self._conn()
            try:
                con.execute(sql, (max_fav, max_adv, obs_id))
                con.commit()
            finally:
                con.close()

    def get_pending_max_favorable(self):
        """Pobiera obserwacje z outcome_24h ale bez max_favorable."""
        sql = """
            SELECT TOP 200 id, symbol, price_at_obs
            FROM observations
            WHERE outcome_24h IS NOT NULL AND outcome_max_favorable IS NULL
        """
        con = self._conn()
        try:
            rows = con.execute(sql).fetchall()
            return [(r.id, r.symbol, r.price_at_obs) for r in rows]
        finally:
            con.close()

    def count_observations(self):
        """Łączna liczba obserwacji."""
        con = self._conn()
        try:
            row = con.execute("SELECT COUNT(*) FROM observations").fetchone()
            return row[0] if row else 0
        finally:
            con.close()

    def get_observation_stats(self, symbol, days=7):
        """Statystyki obserwacji z ostatnich N dni."""
        cutoff = datetime.now() - timedelta(days=days)
        sql = """
            SELECT COUNT(*) as cnt,
                   AVG(candle_score) as avg_candle,
                   AVG(formation_score) as avg_form,
                   AVG(macro_score) as avg_macro,
                   AVG(ccs) as avg_ccs,
                   MAX(ccs) as max_ccs
            FROM observations
            WHERE symbol = ? AND timestamp >= ?
        """
        con = self._conn()
        try:
            row = con.execute(sql, (symbol, cutoff)).fetchone()
            if row and row.cnt:
                return {
                    "count": row.cnt, "avg_candle": row.avg_candle,
                    "avg_formation": row.avg_form, "avg_macro": row.avg_macro,
                    "avg_ccs": row.avg_ccs, "max_ccs": row.max_ccs
                }
            return None
        finally:
            con.close()

    # ------------------------------------------------------------------
    # TRADE OUTCOMES
    # ------------------------------------------------------------------
    def insert_trade_outcome(self, trade_id, symbol, direction,
                             entry_ccs=0.0, entry_candle_score=0.0,
                             entry_formation="none", entry_macro_score=0.0,
                             profit_pips=0.0, profit_money=0.0,
                             duration_hours=0.0, max_drawdown=0.0,
                             sl_hit=False, tp_hit=False):
        """Rejestruje wynik transakcji."""
        now = datetime.now()
        sql = """
            INSERT INTO trade_outcomes
                (trade_id, symbol, direction, entry_ccs, entry_candle_score,
                 entry_formation, entry_macro_score, profit_pips, profit_money,
                 duration_hours, max_drawdown, sl_hit, tp_hit, timestamp)
            VALUES (?,?,?,?,?, ?,?,?,?,?, ?,?,?,?)
        """
        params = (trade_id, symbol, direction, entry_ccs, entry_candle_score,
                  entry_formation, entry_macro_score, profit_pips, profit_money,
                  duration_hours, max_drawdown, int(sl_hit), int(tp_hit), now)
        with self._lock:
            con = self._conn()
            try:
                con.execute(sql, params)
                con.commit()
            finally:
                con.close()
        logging.info(f"[MSSQL] Trade outcome: {symbol} {direction} profit={profit_pips:.1f} pips")

    # ------------------------------------------------------------------
    # FORMATION EFFECTIVENESS
    # ------------------------------------------------------------------
    def aggregate_formation_effectiveness(self):
        """Przelicza win_rate i avg_move per symbol+formation."""
        sql_select = """
            SELECT symbol, formation_type, timeframe,
                   COUNT(*) as cnt,
                   AVG(CASE WHEN outcome_24h > 0 THEN 1.0 ELSE 0.0 END) as wr,
                   AVG(outcome_24h) as avg_mv
            FROM observations
            WHERE formation_type != 'none' AND outcome_24h IS NOT NULL
            GROUP BY symbol, formation_type, timeframe
            HAVING COUNT(*) >= 5
        """
        now = datetime.now()
        con = self._conn()
        try:
            rows = con.execute(sql_select).fetchall()
            for r in rows:
                # MERGE = upsert
                con.execute("""
                    MERGE formation_effectiveness AS tgt
                    USING (SELECT ? AS symbol, ? AS formation_type) AS src
                    ON tgt.symbol = src.symbol AND tgt.formation_type = src.formation_type
                    WHEN MATCHED THEN
                        UPDATE SET occurrences = ?, win_rate = ?, avg_move_pips = ?,
                                   best_timeframe = ?, last_updated = ?
                    WHEN NOT MATCHED THEN
                        INSERT (symbol, formation_type, occurrences, win_rate, avg_move_pips,
                                best_timeframe, last_updated)
                        VALUES (?, ?, ?, ?, ?, ?, ?);
                """, (r.symbol, r.formation_type,
                      r.cnt, round(r.wr, 4), round(r.avg_mv, 2), r.timeframe, now,
                      r.symbol, r.formation_type, r.cnt, round(r.wr, 4),
                      round(r.avg_mv, 2), r.timeframe, now))
            con.commit()
            logging.info(f"[MSSQL] Agregacja formacji: {len(rows)} rekordów.")
        finally:
            con.close()

    def get_formation_winrate(self, symbol, formation_type):
        """Zwraca win_rate formacji."""
        con = self._conn()
        try:
            row = con.execute("""
                SELECT win_rate, occurrences FROM formation_effectiveness
                WHERE symbol = ? AND formation_type = ?
            """, (symbol, formation_type)).fetchone()
            if row:
                return {"win_rate": row.win_rate, "occurrences": row.occurrences}
            return None
        finally:
            con.close()

    def get_best_formations(self, symbol, min_occurrences=10, min_winrate=0.55):
        """Formacje o najwyższej skuteczności."""
        con = self._conn()
        try:
            rows = con.execute("""
                SELECT formation_type, win_rate, avg_move_pips, occurrences
                FROM formation_effectiveness
                WHERE symbol = ? AND occurrences >= ? AND win_rate >= ?
                ORDER BY win_rate DESC
            """, (symbol, min_occurrences, min_winrate)).fetchall()
            return [{"formation": r.formation_type, "win_rate": r.win_rate,
                      "avg_move": r.avg_move_pips, "count": r.occurrences}
                    for r in rows]
        finally:
            con.close()

    # ------------------------------------------------------------------
    # TRADES (odpowiednik trades_log.csv)
    # ------------------------------------------------------------------
    def insert_trade(self, symbol, direction, price, sl, tp, lot,
                     prediction, status, order_id, confidence, atr,
                     result="S", profit=0.0, done="Nie"):
        """Loguje nową transakcję (odpowiednik log_trade z tran_logs.py)."""
        now = datetime.now()
        sql = """
            INSERT INTO trades
                (open_time, symbol, direction, price, sl, tp, lot,
                 prediction, status, order_id, confidence, atr,
                 result, profit, done)
            VALUES (?,?,?,?,?,?,?, ?,?,?,?,?, ?,?,?)
        """
        params = (now, symbol, direction[:10], price, sl, tp, lot,
                  str(prediction)[:50], str(status)[:30], order_id, confidence, atr,
                  str(result)[:5], profit, str(done)[:5])
        with self._lock:
            con = self._conn()
            try:
                con.execute(sql, params)
                con.commit()
            finally:
                con.close()

    def update_trade_status(self, order_id, profit=None, result=None,
                            done=None, close_time=None,
                            sl=None, tp=None, current_price=None,
                            swap=None, duration_hours=None):
        """Aktualizuje status transakcji (profit, Z/S, done, close_time, sl, tp, current_price, swap, duration)."""
        sets = []
        params = []
        if profit is not None:
            sets.append("profit = ?")
            params.append(profit)
        if result is not None:
            sets.append("result = ?")
            params.append(result)
        if done is not None:
            sets.append("done = ?")
            params.append(done)
        if close_time is not None:
            sets.append("close_time = ?")
            params.append(close_time)
        if sl is not None:
            sets.append("sl = ?")
            params.append(sl)
        if tp is not None:
            sets.append("tp = ?")
            params.append(tp)
        if current_price is not None:
            sets.append("current_price = ?")
            params.append(current_price)
        if swap is not None:
            sets.append("swap = ?")
            params.append(swap)
        if duration_hours is not None:
            sets.append("duration_hours = ?")
            params.append(duration_hours)
        if not sets:
            return
        params.append(order_id)
        sql = f"UPDATE trades SET {', '.join(sets)} WHERE order_id = ?"
        with self._lock:
            con = self._conn()
            try:
                con.execute(sql, params)
                con.commit()
            finally:
                con.close()

    def get_open_trades(self):
        """Pobiera otwarte transakcje."""
        con = self._conn()
        try:
            rows = con.execute(
                "SELECT * FROM trades WHERE done = 'Nie' ORDER BY open_time DESC"
            ).fetchall()
            return rows
        finally:
            con.close()

    # ------------------------------------------------------------------
    # BOT STATUS (heartbeat)
    # ------------------------------------------------------------------
    def write_heartbeat(self, status="RUNNING", mode="OBSERVER", version=None,
                        equity=None, balance=None, open_positions=0,
                        uptime_seconds=None, last_trade_time=None,
                        observations_count=0, message=None):
        """Zapisuje heartbeat bota."""
        sql = """
            INSERT INTO bot_status
                (timestamp, status, mode, version, equity, balance,
                 open_positions, uptime_seconds, last_trade_time,
                 observations_count, message)
            VALUES (GETDATE(),?,?,?,?,?, ?,?,?,?,?)
        """
        params = (status, mode, version, equity, balance,
                  open_positions, uptime_seconds, last_trade_time,
                  observations_count, message)
        with self._lock:
            con = self._conn()
            try:
                con.execute(sql, params)
                con.commit()
            finally:
                con.close()

    def get_last_heartbeat(self):
        """Pobiera ostatni heartbeat."""
        con = self._conn()
        try:
            row = con.execute(
                "SELECT TOP 1 * FROM bot_status ORDER BY timestamp DESC"
            ).fetchone()
            return row
        finally:
            con.close()

    # ------------------------------------------------------------------
    # BOT LOGS
    # ------------------------------------------------------------------
    def purge_old_logs(self, days=14):
        """Usuwa wpisy z bot_logs i bot_diagnostics starsze niż `days` dni."""
        sql_logs = "DELETE FROM bot_logs WHERE timestamp < DATEADD(day, ?, GETDATE())"
        sql_diag = "DELETE FROM bot_diagnostics WHERE timestamp < DATEADD(day, ?, GETDATE())"
        try:
            with self._lock:
                con = self._conn()
                try:
                    con.execute(sql_logs, (-days,))
                    con.execute(sql_diag, (-days,))
                    con.commit()
                finally:
                    con.close()
        except Exception as e:
            logging.error(f"[purge_old_logs] error: {e}")

    def insert_log(self, level, message, symbol=None):
        """Zapisuje wpis logu do bazy."""
        sql = """
            INSERT INTO bot_logs (timestamp, level, message, symbol)
            VALUES (GETDATE(), ?, ?, ?)
        """
        with self._lock:
            con = self._conn()
            try:
                con.execute(sql, (level, message[:2000], symbol))
                con.commit()
            finally:
                con.close()

    def get_recent_logs(self, limit=100, level=None):
        """Pobiera ostatnie logi."""
        con = self._conn()
        try:
            if level:
                rows = con.execute(
                    f"SELECT TOP {limit} * FROM bot_logs WHERE level = ? ORDER BY timestamp DESC",
                    (level,)
                ).fetchall()
            else:
                rows = con.execute(
                    f"SELECT TOP {limit} * FROM bot_logs ORDER BY timestamp DESC"
                ).fetchall()
            return rows
        finally:
            con.close()

    # ------------------------------------------------------------------
    # SYNCHRONIZACJA MT5 → DB (reconciliation)
    # ------------------------------------------------------------------
    def _order_exists(self, order_id):
        """Sprawdza czy order_id istnieje w tabeli trades."""
        con = self._conn()
        try:
            row = con.execute(
                "SELECT 1 FROM trades WHERE order_id = ?", (order_id,)
            ).fetchone()
            return row is not None
        finally:
            con.close()

    def _trade_outcome_exists(self, trade_id):
        """Sprawdza czy trade_id istnieje w tabeli trade_outcomes."""
        con = self._conn()
        try:
            row = con.execute(
                "SELECT 1 FROM trade_outcomes WHERE trade_id = ?", (trade_id,)
            ).fetchone()
            return row is not None
        finally:
            con.close()

    def sync_open_positions_from_mt5(self, positions):
        """Synchronizuje otwarte pozycje z MT5 do tabeli trades.
        positions: wynik mt5.positions_get()
        """
        if not positions:
            return 0
        synced = 0
        for pos in positions:
            if self._order_exists(pos.ticket):
                # Pozycja istnieje — aktualizuj bieżące dane
                try:
                    open_time_ts = datetime.fromtimestamp(pos.time)
                    duration_h = round((datetime.now() - open_time_ts).total_seconds() / 3600.0, 2)
                    self.update_trade_status(
                        order_id=pos.ticket,
                        profit=float(pos.profit),
                        result='Z' if pos.profit >= 0 else 'S',
                        done='Nie',
                        sl=float(pos.sl),
                        tp=float(pos.tp),
                        current_price=float(pos.price_current),
                        swap=float(pos.swap),
                        duration_hours=duration_h
                    )
                except Exception:
                    pass
                continue
            try:
                open_time = datetime.fromtimestamp(pos.time)
                direction = "BUY" if pos.type == 0 else "SELL"
                self.insert_trade(
                    symbol=pos.symbol,
                    direction=direction,
                    price=pos.price_open,
                    sl=pos.sl,
                    tp=pos.tp,
                    lot=pos.volume,
                    prediction="SYNC",
                    status="SYNCED",
                    order_id=pos.ticket,
                    confidence=0.0,
                    atr=0.0,
                    result='Z' if pos.profit >= 0 else 'S',
                    profit=pos.profit,
                    done='Nie'
                )
                synced += 1
                logging.info(f"[SYNC] Otwarta pozycja {pos.symbol} #{pos.ticket} zsynchronizowana do DB.")
            except Exception as e:
                logging.error(f"[SYNC] Błąd sync otwartej pozycji {pos.ticket}: {e}")
        return synced

    def sync_deals_from_mt5(self, deals):
        """Synchronizuje zamknięte deale z MT5 do tabel trades + trade_outcomes.
        deals: wynik mt5.history_deals_get()
        """
        if not deals:
            return 0
        synced = 0
        for deal in deals:
            try:
                # DEAL_ENTRY_IN = otwarcie pozycji
                if deal.entry == 0:  # DEAL_ENTRY_IN
                    if not self._order_exists(deal.order):
                        deal_time = datetime.fromtimestamp(deal.time)
                        direction = "BUY" if deal.type == 0 else "SELL"
                        self.insert_trade(
                            symbol=deal.symbol,
                            direction=direction,
                            price=deal.price,
                            sl=0.0,
                            tp=0.0,
                            lot=deal.volume,
                            prediction="SYNC",
                            status="SYNCED",
                            order_id=deal.order,
                            confidence=0.0,
                            atr=0.0,
                            result='S',
                            profit=0.0,
                            done='Nie'
                        )
                        synced += 1
                        logging.info(f"[SYNC] Deal IN {deal.symbol} #{deal.order} zsynchronizowany.")

                # DEAL_ENTRY_OUT = zamknięcie pozycji
                elif deal.entry == 1:  # DEAL_ENTRY_OUT
                    close_time = datetime.fromtimestamp(deal.time)
                    # Używamy deal.position_id (= ticket pozycji w DB),
                    # NIE deal.order (= numer zlecenia zamykającego)
                    self.update_trade_status(
                        order_id=deal.position_id,
                        profit=deal.profit,
                        result='Z' if deal.profit >= 0 else 'S',
                        done='Tak',
                        close_time=close_time
                    )
                    # Dodaj do trade_outcomes jeśli brak
                    if not self._trade_outcome_exists(deal.position_id):
                        direction = "SELL" if deal.type == 0 else "BUY"
                        self.insert_trade_outcome(
                            trade_id=deal.position_id,
                            symbol=deal.symbol,
                            direction=direction,
                            profit_money=float(deal.profit),
                        )
                        synced += 1
                        logging.info(f"[SYNC] Deal OUT {deal.symbol} #{deal.position_id} → trade_outcomes.")
            except Exception as e:
                logging.error(f"[SYNC] Błąd sync deala {deal.ticket}: {e}")
        return synced

    # ------------------------------------------------------------------
    # NPM: Negative Position Manager
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # BOT DIAGNOSTICS — strukturalne logowanie decyzji bota
    # ------------------------------------------------------------------

    def ensure_diagnostics_table(self):
        """Utwórz tabelę bot_diagnostics jeśli nie istnieje."""
        sql = """
        IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'bot_diagnostics')
        CREATE TABLE bot_diagnostics (
            id             BIGINT IDENTITY(1,1) PRIMARY KEY,
            timestamp      DATETIME2(3)     NOT NULL DEFAULT GETDATE(),
            symbol         NVARCHAR(20)     NULL,
            event_type     NVARCHAR(50)     NOT NULL,
            ml_decision    INT              NULL,
            ml_confidence  FLOAT            NULL,
            filter_blocked BIT              NOT NULL DEFAULT 0,
            filter_reason  NVARCHAR(200)    NULL,
            htf_w1         NVARCHAR(10)     NULL,
            htf_d1         NVARCHAR(10)     NULL,
            htf_aligned    BIT              NULL,
            atr            FLOAT            NULL,
            rr_ratio       FLOAT            NULL,
            npm_score      FLOAT            NULL,
            action_taken   NVARCHAR(50)     NULL,
            extra_json     NVARCHAR(MAX)    NULL
        )
        """
        try:
            with self._lock:
                con = self._conn()
                con.execute(sql)
                con.commit()
                con.close()
        except Exception as e:
            logging.error(f"[DiagLog] ensure_diagnostics_table error: {e}")

    def insert_diagnostic(self, event_type, symbol=None, ml_decision=None,
                          ml_confidence=None, filter_blocked=False,
                          filter_reason=None, htf_w1=None, htf_d1=None,
                          htf_aligned=None, atr=None, rr_ratio=None,
                          npm_score=None, action_taken=None, extra_json=None):
        """Zapisz zdarzenie diagnostyczne do bot_diagnostics."""
        sql = """
        INSERT INTO bot_diagnostics
            (timestamp, symbol, event_type, ml_decision, ml_confidence,
             filter_blocked, filter_reason, htf_w1, htf_d1, htf_aligned,
             atr, rr_ratio, npm_score, action_taken, extra_json)
        VALUES (GETDATE(), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        try:
            aligned_bit = None
            if htf_aligned is not None:
                aligned_bit = 1 if htf_aligned else 0
            params = (
                symbol, event_type,
                int(ml_decision) if ml_decision is not None else None,
                float(ml_confidence) if ml_confidence is not None else None,
                1 if filter_blocked else 0,
                filter_reason, htf_w1, htf_d1, aligned_bit,
                float(atr) if atr is not None else None,
                float(rr_ratio) if rr_ratio is not None else None,
                float(npm_score) if npm_score is not None else None,
                action_taken, extra_json
            )
            with self._lock:
                con = self._conn()
                try:
                    con.execute(sql, params)
                    con.commit()
                finally:
                    con.close()
        except Exception as e:
            logging.error(f"[DiagLog] insert_diagnostic error: {e}")

    def ensure_npm_table(self):
        """Utwórz tabelę negative_position_log jeśli nie istnieje."""
        sql = """
        IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'negative_position_log')
        CREATE TABLE negative_position_log (
            id              INT IDENTITY(1,1) PRIMARY KEY,
            timestamp       DATETIME2 DEFAULT GETDATE(),
            ticket          BIGINT NOT NULL,
            symbol          NVARCHAR(20),
            direction       NVARCHAR(10),
            npm_score       FLOAT,
            r_multiple      FLOAT,
            escalation      NVARCHAR(10),
            recovery_prob   FLOAT,
            action_taken    NVARCHAR(30),
            swap_cost_daily FLOAT,
            entry_price     FLOAT,
            current_price   FLOAT,
            duration_hours  FLOAT,
            profit          FLOAT,
            weekend_window  BIT DEFAULT 0
        )
        """
        try:
            with self._lock:
                con = self._conn()
                con.execute(sql)
                con.commit()
                con.close()
        except Exception as e:
            logging.error(f"[NPM] ensure_npm_table error: {e}")

    def insert_npm_log(self, ticket, symbol, direction, npm_score, r_multiple,
                       escalation, recovery_prob, action_taken, swap_cost_daily,
                       entry_price, current_price, duration_hours, profit,
                       weekend_window=False):
        """Zapisz wpis NPM do bazy."""
        sql = """
        INSERT INTO negative_position_log
            (ticket, symbol, direction, npm_score, r_multiple, escalation,
             recovery_prob, action_taken, swap_cost_daily, entry_price,
             current_price, duration_hours, profit, weekend_window)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        try:
            with self._lock:
                con = self._conn()
                con.execute(sql, ticket, symbol, direction, npm_score, r_multiple,
                            escalation, recovery_prob, action_taken, swap_cost_daily,
                            entry_price, current_price, duration_hours, profit,
                            1 if weekend_window else 0)
                con.commit()
                con.close()
        except Exception as e:
            logging.error(f"[NPM] insert_npm_log error: {e}")

    def get_recovery_stats(self, symbol, r_bucket_low, r_bucket_high, min_samples=5):
        """Oblicz recovery probability z trade_outcomes dla symbolu i zakresu R.

        Szuka zamkniętych transakcji na danym symbolu, gdzie initial drawdown
        (max_adverse / initial_risk) mieścił się w zakresie [r_bucket_low, r_bucket_high]
        i sprawdza ile z nich ostatecznie zakończyło się zyskiem.

        Returns: dict z recovery_pct, total_samples, avg_recovery_hours lub None.
        """
        sql = """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN profit_money > 0 THEN 1 ELSE 0 END) as recovered,
            AVG(CASE WHEN profit_money > 0 THEN duration_hours ELSE NULL END) as avg_recovery_h
        FROM trade_outcomes to2
        WHERE to2.symbol = ?
          AND to2.max_drawdown IS NOT NULL
        """
        try:
            with self._lock:
                con = self._conn()
                row = con.execute(sql, symbol).fetchone()
                con.close()
            if row is None or row.total < min_samples:
                return None
            return {
                'recovery_pct': (row.recovered / row.total * 100) if row.total > 0 else 0,
                'total_samples': row.total,
                'avg_recovery_hours': row.avg_recovery_h
            }
        except Exception as e:
            logging.error(f"[NPM] get_recovery_stats error: {e}")
            return None


# ---------------------------------------------------------------------------
# Logging handler — kieruje logi Pythona do tabeli bot_logs
# ---------------------------------------------------------------------------

class DBLogHandler(logging.Handler):
    """Przekierowuje wpisy logging do tabeli bot_logs w MS SQL."""

    def __init__(self, writer: MSSQLWriter, min_level=logging.WARNING):
        super().__init__(level=min_level)
        self._writer = writer

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            symbol = getattr(record, 'symbol', None)
            self._writer.insert_log(record.levelname, msg[:2000], symbol)
        except Exception:
            # Nigdy nie podnoś wyjątku z handlera logowania
            pass
