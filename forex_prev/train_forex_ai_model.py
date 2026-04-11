import pandas as pd
import numpy as np
import os
import joblib
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

# ========================
# PRZYGOTOWANIE DANYCH
# ========================
def prepare_dataset(symbol):
    filepath = os.path.join(DATA_DIR, f"{symbol}.csv")
    df = pd.read_csv(filepath)

    df.columns = [c.lower() for c in df.columns]
    df = extract_features_with_patterns(df)

    # Przykładowy target: 1 jeśli cena wzrosła w następnej świecy
    df['target'] = (df['close'].shift(-1) > df['close']).astype(int)

    df.dropna(inplace=True)

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

    model = XGBClassifier(n_estimators=100, max_depth=5, learning_rate=0.1, use_label_encoder=False, eval_metric='logloss')
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    print(classification_report(y_test, y_pred))

    joblib.dump(model, os.path.join(MODEL_DIR, f"{symbol}_model.pkl"))

# ========================
# GŁÓWNA PĘTLA
# ========================
if __name__ == "__main__":
    for symbol in SYMBOLS:
        try:
            train_model(symbol)
        except Exception as e:
            print(f"[ERROR] {symbol}: {e}")
