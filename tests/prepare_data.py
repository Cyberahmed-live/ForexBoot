import MetaTrader5 as mt5
import pandas as pd
from ta import add_all_ta_features
from datetime import datetime
import joblib

SYMBOL = "EURUSD"
TIMEFRAME = mt5.TIMEFRAME_M15
N_CANDLES = 3000  # ilość świec do analizy
SHIFT = 1  # opóźnienie celu (np. 1 = 1 świeca naprzód)

def load_data():
    if not mt5.initialize():
        raise RuntimeError("❌ Nie udało się połączyć z MT5")

    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, N_CANDLES)
    mt5.shutdown()

    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    return df

def add_indicators(df):
    df = add_all_ta_features(df, open="open", high="high", low="low",
                             close="close", volume="tick_volume", fillna=True)
    return df

def add_target(df):
    df['future_close'] = df['close'].shift(-SHIFT)
    df['target'] = (df['future_close'] > df['close']).astype(int)
    df.dropna(inplace=True)
    return df

if __name__ == "__main__":
    df = load_data()
    df = add_indicators(df)
    df = add_target(df)

    FEATURES = [col for col in df.columns if col.startswith(('volume_', 'trend_', 'momentum_', 'volatility_'))]
    X = df[FEATURES]
    y = df['target']

    df.to_csv("forex_dataset.csv")
    print(f"✅ Dane zapisane — {X.shape[0]} próbki, {X.shape[1]} cech")

    # Zapisujemy dane do dalszego treningu
    joblib.dump((X, y), "forex_data.pkl")
    print("✅ Dane zapisane do forex_data.pkl")
# Dane zostały przygotowane i zapisane do pliku forex_data.pkl