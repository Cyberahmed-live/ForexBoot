# forex_base/train_forex_ai_model_v1.2.py
import logging
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import os
import joblib
import matplotlib.pyplot as plt
import time
import json
from datetime import datetime
from xgboost import XGBClassifier
from sklearn.metrics import classification_report
from sklearn.preprocessing import StandardScaler
from forex_base.globalcfg import get_global_cfg


# --- Ustawienia ---
symbols = get_global_cfg("symbols")
timeframe = get_global_cfg("timeframe")
bars = get_global_cfg("bars")
output_dir = get_global_cfg("output_dir")
model_dir = get_global_cfg("model_path")
TRAIN_TIMES_FILE = os.path.join(model_dir, "model_train_times.json")
LOG_FILE = get_global_cfg("log_file")

os.makedirs(output_dir, exist_ok=True)
os.makedirs(model_dir, exist_ok=True)

def set_logging():
    # Konfiguracja logowania
    logging.basicConfig(
        filename=LOG_FILE,  # Pobierz ścieżkę do pliku loga
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        encoding='utf-8'
    )
    # logging.info("Logging initialized.")

# --- Jeśli chcesz pobrać wszystkie dostępne świece, możesz użyć pętli i łączyć wyniki ---
def fetch_all_bars(symbol, timeframe, chunk_size=10000):
    all_rates = []
    pos = 0
    while True:
        rates = mt5.copy_rates_from_pos(symbol, timeframe, pos, chunk_size)
        if rates is None or len(rates) == 0:
            break
        all_rates.append(rates)
        if len(rates) < chunk_size:
            break
        pos += chunk_size
    if all_rates:
        return np.concatenate(all_rates)
    return None

# --- Funkcja pobierająca dane z MT5 i zapisująca do CSV ---
def fetch_and_save_data(symbol):
    if not mt5.initialize():
        logging.error(f"❌[ERROR] Nie udało się połączyć z MetaTrader 5: {mt5.last_error()}")
        return False
    rates = fetch_all_bars(symbol, timeframe)
    if rates is None or len(rates) == 0:
        logging.warning(f"⚠️[WARNING] Brak danych dla {symbol}, pomiń")
        mt5.shutdown()
        return False
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    file_path = os.path.join(output_dir, f"{symbol}.csv")
    df.to_csv(file_path, index=False)
    logging.info(f"ℹ️[OK] Zapisano do: {file_path}")
    mt5.shutdown()
    return True

def update_all_data():
    for symbol in symbols:
        logging.info(f"ℹ️[INFO] Eksport danych dla: {symbol}")
        fetch_and_save_data(symbol)
    logging.info("ℹ️[DONE] Zakończono eksport danych.")

# --- Feature engineering ---
def extract_features_with_patterns(df):
    import talib
    df = df.copy()
    df['CDL_HAMMER'] = talib.CDLHAMMER(df['open'], df['high'], df['low'], df['close'])
    df['CDL_SHOOTING_STAR'] = talib.CDLSHOOTINGSTAR(df['open'], df['high'], df['low'], df['close'])
    df['CDL_DOJI'] = talib.CDLDOJI(df['open'], df['high'], df['low'], df['close'])
    df['CDL_ENGULFING'] = talib.CDLENGULFING(df['open'], df['high'], df['low'], df['close'])
    df['INSIDE_BAR'] = (df['high'] < df['high'].shift(1)) & (df['low'] > df['low'].shift(1))
    df['PATTERN_W'] = ((df['low'].shift(2) > df['low'].shift(1)) &
                       (df['low'] < df['low'].shift(1)) &
                       (df['low'] < df['low'].shift(2)))
    df['PATTERN_M'] = ((df['high'].shift(2) < df['high'].shift(1)) &
                       (df['high'] > df['high'].shift(1)) &
                       (df['high'] > df['high'].shift(2)))
    df['PATTERN_HS'] = ((df['high'].shift(3) < df['high'].shift(2)) &
                        (df['high'].shift(1) < df['high'].shift(2)))
    df['PATTERN_IHS'] = ((df['low'].shift(3) > df['low'].shift(2)) &
                         (df['low'].shift(1) > df['low'].shift(2)))
    df['CORRECTION_5'] = (
        (df['close'] > df['close'].rolling(5).mean()) &
        (df['close'].shift(1) < df['close'].shift(2)) &
        (df['close'].shift(2) < df['close'].shift(3)) &
        (df['close'] > df['close'].shift(1))
    )
    for col in df.columns:
        if col.startswith("CDL_") or "PATTERN_" in col or col == "INSIDE_BAR" or col == "CORRECTION_5":
            df[col] = df[col].astype(int).apply(lambda x: 1 if x != 0 else 0)
    return df

