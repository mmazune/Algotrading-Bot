"""
Smart Money Concepts (SMC) structure utilities.

Provides swing detection, BOS/CHOCH identification, and order block tagging.
"""
import pandas as pd
import numpy as np
from typing import Tuple


def swings(df: pd.DataFrame, lookback: int = 2) -> pd.DataFrame:
    """
    Identify swing highs and lows using pivot logic.
    
    Args:
        df: DataFrame with High and Low columns
        lookback: Number of bars on each side for comparison
    
    Returns:
        DataFrame with added columns: swing_high, swing_low (boolean)
    """
    df = df.copy()
    df['swing_high'] = False
    df['swing_low'] = False
    
    for i in range(lookback, len(df) - lookback):
        # Swing high: higher than all neighbors in window
        window_highs = df['High'].iloc[i-lookback:i+lookback+1]
        if df['High'].iloc[i] >= window_highs.max():
            df.loc[df.index[i], 'swing_high'] = True
        
        # Swing low: lower than all neighbors in window
        window_lows = df['Low'].iloc[i-lookback:i+lookback+1]
        if df['Low'].iloc[i] <= window_lows.min():
            df.loc[df.index[i], 'swing_low'] = True
    
    return df


def map_structure(df: pd.DataFrame) -> pd.DataFrame:
    """
    Map market structure: BOS (Break of Structure) and CHOCH (Change of Character).
    
    Walks bars sequentially maintaining regime and detecting structure breaks.
    
    Args:
        df: DataFrame with swing_high and swing_low columns (from swings())
    
    Returns:
        DataFrame with added columns:
        - bos_up, bos_down: Break of structure events
        - choch_up, choch_down: Change of character events
        - swing_high_idx, swing_low_idx: Indices of last confirmed swings
        - regime: Current regime ('bull' or 'bear')
    """
    df = df.copy()
    
    # Initialize structure columns
    df['bos_up'] = False
    df['bos_down'] = False
    df['choch_up'] = False
    df['choch_down'] = False
    df['swing_high_idx'] = -1
    df['swing_low_idx'] = -1
    df['regime'] = 'neutral'
    
    # State tracking
    regime = 'neutral'
    last_swing_high_idx = -1
    last_swing_high_val = None
    last_swing_low_idx = -1
    last_swing_low_val = None
    
    for i in range(len(df)):
        row = df.iloc[i]
        current_idx = i
        
        # Update swing points
        if row['swing_high']:
            last_swing_high_idx = current_idx
            last_swing_high_val = row['High']
        
        if row['swing_low']:
            last_swing_low_idx = current_idx
            last_swing_low_val = row['Low']
        
        # Check for structure breaks (require last swings to exist)
        if last_swing_high_val is not None and last_swing_low_val is not None:
            
            # Break above last swing high
            if row['Close'] > last_swing_high_val:
                if regime == 'bull':
                    # BOS in same direction
                    df.loc[df.index[i], 'bos_up'] = True
                elif regime == 'bear':
                    # CHOCH - regime flip
                    df.loc[df.index[i], 'choch_up'] = True
                    regime = 'bull'
                else:
                    # First break establishes regime
                    df.loc[df.index[i], 'bos_up'] = True
                    regime = 'bull'
            
            # Break below last swing low
            elif row['Close'] < last_swing_low_val:
                if regime == 'bear':
                    # BOS in same direction
                    df.loc[df.index[i], 'bos_down'] = True
                elif regime == 'bull':
                    # CHOCH - regime flip
                    df.loc[df.index[i], 'choch_down'] = True
                    regime = 'bear'
                else:
                    # First break establishes regime
                    df.loc[df.index[i], 'bos_down'] = True
                    regime = 'bear'
        
        # Record current state
        df.loc[df.index[i], 'swing_high_idx'] = last_swing_high_idx
        df.loc[df.index[i], 'swing_low_idx'] = last_swing_low_idx
        df.loc[df.index[i], 'regime'] = regime
    
    return df


def tag_order_block(
    df: pd.DataFrame,
    event_idx: int,
    side: str,
    use_body: bool = True
) -> Tuple[float, float, float]:
    """
    Tag order block (OB) that caused a structure event.
    
    An order block is the last opposite candle before the impulse move.
    
    Args:
        df: DataFrame with OHLC data
        event_idx: Index where BOS/CHOCH occurred
        side: 'bearish' for supply OB (before down move), 'bullish' for demand OB
        use_body: Use candle body (open/close) vs full range (high/low)
    
    Returns:
        Tuple of (ob_low, ob_high, ob_mid)
    """
    if event_idx < 1:
        return (None, None, None)
    
    # Look back for the last opposite candle before the event
    if side == 'bearish':
        # Find last bullish candle before bearish impulse
        for i in range(event_idx - 1, max(0, event_idx - 10), -1):
            candle = df.iloc[i]
            if candle['Close'] > candle['Open']:  # Bullish candle
                if use_body:
                    ob_low = min(candle['Open'], candle['Close'])
                    ob_high = max(candle['Open'], candle['Close'])
                else:
                    ob_low = candle['Low']
                    ob_high = candle['High']
                
                # Ensure minimum height
                if ob_high - ob_low < 1e-6:
                    ob_low = candle['Low']
                    ob_high = candle['High']
                
                ob_mid = (ob_low + ob_high) / 2.0
                return (ob_low, ob_high, ob_mid)
    
    elif side == 'bullish':
        # Find last bearish candle before bullish impulse
        for i in range(event_idx - 1, max(0, event_idx - 10), -1):
            candle = df.iloc[i]
            if candle['Close'] < candle['Open']:  # Bearish candle
                if use_body:
                    ob_low = min(candle['Open'], candle['Close'])
                    ob_high = max(candle['Open'], candle['Close'])
                else:
                    ob_low = candle['Low']
                    ob_high = candle['High']
                
                # Ensure minimum height
                if ob_high - ob_low < 1e-6:
                    ob_low = candle['Low']
                    ob_high = candle['High']
                
                ob_mid = (ob_low + ob_high) / 2.0
                return (ob_low, ob_high, ob_mid)
    
    return (None, None, None)


def in_zone(price: float, low: float, high: float, tol: float = 0.0) -> bool:
    """
    Check if price is within a zone with optional tolerance.
    
    Args:
        price: Price to check
        low: Zone lower bound
        high: Zone upper bound
        tol: Tolerance extension (adds to both sides)
    
    Returns:
        True if price is in zone
    """
    if low is None or high is None:
        return False
    
    return (low - tol) <= price <= (high + tol)
