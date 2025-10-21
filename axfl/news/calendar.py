"""
Economic news calendar with event-based trading guards.

Loads high-impact events from CSV and provides utilities to:
- Check if current time falls within event risk window
- Determine which symbols are affected by upcoming events
- Block new trade entries around major announcements
"""
import os
from typing import List, Dict, Optional
import pandas as pd
from datetime import timedelta


def load_events_csv(path: str) -> pd.DataFrame:
    """
    Load economic events from CSV file.
    
    Expected CSV format:
        date,time_utc,currencies,impact,title
        2025-10-20,12:30,USD,high,Core Retail Sales (MoM)
        2025-10-21,07:00,GBP,high,CPI (YoY)
    
    Args:
        path: Path to CSV file
    
    Returns:
        DataFrame with columns: datetime (index), currencies (list), impact, title
    
    Raises:
        FileNotFoundError: If CSV file doesn't exist
        ValueError: If CSV format is invalid
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"News events CSV not found: {path}")
    
    # Load CSV
    df = pd.read_csv(path)
    
    # Validate required columns
    required = ['date', 'time_utc', 'currencies', 'impact', 'title']
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"CSV missing required columns: {missing}")
    
    # Combine date + time into datetime
    df['datetime'] = pd.to_datetime(df['date'] + ' ' + df['time_utc'], utc=True)
    
    # Parse currencies as list
    df['currencies'] = df['currencies'].apply(lambda x: [c.strip() for c in str(x).split(',')])
    
    # Set datetime as index
    df = df.set_index('datetime')
    
    # Keep only needed columns
    df = df[['currencies', 'impact', 'title']]
    
    # Sort by datetime
    df = df.sort_index()
    
    return df


def upcoming_windows(
    df: pd.DataFrame,
    now_utc: pd.Timestamp,
    pad_before_m: int = 30,
    pad_after_m: int = 30,
    lookahea_hours: int = 24
) -> List[Dict]:
    """
    Get upcoming event risk windows within lookahead period.
    
    Args:
        df: Events DataFrame from load_events_csv()
        now_utc: Current time (UTC)
        pad_before_m: Minutes to pad before event
        pad_after_m: Minutes to pad after event
        lookahea_hours: Hours to look ahead for events
    
    Returns:
        List of event windows:
        [
            {
                "start": "2025-10-20T12:00:00+00:00",
                "end": "2025-10-20T13:00:00+00:00",
                "currencies": ["USD"],
                "impact": "high",
                "title": "Core Retail Sales"
            },
            ...
        ]
    """
    if df.empty:
        return []
    
    # Filter to upcoming events within lookahead window
    end_time = now_utc + timedelta(hours=lookahea_hours)
    upcoming = df[(df.index >= now_utc) & (df.index <= end_time)]
    
    windows = []
    for event_time, row in upcoming.iterrows():
        # Create padded window
        start = event_time - timedelta(minutes=pad_before_m)
        end = event_time + timedelta(minutes=pad_after_m)
        
        windows.append({
            "start": start.isoformat(),
            "end": end.isoformat(),
            "event_time": event_time.isoformat(),
            "currencies": row['currencies'],
            "impact": row['impact'],
            "title": row['title']
        })
    
    return windows


def affects_symbol(symbol: str, currencies: List[str]) -> bool:
    """
    Check if symbol is affected by currencies in event.
    
    Symbol-to-currency mapping:
        EURUSD → EUR, USD
        GBPUSD → GBP, USD
        XAUUSD → USD (gold priced in USD)
        USDJPY → USD, JPY
        etc.
    
    Args:
        symbol: Trading symbol (e.g., "EURUSD", "GBPUSD")
        currencies: List of currency codes (e.g., ["USD", "EUR"])
    
    Returns:
        True if symbol contains any of the currencies
    
    Examples:
        >>> affects_symbol("EURUSD", ["USD"])
        True
        >>> affects_symbol("EURUSD", ["GBP"])
        False
        >>> affects_symbol("XAUUSD", ["USD"])
        True  # Gold priced in USD
    """
    # Normalize symbol
    norm_symbol = symbol.upper().replace("=X", "").split(":")[-1]
    
    # Currency mapping
    symbol_currencies = set()
    
    # Standard forex pairs
    if len(norm_symbol) == 6:
        # First 3 chars = base, last 3 = quote
        base = norm_symbol[:3]
        quote = norm_symbol[3:]
        symbol_currencies = {base, quote}
    
    # Special cases
    if "XAU" in norm_symbol or "GOLD" in norm_symbol:
        # Gold: typically XAUUSD (gold in USD)
        symbol_currencies.add("USD")
    
    if "XAG" in norm_symbol or "SILVER" in norm_symbol:
        # Silver: typically XAGUSD
        symbol_currencies.add("USD")
    
    # Check overlap
    event_currencies = set([c.upper() for c in currencies])
    return bool(symbol_currencies & event_currencies)


def is_in_event_window(
    symbol: str,
    now_utc: pd.Timestamp,
    windows: List[Dict]
) -> bool:
    """
    Check if current time falls within any event window for this symbol.
    
    Args:
        symbol: Trading symbol
        now_utc: Current time (UTC)
        windows: List of event windows from upcoming_windows()
    
    Returns:
        True if symbol is affected and current time is in window
    """
    for window in windows:
        # Parse times
        start = pd.Timestamp(window['start'])
        end = pd.Timestamp(window['end'])
        
        # Check if in time window
        if start <= now_utc <= end:
            # Check if symbol affected
            if affects_symbol(symbol, window['currencies']):
                return True
    
    return False


def get_active_events(
    symbol: str,
    now_utc: pd.Timestamp,
    windows: List[Dict]
) -> List[Dict]:
    """
    Get all active events affecting this symbol right now.
    
    Args:
        symbol: Trading symbol
        now_utc: Current time (UTC)
        windows: List of event windows
    
    Returns:
        List of active event windows affecting this symbol
    """
    active = []
    
    for window in windows:
        start = pd.Timestamp(window['start'])
        end = pd.Timestamp(window['end'])
        
        # Check if in time window and affects symbol
        if start <= now_utc <= end:
            if affects_symbol(symbol, window['currencies']):
                active.append(window)
    
    return active
