import pandas as pd
import numpy as np


def add_moving_averages(df: pd.DataFrame, short: int = 25, long: int = 75) -> pd.DataFrame:
    df[f"SMA{short}"] = df["Close"].rolling(short).mean()
    df[f"SMA{long}"] = df["Close"].rolling(long).mean()
    df["EMA12"] = df["Close"].ewm(span=12, adjust=False).mean()
    df["EMA26"] = df["Close"].ewm(span=26, adjust=False).mean()
    return df


def add_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["RSI"] = 100 - (100 / (1 + rs))
    return df


def add_macd(df: pd.DataFrame) -> pd.DataFrame:
    df["MACD"] = df["EMA12"] - df["EMA26"]
    df["MACD_signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
    df["MACD_hist"] = df["MACD"] - df["MACD_signal"]
    return df


def add_bollinger_bands(df: pd.DataFrame, period: int = 20, std: float = 2.0) -> pd.DataFrame:
    sma = df["Close"].rolling(period).mean()
    sigma = df["Close"].rolling(period).std()
    df["BB_upper"] = sma + std * sigma
    df["BB_mid"] = sma
    df["BB_lower"] = sma - std * sigma
    bb_width = (df["BB_upper"] - df["BB_lower"]).replace(0, np.nan)
    df["BB_pct"] = (df["Close"] - df["BB_lower"]) / bb_width
    return df


def add_ichimoku(df: pd.DataFrame) -> pd.DataFrame:
    high = df["High"]
    low = df["Low"]

    tenkan = (high.rolling(9).max() + low.rolling(9).min()) / 2
    kijun = (high.rolling(26).max() + low.rolling(26).min()) / 2
    senkou_a = ((tenkan + kijun) / 2).shift(26)
    senkou_b = ((high.rolling(52).max() + low.rolling(52).min()) / 2).shift(26)
    chikou = df["Close"].shift(-26)

    df["Ichimoku_tenkan"] = tenkan
    df["Ichimoku_kijun"] = kijun
    df["Ichimoku_senkou_a"] = senkou_a
    df["Ichimoku_senkou_b"] = senkou_b
    df["Ichimoku_chikou"] = chikou
    return df


def add_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    high_low = df["High"] - df["Low"]
    high_close = (df["High"] - df["Close"].shift()).abs()
    low_close = (df["Low"] - df["Close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["ATR"] = tr.ewm(com=period - 1, adjust=False).mean()
    return df


def add_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    ADX（平均方向性指数）: トレンドの強さを0〜100で計測。
    方向は見ない（上昇/下落どちらのトレンドでも高くなる）。
    ADX > 25: 強いトレンド → シグナルの信頼性高い
    ADX < 20: 横ばい相場 → シグナルが騙しになりやすい
    DI+: 上昇の勢い、DI-: 下落の勢い
    """
    high_low = df["High"] - df["Low"]
    high_close = (df["High"] - df["Close"].shift()).abs()
    low_close = (df["Low"] - df["Close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)

    up_move = df["High"].diff()
    down_move = -df["Low"].diff()

    dm_plus = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    dm_minus = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    atr_s = tr.ewm(com=period - 1, adjust=False).mean()
    di_plus = 100 * dm_plus.ewm(com=period - 1, adjust=False).mean() / atr_s
    di_minus = 100 * dm_minus.ewm(com=period - 1, adjust=False).mean() / atr_s

    dx = 100 * (di_plus - di_minus).abs() / (di_plus + di_minus).replace(0, np.nan)
    adx = dx.ewm(com=period - 1, adjust=False).mean()

    df["ADX"] = adx
    df["DI_plus"] = di_plus
    df["DI_minus"] = di_minus
    return df


def add_stochastic(df: pd.DataFrame, k: int = 14, d: int = 3) -> pd.DataFrame:
    low_min = df["Low"].rolling(k).min()
    high_max = df["High"].rolling(k).max()
    denom = (high_max - low_min).replace(0, np.nan)
    df["Stoch_K"] = 100 * (df["Close"] - low_min) / denom
    df["Stoch_D"] = df["Stoch_K"].rolling(d).mean()
    return df


def add_obv(df: pd.DataFrame) -> pd.DataFrame:
    direction = df["Close"].diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    df["OBV"] = (df["Volume"] * direction).cumsum()
    return df


def add_vwap(df: pd.DataFrame) -> pd.DataFrame:
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    tpv = (tp * df["Volume"]).fillna(0)
    vol = df["Volume"].fillna(0)
    try:
        dates = pd.Series([idx.date() for idx in df.index], index=df.index)
        n_bars_per_day = len(df) / max(dates.nunique(), 1)
        if n_bars_per_day > 1.5:
            cum_tpv = tpv.groupby(dates).cumsum()
            cum_vol = vol.groupby(dates).cumsum()
        else:
            cum_tpv = tpv.rolling(20).sum()
            cum_vol = vol.rolling(20).sum()
    except Exception:
        cum_tpv = tpv.cumsum()
        cum_vol = vol.cumsum()
    df["VWAP"] = cum_tpv / cum_vol.replace(0, float("nan"))
    return df


def compute_all(df: pd.DataFrame, sma_short: int = 25, sma_long: int = 75) -> pd.DataFrame:
    df = df.copy()
    df = add_moving_averages(df, sma_short, sma_long)
    df = add_rsi(df)
    df = add_macd(df)
    df = add_bollinger_bands(df)
    df = add_ichimoku(df)
    df = add_atr(df)
    df = add_adx(df)
    df = add_stochastic(df)
    df = add_obv(df)
    df = add_vwap(df)
    return df
