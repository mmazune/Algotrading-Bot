"""
Target Window Helpers - Filter and merge scan targets for replay.
"""

import pandas as pd
from typing import Any


def windows_by_symbol(targets: dict, extend_minutes: int = 0) -> dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]]:
    """
    Convert scan targets to per-symbol window lists.
    
    Args:
        targets: Dict from scan_symbols with {"targets": [...]}
        extend_minutes: Extend each window by this many minutes (both start and end)
        
    Returns:
        {"EURUSD": [(start, end), ...], "GBPUSD": [...], ...}
        All timestamps are tz-aware UTC.
    """
    result = {}
    
    for target in targets.get("targets", []):
        symbol = target["symbol"]
        
        if symbol not in result:
            result[symbol] = []
        
        for window in target.get("windows", []):
            start_ts = pd.Timestamp(window["start"])
            end_ts = pd.Timestamp(window["end"])
            
            # Ensure UTC timezone
            if start_ts.tz is None:
                start_ts = start_ts.tz_localize("UTC")
            else:
                start_ts = start_ts.tz_convert("UTC")
            
            if end_ts.tz is None:
                end_ts = end_ts.tz_localize("UTC")
            else:
                end_ts = end_ts.tz_convert("UTC")
            
            # Apply extension
            if extend_minutes > 0:
                start_ts = start_ts - pd.Timedelta(f"{extend_minutes}min")
                end_ts = end_ts + pd.Timedelta(f"{extend_minutes}min")
            
            result[symbol].append((start_ts, end_ts))
    
    return result


def window_filter(ts: pd.Timestamp, sym_windows: list[tuple]) -> bool:
    """
    Check if timestamp is inside any of the provided windows.
    
    Args:
        ts: Timestamp to check (tz-aware UTC)
        sym_windows: List of (start, end) tuples
        
    Returns:
        True if ts is within any window, False otherwise
    """
    for start, end in sym_windows:
        if start <= ts <= end:
            return True
    return False


def earliest_start(targets: dict) -> pd.Timestamp:
    """
    Find the earliest window start time across all targets.
    
    Args:
        targets: Dict from scan_symbols with {"targets": [...]}
        
    Returns:
        Earliest start timestamp (tz-aware UTC)
    """
    earliest = None
    
    for target in targets.get("targets", []):
        for window in target.get("windows", []):
            start_ts = pd.Timestamp(window["start"])
            
            # Ensure UTC timezone
            if start_ts.tz is None:
                start_ts = start_ts.tz_localize("UTC")
            else:
                start_ts = start_ts.tz_convert("UTC")
            
            if earliest is None or start_ts < earliest:
                earliest = start_ts
    
    return earliest if earliest else pd.Timestamp.now(tz='UTC')
