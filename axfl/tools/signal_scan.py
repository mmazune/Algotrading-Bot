"""
Signal Scanner - Finds high-probability windows for strategy entries.

Modes:
1. exact: Run real backtester and convert trade entries into windows
2. heuristic: Use strategy-specific preconditions (looser than entry)
3. volatility: Pick top-ATR days during London and emit windows around 07:00-10:00
4. auto: Try exact → heuristic → volatility until windows found
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Any, Optional

from axfl.data.provider import DataProvider
from axfl.strategies.lsg import LSGStrategy
from axfl.strategies.orb import ORBStrategy
from axfl.strategies.arls import ARLSStrategy
from axfl.config.defaults import get_strategy_defaults, resolve_params
from axfl.core.backtester import Backtester


STRATEGY_MAP = {
    "lsg": LSGStrategy,
    "orb": ORBStrategy,
    "arls": ARLSStrategy,
}


def windows_from_backtest(
    df_5m: pd.DataFrame,
    strategy_cls: type,
    symbol: str,
    params: dict,
    max_events: int = 3,
    pad_before_m: int = 30,
    pad_after_m: int = 120,
) -> tuple[list[dict], dict]:
    """
    Run real backtester and convert trade entries into windows.
    
    Args:
        df_5m: DataFrame with OHLCV at 5m interval (UTC)
        strategy_cls: Strategy class
        symbol: Symbol name
        params: Strategy parameters
        max_events: Maximum number of windows to return
        pad_before_m: Minutes before entry
        pad_after_m: Minutes after entry (capped at 3h from entry)
        
    Returns:
        Tuple of (windows, params_used):
        - windows: List of [{"start": ISO, "end": ISO, "bar": ISO}, ...]
        - params_used: Dict of actual params used in backtest
    """
    if df_5m.empty:
        return [], {}
    
    try:
        # Run backtester
        backtester = Backtester(
            strategy_class=strategy_cls,
            df=df_5m.copy(),
            symbol=symbol,
            params=params,
            spread_pips=0.6,  # Minimal for scanning
        )
        
        metrics = backtester.run()
        trades = backtester.trades
        
        if not trades:
            return [], params
        
        # Convert trades to windows (most recent first)
        windows = []
        for trade in reversed(trades[-max_events:]):
            entry_time = trade['entry_time']
            exit_time = trade.get('exit_time', entry_time + pd.Timedelta('3h'))
            
            # Build window
            start = entry_time - pd.Timedelta(f"{pad_before_m}min")
            # Bound end to max 3h from entry or pad_after after exit
            end = min(
                exit_time + pd.Timedelta(f"{pad_after_m}min"),
                entry_time + pd.Timedelta("3h")
            )
            
            windows.append({
                "start": start.isoformat(),
                "end": end.isoformat(),
                "bar": entry_time.isoformat(),
            })
        
        return windows, params
        
    except Exception as e:
        # Backtest failed, return empty
        return [], params


def windows_from_heuristics(
    df_5m: pd.DataFrame,
    strategy_name: str,
    symbol: str,
    params: dict,
    max_events: int = 3,
    pad_before_m: int = 30,
    pad_after_m: int = 120,
) -> list[dict]:
    """
    Use strategy-specific heuristics (looser than entry conditions).
    
    Heuristics:
    - LSG: Detect equal highs/lows in Asia (00:00-06:59), sweeps in London (07:00-10:00)
    - ORB: Opening range >= 3 pips at 07:05, first break beyond by >=2 pips
    - ARLS: Asia range formed, price wicks outside then closes back within 45m
    
    Args:
        df_5m: DataFrame with OHLCV at 5m interval (UTC)
        strategy_name: Strategy name ("lsg", "orb", "arls")
        symbol: Symbol name
        params: Strategy parameters
        max_events: Maximum number of windows
        pad_before_m: Minutes before signal
        pad_after_m: Minutes after signal
        
    Returns:
        List of windows
    """
    if df_5m.empty:
        return []
    
    windows = []
    
    try:
        if strategy_name == "lsg":
            # LSG heuristic: Equal highs/lows + sweeps
            for date in pd.unique(df_5m.index.date)[-30:]:  # Last 30 days
                day_df = df_5m[df_5m.index.date == date]
                
                # Asia session (00:00-06:59 UTC)
                asia = day_df.between_time('00:00', '06:59')
                # London session (07:00-10:00 UTC)
                london = day_df.between_time('07:00', '10:00')
                
                if asia.empty or london.empty:
                    continue
                
                # Find equal highs (within 2 pips)
                asia_high = asia['high'].max()
                asia_low = asia['low'].min()
                pip_value = 0.0001 if 'JPY' not in symbol else 0.01
                
                # Check if London swept highs or lows
                for idx, row in london.iterrows():
                    swept_high = row['high'] > asia_high + 3 * pip_value
                    swept_low = row['low'] < asia_low - 3 * pip_value
                    
                    if swept_high or swept_low:
                        start = idx - pd.Timedelta(f"{pad_before_m}min")
                        end = idx + pd.Timedelta(f"{pad_after_m}min")
                        windows.append({
                            "start": start.isoformat(),
                            "end": end.isoformat(),
                            "bar": idx.isoformat(),
                        })
                        break  # One per day
                
                if len(windows) >= max_events:
                    break
        
        elif strategy_name == "orb":
            # ORB heuristic: Opening range width >= 3 pips, breakout >= 2 pips
            for date in pd.unique(df_5m.index.date)[-30:]:
                day_df = df_5m[df_5m.index.date == date]
                
                # Opening range at 07:05
                orb_start = day_df.between_time('07:00', '07:05')
                if orb_start.empty:
                    continue
                
                orb_high = orb_start['high'].max()
                orb_low = orb_start['low'].min()
                orb_range = orb_high - orb_low
                
                pip_value = 0.0001 if 'JPY' not in symbol else 0.01
                
                if orb_range < 3 * pip_value:
                    continue  # Range too small
                
                # Check for breakout in London session
                london = day_df.between_time('07:05', '10:00')
                for idx, row in london.iterrows():
                    broke_high = row['close'] > orb_high + 2 * pip_value
                    broke_low = row['close'] < orb_low - 2 * pip_value
                    
                    if broke_high or broke_low:
                        start = idx - pd.Timedelta(f"{pad_before_m}min")
                        end = idx + pd.Timedelta(f"{pad_after_m}min")
                        windows.append({
                            "start": start.isoformat(),
                            "end": end.isoformat(),
                            "bar": idx.isoformat(),
                        })
                        break
                
                if len(windows) >= max_events:
                    break
        
        elif strategy_name == "arls":
            # ARLS heuristic: Asia range, wick outside + close back in
            for date in pd.unique(df_5m.index.date)[-30:]:
                day_df = df_5m[df_5m.index.date == date]
                
                asia = day_df.between_time('00:00', '06:59')
                london = day_df.between_time('07:00', '10:00')
                
                if asia.empty or london.empty:
                    continue
                
                asia_high = asia['high'].max()
                asia_low = asia['low'].min()
                
                # Look for wick outside then close back in
                for idx, row in london.iterrows():
                    wicked_high = row['high'] > asia_high and row['close'] < asia_high
                    wicked_low = row['low'] < asia_low and row['close'] > asia_low
                    
                    if wicked_high or wicked_low:
                        start = idx - pd.Timedelta(f"{pad_before_m}min")
                        end = idx + pd.Timedelta(f"{pad_after_m}min")
                        windows.append({
                            "start": start.isoformat(),
                            "end": end.isoformat(),
                            "bar": idx.isoformat(),
                        })
                        break
                
                if len(windows) >= max_events:
                    break
    
    except Exception as e:
        pass  # Return whatever we found
    
    return list(reversed(windows[-max_events:]))


def windows_from_volatility(
    df_5m: pd.DataFrame,
    max_days: int = 3,
    pad_before_m: int = 30,
    pad_after_m: int = 120,
) -> list[dict]:
    """
    Pick top-ATR days during London session and emit windows around 07:00-10:00.
    
    Args:
        df_5m: DataFrame with OHLCV at 5m interval (UTC)
        max_days: Number of top volatility days to select
        pad_before_m: Minutes before 07:00
        pad_after_m: Minutes after 10:00
        
    Returns:
        List of windows
    """
    if df_5m.empty:
        return []
    
    windows = []
    
    try:
        # Calculate daily ATR (using true range approximation)
        df_5m['tr'] = df_5m['high'] - df_5m['low']
        daily_atr = df_5m.groupby(df_5m.index.date)['tr'].mean()
        
        # Get top N days by ATR
        top_dates = daily_atr.nlargest(max_days).index
        
        for date in sorted(top_dates, reverse=True):
            # Create window for London session
            london_start = pd.Timestamp(f"{date} 07:00:00", tz='UTC')
            london_end = pd.Timestamp(f"{date} 10:00:00", tz='UTC')
            
            start = london_start - pd.Timedelta(f"{pad_before_m}min")
            end = london_end + pd.Timedelta(f"{pad_after_m}min")
            
            windows.append({
                "start": start.isoformat(),
                "end": end.isoformat(),
                "bar": london_start.isoformat(),
            })
    
    except Exception as e:
        pass
    
    return windows


def scan_symbols(
    symbols: list[str],
    strategies: list[str],
    days: int,
    source: str,
    venue: str,
    interval: str = "5m",
    method: str = "auto",
    top: int = 3,
    pad_before_m: int = 30,
    pad_after_m: int = 120,
) -> dict:
    """
    Scan multiple symbols/strategies for signal triggers.
    
    Args:
        symbols: List of symbols (e.g., ["EURUSD", "GBPUSD"])
        strategies: List of strategy names (e.g., ["lsg", "orb", "arls"])
        days: Number of days to scan back
        source: Data source ("auto", "twelvedata", "finnhub")
        venue: Venue name ("OANDA")
        interval: Bar interval (default "5m")
        method: Scan method ("auto", "exact", "heuristic", "volatility")
        top: Maximum windows per symbol/strategy pair
        pad_before_m: Minutes before signal
        pad_after_m: Minutes after signal
        
    Returns:
        Dict with meta and targets:
        {
            "meta": {"source": str, "interval": str, "days": int, "method": str},
            "targets": [
                {"symbol": str, "strategy": str, "windows": [...]},
                ...
            ]
        }
    """
    provider = DataProvider(source=source if source != "auto" else "twelvedata", venue=venue)
    
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    targets = []
    debug_info = []
    
    for symbol in symbols:
        # Fetch 1m data and resample to 5m
        try:
            df_1m = provider.get_intraday(
                symbol=symbol,
                interval="1min",
                days=days,
            )
            
            if df_1m.empty:
                debug_info.append(f"{symbol}: no data fetched")
                continue
            
            # Resample to 5m (handle both lowercase and uppercase column names)
            col_map = {}
            for col in df_1m.columns:
                col_lower = col.lower()
                if col_lower in ['open', 'high', 'low', 'close', 'volume']:
                    col_map[col] = col_lower
            
            df_1m_renamed = df_1m.rename(columns=col_map)
            
            df_5m = df_1m_renamed.resample("5min").agg({
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }).dropna()
            
            debug_info.append(f"{symbol}: {len(df_5m)} bars from {df_5m.index[0]} to {df_5m.index[-1]}")
            
        except Exception as e:
            # Skip symbols that fail to fetch
            debug_info.append(f"{symbol}: fetch error - {e}")
            continue
        
        for strategy_name in strategies:
            strategy_cls = STRATEGY_MAP.get(strategy_name)
            if not strategy_cls:
                continue
            
            # Resolve params using resolve_params for proper defaults + overrides
            try:
                params = resolve_params(
                    base_params=None,  # No user overrides in scan
                    strategy=strategy_name,
                    symbol=symbol,
                    interval="5m"
                )
            except Exception:
                # Fallback to get_strategy_defaults
                try:
                    params = get_strategy_defaults(strategy_name, symbol, "5m")
                    if not params:
                        params = {}
                except Exception:
                    params = {}
            
            # Find windows based on method
            windows = []
            params_used = None
            method_used = method
            
            if method == "exact":
                windows, params_used = windows_from_backtest(
                    df_5m, strategy_cls, symbol, params,
                    max_events=top, pad_before_m=pad_before_m, pad_after_m=pad_after_m
                )
            elif method == "heuristic":
                windows = windows_from_heuristics(
                    df_5m, strategy_name, symbol, params,
                    max_events=top, pad_before_m=pad_before_m, pad_after_m=pad_after_m
                )
            elif method == "volatility":
                windows = windows_from_volatility(
                    df_5m, max_days=top, pad_before_m=pad_before_m, pad_after_m=pad_after_m
                )
            elif method == "auto":
                # Try exact first
                windows, params_used = windows_from_backtest(
                    df_5m, strategy_cls, symbol, params,
                    max_events=top, pad_before_m=pad_before_m, pad_after_m=pad_after_m
                )
                method_used = "exact"
                
                # If empty, try heuristic
                if not windows:
                    windows = windows_from_heuristics(
                        df_5m, strategy_name, symbol, params,
                        max_events=top, pad_before_m=pad_before_m, pad_after_m=pad_after_m
                    )
                    method_used = "heuristic"
                    params_used = None  # Don't embed params for heuristic
                
                # If still empty, try volatility
                if not windows:
                    windows = windows_from_volatility(
                        df_5m, max_days=top, pad_before_m=pad_before_m, pad_after_m=pad_after_m
                    )
                    method_used = "volatility"
                    params_used = None
            
            debug_info.append(f"{symbol}/{strategy_name}: {len(windows)} windows found (method: {method_used})")
            
            if windows:
                target_entry = {
                    "symbol": symbol,
                    "strategy": strategy_name,
                    "windows": windows[:top],  # Cap to top
                }
                
                # Include params only for exact method
                if method == "exact" and params_used:
                    target_entry["params"] = params_used
                elif method_used == "exact" and params_used:  # For auto that used exact
                    target_entry["params"] = params_used
                
                targets.append(target_entry)
    
    # Print debug info to stderr
    import sys
    for line in debug_info:
        print(f"DEBUG: {line}", file=sys.stderr)
    
    return {
        "meta": {
            "source": source,
            "interval": interval,
            "days": days,
            "method": method,
            "pad_before": pad_before_m,
            "pad_after": pad_after_m,
            "scanned_at": datetime.utcnow().isoformat(),
        },
        "targets": targets,
    }
