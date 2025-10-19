"""
Breaker Block Strategy.

Trades failed order blocks (breakers) that flip from support to resistance.
"""
import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional, Tuple

from .base import Strategy
from ..ta.structure import swings, in_zone
from ..core.sessions import is_in_window
from ..core.utils import compute_atr
from ..data.symbols import pip_size


class BreakerStrategy(Strategy):
    """Breaker block strategy implementation."""
    
    name = "BREAKER"
    
    def __init__(self, symbol: str, params: Dict[str, Any]):
        """
        Initialize Breaker strategy.
        
        Default params:
        - lookback: 2 (swing detection window)
        - min_zone_height_pips: 2 (minimum zone height)
        - retest_window_m: 120 (minutes to wait for retest after break)
        - buffer_pips: 2 (SL buffer beyond zone)
        - risk_perc: 0.5 (risk per trade)
        - time_stop_m: 180 (max trade duration)
        - tp1_r: 1.5 (first target)
        - tp2_r: 3.0 (second target)
        - move_be_at: 1.0 (move SL to BE after this R)
        """
        super().__init__(symbol, params)
        
        # Set defaults
        self.lookback = params.get('lookback', 2)
        self.min_zone_height_pips = params.get('min_zone_height_pips', 2)
        self.retest_window_m = params.get('retest_window_m', 120)
        self.buffer_pips = params.get('buffer_pips', 2)
        self.risk_perc = params.get('risk_perc', 0.5)
        self.time_stop_m = params.get('time_stop_m', 180)
        self.tp1_r = params.get('tp1_r', 1.5)
        self.tp2_r = params.get('tp2_r', 3.0)
        self.move_be_at = params.get('move_be_at', 1.0)
        
        self.pip = pip_size(symbol)
        
        # Debug counters
        self.debug = {
            'zones_tracked': 0,
            'zones_broken_up': 0,
            'zones_broken_down': 0,
            'retests': 0,
            'entries_long': 0,
            'entries_short': 0,
            'risk_blocked_entries': 0,
        }
    
    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        """Store df reference and add swing analysis."""
        self._df = df.copy()
        
        # Compute ATR
        self._df['ATR'] = compute_atr(self._df, period=14)
        
        # Identify swings
        self._df = swings(self._df, lookback=self.lookback)
        
        # Add date for daily tracking
        self._df['date'] = self._df.index.date
        
        return self._df
    
    def _find_recent_swing_zones(self, i: int, lookback_bars: int = 50) -> List[Tuple[float, float, str]]:
        """
        Find recent swing high/low zones.
        
        Returns:
            List of (zone_low, zone_high, zone_type) tuples
            zone_type: 'resistance' or 'support'
        """
        zones = []
        start_i = max(0, i - lookback_bars)
        
        for j in range(start_i, i):
            row = self._df.iloc[j]
            
            # Swing high = resistance zone
            if row.get('swing_high', False):
                zone_low = row['Low']
                zone_high = row['High']
                zone_height = (zone_high - zone_low) / self.pip
                
                if zone_height >= self.min_zone_height_pips:
                    zones.append((zone_low, zone_high, 'resistance'))
            
            # Swing low = support zone
            if row.get('swing_low', False):
                zone_low = row['Low']
                zone_high = row['High']
                zone_height = (zone_high - zone_low) / self.pip
                
                if zone_height >= self.min_zone_height_pips:
                    zones.append((zone_low, zone_high, 'support'))
        
        return zones
    
    def generate_signals(self, i: int, row: pd.Series, state: Dict) -> List[Dict]:
        """
        Generate breaker signals.
        
        State tracking:
        - current_date: date being processed
        - tracked_zones: List of active zones waiting for break/retest
        - broken_zone: (zone_low, zone_high, break_direction, break_time)
        - entry_taken: bool
        """
        signals = []
        
        # Extract data
        current_time = row.name
        date = current_time.date()
        
        # Initialize state for new day
        if state.get('current_date') != date:
            state['current_date'] = date
            state['tracked_zones'] = []
            state['broken_zone'] = None
            state['entry_taken'] = False
            
            # Find swing zones from recent history
            zones = self._find_recent_swing_zones(i)
            state['tracked_zones'] = zones
            self.debug['zones_tracked'] += len(zones)
        
        # Only trade during London session (07:00-16:00 UTC)
        if not is_in_window(current_time, 7, 16):
            return signals
        
        # Skip if already entered
        if state.get('entry_taken'):
            return signals
        
        # Check for zone breaks
        if state.get('broken_zone') is None and state.get('tracked_zones'):
            for zone_low, zone_high, zone_type in state['tracked_zones']:
                
                # Support broken downward (becomes resistance)
                if zone_type == 'support' and row['Close'] < zone_low:
                    state['broken_zone'] = (zone_low, zone_high, 'down', current_time)
                    state['tracked_zones'] = []  # Clear tracked zones
                    self.debug['zones_broken_down'] += 1
                    break
                
                # Resistance broken upward (becomes support)
                elif zone_type == 'resistance' and row['Close'] > zone_high:
                    state['broken_zone'] = (zone_low, zone_high, 'up', current_time)
                    state['tracked_zones'] = []  # Clear tracked zones
                    self.debug['zones_broken_up'] += 1
                    break
        
        # Check for retest and entry after break
        elif state.get('broken_zone') is not None:
            zone_low, zone_high, break_dir, break_time = state['broken_zone']
            
            # Check if still within retest window
            time_since_break = (current_time - break_time).total_seconds() / 60.0
            if time_since_break > self.retest_window_m:
                # Reset if window expired
                state['broken_zone'] = None
                return signals
            
            # Broken support (now resistance) -> SHORT on retest
            if break_dir == 'down':
                # Check if price retested the zone from below
                if in_zone(row['High'], zone_low, zone_high):
                    self.debug['retests'] += 1
                    
                    # Look for bearish rejection (close < open and below zone)
                    if row['Close'] < row['Open'] and row['Close'] < zone_low:
                        # Enter SHORT
                        sl = zone_high + (self.buffer_pips * self.pip)
                        entry = row['Close']
                        risk = sl - entry
                        tp1 = entry - (risk * self.tp1_r)
                        
                        signals.append({
                            'action': 'open',
                            'side': 'short',
                            'price': entry,
                            'sl': sl,
                            'tp': tp1,
                            'notes': f'BREAKER_short|zone_height={(zone_high-zone_low)/self.pip:.1f}pips'
                        })
                        
                        state['entry_taken'] = True
                        self.debug['entries_short'] += 1
            
            # Broken resistance (now support) -> LONG on retest
            elif break_dir == 'up':
                # Check if price retested the zone from above
                if in_zone(row['Low'], zone_low, zone_high):
                    self.debug['retests'] += 1
                    
                    # Look for bullish rejection (close > open and above zone)
                    if row['Close'] > row['Open'] and row['Close'] > zone_high:
                        # Enter LONG
                        sl = zone_low - (self.buffer_pips * self.pip)
                        entry = row['Close']
                        risk = entry - sl
                        tp1 = entry + (risk * self.tp1_r)
                        
                        signals.append({
                            'action': 'open',
                            'side': 'long',
                            'price': entry,
                            'sl': sl,
                            'tp': tp1,
                            'notes': f'BREAKER_long|zone_height={(zone_high-zone_low)/self.pip:.1f}pips'
                        })
                        
                        state['entry_taken'] = True
                        self.debug['entries_long'] += 1
        
        return signals
