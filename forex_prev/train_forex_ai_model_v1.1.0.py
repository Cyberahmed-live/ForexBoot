import pandas as pd
import numpy as np
import os
import joblib
import matplotlib.pyplot as plt
import time
from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
from sklearn.preprocessing import StandardScaler
from forex_base.globalcfg import get_global_cfg
# ======= =================
# KONFIGURACJA
# ========================
SYMBOLS = get_global_cfg("symbols")         # Pobierz listę symboli z konfiguracji
DATA_DIR = get_global_cfg("output_dir")     # Folder z plikami CSV np. forex_data/EURUSD.csv
MODEL_DIR = get_global_cfg("model_path")    # Folder do zapisywania modeli np. forex_models
os.makedirs(MODEL_DIR, exist_ok=True)

# ========================
# EKSTRAKCJA FORMACJI ŚWIECOWYCH
# ========================
def extract_features_with_patterns(df):
    import talib
    df = df.copy()

    # Formacje świecowe TA-Lib (zwrotne)
    df['CDL_HAMMER'] = talib.CDLHAMMER(df['open'], df['high'], df['low'], df['close'])
    df['CDL_SHOOTING_STAR'] = talib.CDLSHOOTINGSTAR(df['open'], df['high'], df['low'], df['close'])
    df['CDL_DOJI'] = talib.CDLDOJI(df['open'], df['high'], df['low'], df['close'])
    df['CDL_ENGULFING'] = talib.CDLENGULFING(df['open'], df['high'], df['low'], df['close'])

    # Inside bar
    df['INSIDE_BAR'] = (df['high'] < df['high'].shift(1)) & (df['low'] > df['low'].shift(1))

    # W (double bottom)
    df['PATTERN_W'] = ((df['low'].shift(2) > df['low'].shift(1)) &
                       (df['low'] < df['low'].shift(1)) &
                       (df['low'] < df['low'].shift(2)))

    # M (double top)
    df['PATTERN_M'] = ((df['high'].shift(2) < df['high'].shift(1)) &
                       (df['high'] > df['high'].shift(1)) &
                       (df['high'] > df['high'].shift(2)))

    # Głowa z ramionami
    df['PATTERN_HS'] = ((df['high'].shift(3) < df['high'].shift(2)) &
                        (df['high'].shift(1) < df['high'].shift(2)))

    # Odwrócona głowa z ramionami
    df['PATTERN_IHS'] = ((df['low'].shift(3) > df['low'].shift(2)) &
                         (df['low'].shift(1) > df['low'].shift(2)))

    # 5 korekt – uproszczona logika
    df['CORRECTION_5'] = (
        (df['close'] > df['close'].rolling(5).mean()) &
        (df['close'].shift(1) < df['close'].shift(2)) &
        (df['close'].shift(2) < df['close'].shift(3)) &
        (df['close'] > df['close'].shift(1))
    )

    # Zamiana na 0/1
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
    # Price action
    df['candle_size'] = df['high'] - df['low']
    df['upper_shadow'] = df['high'] - df[['close', 'open']].max(axis=1)
    df['lower_shadow'] = df[['close', 'open']].min(axis=1) - df['low']
    # Sygnały binarne
    df['ema_trend'] = (df['ema50'] > df['ema200']).astype(int)
    df['rsi_overbought'] = (df['rsi'] > 70).astype(int)
    df['rsi_oversold'] = (df['rsi'] < 30).astype(int)
    df['price_above_ema'] = (df['close'] > df['ema50']).astype(int)
    return df

def should_retrain(model_path, data_path, retrain_interval_hours=24):
    # Sprawdź czas ostatniego treningu i ostatniej modyfikacji danych
    if not os.path.exists(model_path):
        return True
    model_time = os.path.getmtime(model_path)
    data_time = os.path.getmtime(data_path)
    now = time.time()
    # Jeśli dane są nowsze niż model lub minął interwał
    if data_time > model_time or (now - model_time) > retrain_interval_hours * 3600:
        return True
    return False

# ========================
# PRZYGOTOWANIE DANYCH
# ========================
def prepare_dataset(symbol):
    filepath = os.path.join(DATA_DIR, f"{symbol}.csv")
    df = pd.read_csv(filepath)

    df.columns = [c.lower() for c in df.columns]
    df = extract_features_with_patterns(df)

    # Lepszy target (zmiana procentowa, z progiem)
    df['target'] = np.where(df['return'] > 0.0005, 1, np.where(df['return'] < -0.0005, 0, np.nan))

    df.dropna(inplace=True)

    # Dodanie wskaźników
    df = add_indicators(df)

    X = df.drop(['target', 'time'], axis=1, errors='ignore')
    y = df['target']

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Zapis kolumn cech i skalera
    joblib.dump(X.columns.tolist(), os.path.join(MODEL_DIR, f"{symbol}_feature_columns.pkl"))
    joblib.dump(scaler, os.path.join(MODEL_DIR, f"{symbol}_scaler.pkl"))

    return X_scaled, y

# ========================
# TRENING MODELU
# ========================
def train_model(symbol):
    print(f"[INFO] Trening modelu dla: {symbol}")
    X, y = prepare_dataset(symbol)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = XGBClassifier(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric='logloss',
        use_label_encoder=False
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    print(classification_report(y_test, y_pred))

    joblib.dump(model, os.path.join(MODEL_DIR, f"{symbol}_model.pkl"))

    # Zapisz model
    importances = model.feature_importances_
    columns = joblib.load(os.path.join(MODEL_DIR, f"{symbol}_feature_columns.pkl"))

    importance_df = pd.DataFrame({'feature': columns, 'importance': importances})
    importance_df.sort_values(by='importance', ascending=False, inplace=True)
    importance_df.to_csv(os.path.join(MODEL_DIR, f"{symbol}_feature_importance.csv"), index=False)

    # opcjonalnie wykres
    importance_df.head(20).plot(kind='barh', x='feature', y='importance', figsize=(10, 6), title=f"{symbol} - Feature Importance")
    plt.gca().invert_yaxis()
    plt.tight_layout()
    plt.savefig(os.path.join(MODEL_DIR, f"{symbol}_feature_importance.png"))
    plt.close()

# ========================
# GŁÓWNA PĘTLA
# ========================
if __name__ == "__main__":
    for symbol in SYMBOLS:
        try:
            data_file = os.path.join(DATA_DIR, f"{symbol}.csv")
            model_file = os.path.join(MODEL_DIR, f"{symbol}_model.pkl")
            if should_retrain(model_file, data_file, retrain_interval_hours=24):
                print(f"[INFO] Trening modelu dla {symbol} (nowe dane lub minął czas)")
                train_model(symbol)
            else:
                print(f"[INFO] Model dla {symbol} aktualny, pomijam trening.")
        except Exception as e:
            print(f"[ERROR] {symbol}: {e}")
