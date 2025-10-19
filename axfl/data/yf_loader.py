"""
Data loader using yfinance.
"""
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from typing import Optional


def get_intraday(symbol: str, interval: str = "1m", days: int = 20) -> pd.DataFrame:
    """
    Download intraday OHLCV data using yfinance.
    
    Args:
        symbol: Trading symbol (e.g., "EURUSD=X")
        interval: Time interval (1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo)
        days: Number of days of history to download
    
    Returns:
        DataFrame with DatetimeIndex (UTC) and columns: Open, High, Low, Close, Volume
    """
    # Calculate period
    if interval in ['1m', '2m', '5m', '15m', '30m']:
        # For minute data, yfinance limits to 7 days per request
        period = min(days, 7)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=period)
    else:
        period = f"{days}d"
        start_date = None
        end_date = None
    
    # Download data
    ticker = yf.Ticker(symbol)
    
    if start_date is not None:
        df = ticker.history(start=start_date, end=end_date, interval=interval)
    else:
        df = ticker.history(period=period, interval=interval)
    
    if df.empty:
        raise ValueError(f"No data returned for {symbol} with interval {interval}")
    
    # Ensure required columns exist
    required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")
    
    # Select only OHLCV columns
    df = df[required_cols].copy()
    
    # Ensure UTC timezone
    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC')
    else:
        df.index = df.index.tz_convert('UTC')
    
    # Remove any NaN rows
    df = df.dropna()
    
    return df
