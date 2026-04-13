# indicators.py
import pandas as pd
import talib

def generate_features(df):
    # --- EMA ---
    df['ema20']  = talib.EMA(df['close'], timeperiod=20)
    df['ema50']  = talib.EMA(df['close'], timeperiod=50)
    df['ema100'] = talib.EMA(df['close'], timeperiod=100)
    df['ema200'] = talib.EMA(df['close'], timeperiod=200)

    # --- RSI i progi ---
    df['rsi']          = talib.RSI(df['close'], timeperiod=14)
    df['rsi_overbought'] = (df['rsi'] > 70).astype(int)
    df['rsi_oversold']   = (df['rsi'] < 30).astype(int)

    # --- ATR ---
    df['atr'] = talib.ATR(df['high'], df['low'], df['close'], timeperiod=14)

    # --- ADX ---
    df['adx'] = talib.ADX(df['high'], df['low'], df['close'], timeperiod=14)

    # --- Bollinger Bands ---
    df['bb_upper'], df['bb_middle'], df['bb_lower'] = talib.BBANDS(
        df['close'], timeperiod=20, nbdevup=2, nbdevdn=2, matype=0
    )

    # --- MACD ---
    df['macd'], df['macd_signal'], _ = talib.MACD(
        df['close'], fastperiod=12, slowperiod=26, signalperiod=9
    )

    # --- Stochastic ---
    df['stoch_k'], df['stoch_d'] = talib.STOCH(
        df['high'], df['low'], df['close'],
        fastk_period=14, slowk_period=3, slowk_matype=0,
        slowd_period=3, slowd_matype=0
    )

    # --- CCI ---
    df['cci'] = talib.CCI(df['high'], df['low'], df['close'], timeperiod=14)

    # --- Williams %R ---
    df['willr'] = talib.WILLR(df['high'], df['low'], df['close'], timeperiod=14)

    # --- Rate of Change ---
    df['roc'] = talib.ROC(df['close'], timeperiod=10)

    # --- Trend EMA (1 = ema20 > ema50, -1 = ema20 < ema50) ---
    df['ema_trend'] = 0
    df.loc[df['ema20'] > df['ema50'], 'ema_trend'] = 1
    df.loc[df['ema20'] < df['ema50'], 'ema_trend'] = -1

    # --- Cena powyżej EMA20 ---
    df['price_above_ema'] = (df['close'] > df['ema20']).astype(int)

    # --- Rozmiar świecy (body) ---
    df['candle_size'] = (df['close'] - df['open']).abs()

    # --- Cienie góra / dół ---
    candle_high_low = df['high'] - df['low']
    candle_high_low = candle_high_low.replace(0, 1e-9)  # unikamy dzielenia przez 0
    body_top    = df[['open', 'close']].max(axis=1)
    body_bottom = df[['open', 'close']].min(axis=1)
    df['upper_shadow'] = (df['high'] - body_top)    / candle_high_low
    df['lower_shadow'] = (body_bottom - df['low'])  / candle_high_low

    # --- Return (zmiana procentowa) ---
    df['return'] = df['close'].pct_change()

    df.fillna(0, inplace=True)
    return df