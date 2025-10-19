"""
Utility functions for the trading system.
"""
import pandas as pd
import numpy as np
from typing import Optional


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Compute Average True Range (ATR).
    
    Args:
        df: DataFrame with High, Low, Close columns
        period: ATR period
    
    Returns:
        Series with ATR values
    """
    high = df['High']
    low = df['Low']
    close = df['Close']
    
    # True Range calculation
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # ATR is exponential moving average of TR
    atr = tr.ewm(span=period, adjust=False).mean()
    
    return atr


def to_utc(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure DataFrame index is UTC timezone-aware.
    
    Args:
        df: DataFrame with DatetimeIndex
    
    Returns:
        DataFrame with UTC timezone
    """
    df = df.copy()
    
    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC')
    else:
        df.index = df.index.tz_convert('UTC')
    
    return df
