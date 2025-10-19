"""
Tick-to-bar aggregation for live trading.
"""
import pandas as pd
import numpy as np
from typing import Optional, Tuple, List
from datetime import datetime, timedelta


class BarAggregator:
    """Aggregates ticks into OHLCV bars at specified timeframe."""
    
    def __init__(self, timeframe: str):
        """
        Initialize bar aggregator.
        
        Args:
            timeframe: '1m' or '5m'
        """
        self.timeframe = timeframe
        self.minutes = 1 if timeframe == '1m' else 5
        
        # Current partial bar
        self.current_bar_start = None
        self.open_price = None
        self.high_price = None
        self.low_price = None
        self.close_price = None
        self.volume = 0
        
    def _align_timestamp(self, ts: pd.Timestamp) -> pd.Timestamp:
        """Align timestamp to bar boundary."""
        minute = (ts.minute // self.minutes) * self.minutes
        return ts.replace(minute=minute, second=0, microsecond=0)
    
    def push_tick(self, ts: pd.Timestamp, 
                  bid: Optional[float] = None, 
                  ask: Optional[float] = None, 
                  last: Optional[float] = None) -> Optional[dict]:
        """
        Push a tick and potentially emit a completed bar.
        
        Args:
            ts: Tick timestamp (must be tz-aware UTC)
            bid: Bid price
            ask: Ask price
            last: Last price
        
        Returns:
            Completed bar dict with keys: time, Open, High, Low, Close, Volume
            or None if bar not yet complete
        """
        # Ensure UTC
        if ts.tz is None:
            ts = ts.tz_localize('UTC')
        else:
            ts = ts.tz_convert('UTC')
        
        # Derive mid price
        if bid is not None and ask is not None:
            price = (bid + ask) / 2.0
        elif last is not None:
            price = last
        elif bid is not None:
            price = bid
        elif ask is not None:
            price = ask
        else:
            return None  # No price data
        
        # Determine bar start
        bar_start = self._align_timestamp(ts)
        
        # Check if we need to emit the previous bar
        completed_bar = None
        if self.current_bar_start is not None and bar_start > self.current_bar_start:
            # Emit completed bar
            completed_bar = {
                'time': self.current_bar_start,
                'Open': self.open_price,
                'High': self.high_price,
                'Low': self.low_price,
                'Close': self.close_price,
                'Volume': self.volume,
            }
            
            # Reset for new bar
            self.current_bar_start = None
            self.open_price = None
            self.high_price = None
            self.low_price = None
            self.close_price = None
            self.volume = 0
        
        # Update current bar
        if self.current_bar_start is None:
            self.current_bar_start = bar_start
            self.open_price = price
            self.high_price = price
            self.low_price = price
        else:
            self.high_price = max(self.high_price, price)
            self.low_price = min(self.low_price, price)
        
        self.close_price = price
        self.volume += 1  # Count ticks as volume
        
        return completed_bar


class CascadeAggregator:
    """Chains 1m aggregator into 5m aggregator."""
    
    def __init__(self):
        """Initialize cascade with 1m -> 5m aggregation."""
        self.agg_1m = BarAggregator('1m')
        self.agg_5m = BarAggregator('5m')
    
    def push_tick(self, ts: pd.Timestamp, 
                  bid: Optional[float] = None, 
                  ask: Optional[float] = None, 
                  last: Optional[float] = None) -> List[dict]:
        """
        Push tick through cascade.
        
        Returns:
            List of completed 5m bars (0 or 1 usually)
        """
        bars_5m = []
        
        # Push to 1m aggregator
        bar_1m = self.agg_1m.push_tick(ts, bid, ask, last)
        
        # If 1m bar completed, push to 5m aggregator
        if bar_1m is not None:
            # Use 1m bar OHLC as synthetic ticks to 5m
            bar_5m = self.agg_5m.push_tick(
                bar_1m['time'], 
                bid=bar_1m['Close'], 
                ask=bar_1m['Close'], 
                last=bar_1m['Close']
            )
            
            if bar_5m is not None:
                bars_5m.append(bar_5m)
        
        return bars_5m
