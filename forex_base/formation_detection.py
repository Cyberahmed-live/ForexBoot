import pandas as pd
import talib

def detect_candle_formations(df):
    df = df.copy()

    # Upewnij się, że są wystarczające dane
    if df is None or df.empty or len(df) < 5:
        return df

    required_cols = ['open', 'high', 'low', 'close']
    if not all(col in df.columns for col in required_cols):
        raise ValueError(f"DataFrame must contain columns: {required_cols}")

    try:
        # Formacje świecowe TA-Lib
        df['CDL_HAMMER'] = talib.CDLHAMMER(df['open'], df['high'], df['low'], df['close'])
        df['CDL_SHOOTING_STAR'] = talib.CDLSHOOTINGSTAR(df['open'], df['high'], df['low'], df['close'])
        df['CDL_DOJI'] = talib.CDLDOJI(df['open'], df['high'], df['low'], df['close'])
        df['CDL_ENGULFING'] = talib.CDLENGULFING(df['open'], df['high'], df['low'], df['close'])
        df['CDL_MORNING_STAR'] = talib.CDLMORNINGSTAR(df['open'], df['high'], df['low'], df['close'])
        df['CDL_EVENING_STAR'] = talib.CDLEVENINGSTAR(df['open'], df['high'], df['low'], df['close'])
        df['CDL_HARAMI'] = talib.CDLHARAMI(df['open'], df['high'], df['low'], df['close'])
        df['CDL_PIERCING'] = talib.CDLPIERCING(df['open'], df['high'], df['low'], df['close'])
        df['CDL_DARK_CLOUD_COVER'] = talib.CDLDARKCLOUDCOVER(df['open'], df['high'], df['low'], df['close'])

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

        # Zamiana wartości formacji na 0/1
        for col in df.columns:
            if col.startswith("CDL_") or "PATTERN_" in col or col == "INSIDE_BAR" or col == "CORRECTION_5":
                df[col] = df[col].astype(int).apply(lambda x: 1 if x != 0 else 0)

    except Exception as e:
        print(f"[Formation Detection Error] {str(e)}")

    return df