def add_indicators(df):
    import talib
    df['ema20'] = talib.EMA(df['close'], timeperiod=20)
    df['ema50'] = talib.EMA(df['close'], timeperiod=50)
    df['ema100'] = talib.EMA(df['close'], timeperiod=100)
    df['ema200'] = talib.EMA(df['close'], timeperiod=200)
    df['rsi'] = talib.RSI(df['close'], timeperiod=14)
    df['macd'], df['macd_signal'], _ = talib.MACD(df['close'])
    df['atr'] = talib.ATR(df['high'], df['low'], df['close'], timeperiod=14)
    df['bb_upper'], df['bb_middle'], df['bb_lower'] = talib.BBANDS(df['close'])
    df['adx'] = talib.ADX(df['high'], df['low'], df['close'])
    df['cci'] = talib.CCI(df['high'], df['low'], df['close'])
    df['roc'] = talib.ROC(df['close'])
    df['stoch_k'], df['stoch_d'] = talib.STOCH(df['high'], df['low'], df['close'])
    df['willr'] = talib.WILLR(df['high'], df['low'], df['close'])
    df['candle_size'] = df['high'] - df['low']
    df['upper_shadow'] = df['high'] - df[['close', 'open']].max(axis=1)
    df['lower_shadow'] = df[['close', 'open']].min(axis=1) - df['low']
    df['ema_trend'] = (df['ema50'] > df['ema200']).astype(int)
    df['rsi_overbought'] = (df['rsi'] > 70).astype(int)
    df['rsi_oversold'] = (df['rsi'] < 30).astype(int)
    df['price_above_ema'] = (df['close'] > df['ema50']).astype(int)
    return df

def should_retrain(model_path, data_path, retrain_interval_hours=24):
    if not os.path.exists(model_path):
        return True
    if not os.path.exists(data_path):
        return True  # Brak danych CSV → pobierz i trenuj
    model_time = os.path.getmtime(model_path)
    data_time = os.path.getmtime(data_path)
    now = time.time()
    if data_time > model_time or (now - model_time) > retrain_interval_hours * 3600:
        return True
    return False

def prepare_dataset(symbol):
    filepath = os.path.join(output_dir, f"{symbol}.csv")
    df = pd.read_csv(filepath)
    df.columns = [c.lower() for c in df.columns]

    # return = zmiana poprzedniej swiacy (shift +1 = bez data leakage)
    df['return'] = df['close'].pct_change().shift(1).fillna(0)

    df = extract_features_with_patterns(df)
    df = add_indicators(df)

    # target = kierunek NASTEPNEJ swiecy (to chcemy przewidziec)
    next_return = df['close'].pct_change().shift(-1)

    # Próg uwzględnia ATR jako proxy spreadu — eliminuje sygnały bliskie granicy
    atr_median = float(df['atr'].median()) if 'atr' in df.columns and df['atr'].notna().any() else 0.0
    threshold = max(0.0003, min(atr_median * 0.03, 0.0020))

    df['target'] = np.where(next_return > threshold, 1, np.where(next_return < -threshold, 0, np.nan))
    df['_next_return'] = next_return  # zachowaj do wag
    df.dropna(inplace=True)

    # sample_weight: duże ruchy ważniejsze niż szum; normalizuj do ATR aby porówn. symbole
    weight_raw = np.abs(df['_next_return']) / df['atr'].clip(lower=1e-8)
    weight_raw = weight_raw.clip(upper=5.0)  # odetnij outliers
    sample_weight = (weight_raw / weight_raw.mean()).values

    X = df.drop(['target', '_next_return', 'time'], axis=1, errors='ignore')
    y = df['target']
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    joblib.dump(X.columns.tolist(), os.path.join(model_dir, f"{symbol}_feature_columns.pkl"))
    joblib.dump(scaler, os.path.join(model_dir, f"{symbol}_scaler.pkl"))
    return X_scaled, y, sample_weight

def train_model(symbol):
    logging.info(f"ℹ️[INFO] Trening modelu dla: {symbol}")
    X, y, sample_weight = prepare_dataset(symbol)
    # Chronologiczny podział — ostatnie 20% jako test (bez mieszania danych)
    split_idx = int(len(X) * 0.8)
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
    sw_train = sample_weight[:split_idx]
    # Balans klas — zapobiega bias SELL lub BUY
    sell_count = int((y_train == 0).sum())
    buy_count  = int((y_train == 1).sum())
    scale_pos_weight = sell_count / buy_count if buy_count > 0 else 1.0
    logging.info(f"ℹ️[TRAIN] {symbol}: BUY={buy_count}, SELL={sell_count}, scale_pos_weight={scale_pos_weight:.2f}")

    model = XGBClassifier(
        n_estimators=500,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=scale_pos_weight,
        eval_metric='error',
        early_stopping_rounds=30,
    )
    model.fit(X_train, y_train, sample_weight=sw_train,
              eval_set=[(X_test, y_test)], verbose=False)
    logging.info(f"ℹ️[TRAIN] {symbol}: najlepsze drzewo = {model.best_iteration} / max 500")
    y_pred = model.predict(X_test)
    # print(classification_report(y_test, y_pred))
    joblib.dump(model, os.path.join(model_dir, f"{symbol}_model.pkl"))
    importances = model.feature_importances_
    columns = joblib.load(os.path.join(model_dir, f"{symbol}_feature_columns.pkl"))
    importance_df = pd.DataFrame({'feature': columns, 'importance': importances})
    importance_df.sort_values(by='importance', ascending=False, inplace=True)
    importance_df.to_csv(os.path.join(model_dir, f"{symbol}_feature_importance.csv"), index=False)
    importance_df.head(20).plot(kind='barh', x='feature', y='importance', figsize=(10, 6), title=f"{symbol} - Feature Importance")
    plt.gca().invert_yaxis()
    plt.tight_layout()
    plt.savefig(os.path.join(model_dir, f"{symbol}_feature_importance.png"))
    plt.close()

