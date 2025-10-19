"""
FX trading session helpers and utilities.
Handles session windows in UTC timezone.
"""
from typing import Tuple
import pandas as pd
import pytz


# Session windows in UTC
ASIA_RANGE = (0, 6, 59)  # 00:00 to 06:59 UTC
LONDON_OPEN = (7, 0, 10, 0)  # 07:00 to 10:00 UTC


def is_in_window(ts: pd.Timestamp, start_h: int, end_h: int) -> bool:
    """
    Check if a timestamp falls within a time window.
    
    Args:
        ts: Timezone-aware timestamp
        start_h: Start hour (inclusive)
        end_h: End hour (inclusive)
    
    Returns:
        True if timestamp hour is in [start_h, end_h]
    """
    if not isinstance(ts, pd.Timestamp):
        ts = pd.Timestamp(ts)
    
    # Ensure UTC
    if ts.tz is None:
        ts = ts.tz_localize('UTC')
    else:
        ts = ts.tz_convert('UTC')
    
    return start_h <= ts.hour <= end_h


def day_range(df: pd.DataFrame, start_h: int, end_h: int) -> pd.DataFrame:
    """
    Compute daily high/low/start/end for a specific time window.
    
    Args:
        df: DataFrame with DatetimeIndex and columns ['Open', 'High', 'Low', 'Close']
        start_h: Window start hour (UTC)
        end_h: Window end hour (UTC, inclusive)
    
    Returns:
        DataFrame indexed by date with columns: high, low, start, end
    """
    if df.empty:
        return pd.DataFrame(columns=['high', 'low', 'start', 'end'])
    
    # Ensure UTC
    if df.index.tz is None:
        df = df.copy()
        df.index = df.index.tz_localize('UTC')
    else:
        df = df.copy()
        df.index = df.index.tz_convert('UTC')
    
    # Filter to window hours
    mask = (df.index.hour >= start_h) & (df.index.hour <= end_h)
    window_df = df[mask].copy()
    
    if window_df.empty:
        return pd.DataFrame(columns=['high', 'low', 'start', 'end'])
    
    # Group by date
    window_df['date'] = window_df.index.date
    
    result = window_df.groupby('date').agg({
        'High': 'max',
        'Low': 'min',
    }).rename(columns={'High': 'high', 'Low': 'low'})
    
    # Add start and end times
    start_times = window_df.groupby('date').apply(lambda x: x.index.min())
    end_times = window_df.groupby('date').apply(lambda x: x.index.max())
    
    result['start'] = start_times
    result['end'] = end_times
    
    return result


def pip_size(symbol: str) -> float:
    """
    Get pip size for a given symbol.
    
    Args:
        symbol: Trading symbol (e.g., "EURUSD=X", "GBPUSD=X")
    
    Returns:
        Pip size (0.0001 for major pairs, 0.01 for JPY pairs)
    """
    symbol_upper = symbol.upper()
    
    # JPY pairs have different pip size
    if 'JPY' in symbol_upper:
        return 0.01
    
    # Default for major FX pairs
    return 0.0001
