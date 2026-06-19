import numpy as np
import pandas as pd


def calc_ema(df: pd.DataFrame, period: int) -> pd.Series:
    if df is None or len(df) == 0:
        return pd.Series(dtype=float)
    close = df["close"].astype(float)
    return close.ewm(span=period, adjust=False).mean()


def calc_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    if df is None or len(df) < period:
        return pd.Series(dtype=float)
    close = df["close"].astype(float)
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def calc_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    if df is None or len(df) < 2:
        return pd.Series(dtype=float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = true_range.ewm(alpha=1 / period, adjust=False).mean()
    return atr