def load_train_times():
    if os.path.exists(TRAIN_TIMES_FILE):
        with open(TRAIN_TIMES_FILE, "r") as f:
            return json.load(f)
    return {}

def save_train_times(train_times):
    with open(TRAIN_TIMES_FILE, "w") as f:
        json.dump(train_times, f)

def update_train_time(symbol):
    train_times = load_train_times()
    train_times[symbol] = datetime.now().isoformat()
    save_train_times(train_times)

def get_last_train_time(symbol):
    train_times = load_train_times()
    return train_times.get(symbol, None)

def get_recent_win_rate(symbol, last_n=20):
    """Pobierz win_rate z ostatnich N zamkniętych transakcji dla symbolu.

    Łączy się z ForexBotDB przez pyodbc. Zwraca float [0.0–1.0] lub None.
    """
    try:
        import pyodbc
        conn_str = (
            "DRIVER={ODBC Driver 17 for SQL Server};"
            "SERVER=localhost;"
            "DATABASE=ForexBotDB;"
            "Trusted_Connection=yes;"
        )
        sql = """
        SELECT TOP (?) profit_money
        FROM trade_outcomes
        WHERE symbol = ?
        ORDER BY timestamp DESC
        """
        con = pyodbc.connect(conn_str, timeout=5)
        rows = con.execute(sql, last_n, symbol).fetchall()
        con.close()
        if not rows or len(rows) < 5:
            return None  # za mało próbek
        wins = sum(1 for r in rows if r.profit_money is not None and r.profit_money > 0)
        return wins / len(rows)
    except Exception as e:
        logging.warning(f"⚠️[TRAIN] get_recent_win_rate({symbol}) error: {e}")
        return None


# --- Główna pętla ---
# Uruchamiamy process trenowania
def run():
    set_logging()  # Inicjalizacja logowania
    logging.info(f"ℹ️ Uruchamiamy process trenowania, ver: train_forex_ai_model_v1_2")

    # Sprawdz flage wymuszonych retrenów z DB (retrain_symbols w bot_config)
    forced_retrain_set = set()
    try:
        from forex_v14.db_writer import MSSQLWriter as _MW
        forced_retrain_set = set(_MW().pop_retrain_symbols())
        if forced_retrain_set:
            logging.info(f"[TRAIN] Wymuszony retrain z DB dla: {forced_retrain_set}")
    except Exception as _fre:
        logging.warning(f"[TRAIN] Nie mozna pobrac forced_retrain z DB: {_fre}")

    # Dodaj ewentualnie brakujace symbole z flagi (spoza aktualnej listy)
    all_symbols = list(symbols) + [s for s in forced_retrain_set if s not in symbols]

    for symbol in all_symbols:
        try:
            data_file = os.path.join(output_dir, f"{symbol}.csv")
            model_file = os.path.join(model_dir, f"{symbol}_model.pkl")
            last_train = get_last_train_time(symbol)
            retrain = False
            if symbol in forced_retrain_set:
                retrain = True  # Wymuszony retrain z DB
                logging.info(f"⚡[TRAIN] {symbol}: wymuszony retrain z flagi DB")
            elif last_train:
                last_train_dt = datetime.fromisoformat(last_train)
                hours_since = (datetime.now() - last_train_dt).total_seconds() / 3600
                if hours_since >= 24:
                    retrain = True
            else:
                retrain = True  # Nigdy nie trenowano

            if retrain and (symbol in forced_retrain_set or should_retrain(model_file, data_file, retrain_interval_hours=24)):
                logging.info(f"ℹ️[INFO] Pobieranie danych i trening modelu dla {symbol} (nowe dane lub minęło >=24h)")
                fetch_and_save_data(symbol)  # Pobierz dane tylko jeśli trzeba trenować
                train_model(symbol)
                update_train_time(symbol)
            else:
                # ⚡ Profit-aware check: zły wynik → wymuś retrain nawet przed 24h
                if not retrain:
                    win_rate = get_recent_win_rate(symbol)
                    if win_rate is not None and win_rate < 0.35:
                        logging.info(
                            f"⚠️[TRAIN] {symbol}: win_rate={win_rate:.1%} <35% w ostatnich transakcjach "
                            f"— wymuszam wcześniejszy retrain."
                        )
                        fetch_and_save_data(symbol)
                        train_model(symbol)
                        update_train_time(symbol)
            last_train = get_last_train_time(symbol)
            # if last_train:
            #     logging.info(f"ℹ️[INFO] Ostatni trening {symbol}: {last_train}")
        except Exception as e:
            logging.error(f"❌[ERROR] {symbol}: {e}")

if __name__ == "__main__":
    run()