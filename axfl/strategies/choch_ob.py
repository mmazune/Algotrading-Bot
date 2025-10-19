"""
CHOCH + Order Block Retest Strategy.

Trades CHOCH (Change of Character) with order block retest confirmation.
"""
import pandas as pd
import numpy as np
from typing import List, Dict, Any

from .base import Strategy
from ..ta.structure import swings, map_structure, tag_order_block, in_zone
from ..core.sessions import is_in_window
from ..core.utils import compute_atr
from ..data.symbols import pip_size


class CHOCHOBStrategy(Strategy):
    """CHOCH + Order Block retest strategy implementation."""
    
    name = "CHOCH_OB"
    
    def __init__(self, symbol: str, params: Dict[str, Any]):
        """
        Initialize CHOCH OB strategy.
        
        Default params:
        - lookback: 2 (swing detection window)
        - confirm_with_body: True (require close beyond swing for BOS/CHOCH)
        - retest_window_m: 60 (minutes to wait for retest)
        - buffer_pips: 2 (SL buffer beyond OB)
        - min_ob_height_pips: 2 (minimum OB height)
        - risk_perc: 0.5 (risk per trade)
        - time_stop_m: 180 (max trade duration)
        - tp1_r: 1.0 (first target)
        - tp2_r: 2.0 (second target)
        - move_be_at: 1.0 (move SL to BE after this R)
        """
        super().__init__(symbol, params)
        
        # Set defaults
        self.lookback = params.get('lookback', 2)
        self.confirm_with_body = params.get('confirm_with_body', True)
        self.retest_window_m = params.get('retest_window_m', 60)
        self.buffer_pips = params.get('buffer_pips', 2)
        self.min_ob_height_pips = params.get('min_ob_height_pips', 2)
        self.risk_perc = params.get('risk_perc', 0.5)
        self.time_stop_m = params.get('time_stop_m', 180)
        self.tp1_r = params.get('tp1_r', 1.0)
        self.tp2_r = params.get('tp2_r', 2.0)
        self.move_be_at = params.get('move_be_at', 1.0)
        
        self.pip = pip_size(symbol)
        
        # Debug counters
        self.debug = {
            'choch_up': 0,
            'choch_down': 0,
            'ob_tagged': 0,
            'retests': 0,
            'entries_long': 0,
            'entries_short': 0,
            'rejections': 0,
            'risk_blocked_entries': 0,
        }
    
    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add structure analysis to dataframe."""
        df = df.copy()
        
        # Compute ATR
        df['ATR'] = compute_atr(df, period=14)
        
        # Identify swings
        df = swings(df, lookback=self.lookback)
        
        # Map market structure
        df = map_structure(df)
        
        # Add date for daily tracking
        df['date'] = df.index.date
        
        return df
    
    def generate_signals(self, i: int, row: pd.Series, state: Dict) -> List[Dict]:
        """
        Generate CHOCH OB signals.
        
        State tracking:
        - current_date: date being processed
        - choch_detected: 'up' or 'down' or None
        - choch_time: timestamp of CHOCH
        - ob_low, ob_high, ob_mid: order block levels
        - retest_confirmed: bool
        - entry_taken: bool
        """
        signals = []
        
        # Extract data
        current_time = row.name
        date = current_time.date()
        
        # Initialize state for new day
        if state.get('current_date') != date:
            state['current_date'] = date
            state['choch_detected'] = None
            state['choch_time'] = None
            state['ob_low'] = None
            state['ob_high'] = None
            state['ob_mid'] = None
            state['retest_confirmed'] = False
            state['entry_taken'] = False
        
        # Only trade during London session (07:00-10:00 UTC)
        if not is_in_window(current_time, 7, 16):
            return signals
        
        # Skip if already entered
        if state.get('entry_taken'):
            return signals
        
        # Detect CHOCH
        if state.get('choch_detected') is None:
            # CHOCH Up (bearish to bullish)
            if row.get('choch_up', False):
                self.debug['choch_up'] += 1
                
                # Tag the bullish order block
                ob_low, ob_high, ob_mid = tag_order_block(
                    self._df, i, 'bullish', use_body=self.confirm_with_body
                )
                
                if ob_low is not None and ob_high is not None:
                    ob_height = (ob_high - ob_low) / self.pip
                    
                    # Check minimum height
                    if ob_height >= self.min_ob_height_pips:
                        state['choch_detected'] = 'up'
                        state['choch_time'] = current_time
                        state['ob_low'] = ob_low
                        state['ob_high'] = ob_high
                        state['ob_mid'] = ob_mid
                        self.debug['ob_tagged'] += 1
            
            # CHOCH Down (bullish to bearish)
            elif row.get('choch_down', False):
                self.debug['choch_down'] += 1
                
                # Tag the bearish order block
                ob_low, ob_high, ob_mid = tag_order_block(
                    self._df, i, 'bearish', use_body=self.confirm_with_body
                )
                
                if ob_low is not None and ob_high is not None:
                    ob_height = (ob_high - ob_low) / self.pip
                    
                    # Check minimum height
                    if ob_height >= self.min_ob_height_pips:
                        state['choch_detected'] = 'down'
                        state['choch_time'] = current_time
                        state['ob_low'] = ob_low
                        state['ob_high'] = ob_high
                        state['ob_mid'] = ob_mid
                        self.debug['ob_tagged'] += 1
        
        # Check for retest and entry
        elif state.get('choch_detected') is not None and not state.get('retest_confirmed'):
            choch_dir = state['choch_detected']
            choch_time = state['choch_time']
            ob_low = state['ob_low']
            ob_high = state['ob_high']
            
            # Check if still within retest window
            time_since_choch = (current_time - choch_time).total_seconds() / 60.0
            if time_since_choch > self.retest_window_m:
                # Reset if window expired
                state['choch_detected'] = None
                return signals
            
            # CHOCH Up -> Look for LONG entry on retest
            if choch_dir == 'up':
                # Check if price is in OB zone
                if in_zone(row['Low'], ob_low, ob_high) or in_zone(row['Close'], ob_low, ob_high):
                    self.debug['retests'] += 1
                    
                    # Look for bullish rejection (close > open)
                    if row['Close'] > row['Open']:
                        self.debug['rejections'] += 1
                        state['retest_confirmed'] = True
                        
                        # Enter LONG
                        sl = ob_low - (self.buffer_pips * self.pip)
                        entry = row['Close']
                        risk = entry - sl
                        tp1 = entry + (risk * self.tp1_r)
                        
                        signals.append({
                            'action': 'open',
                            'side': 'long',
                            'price': entry,
                            'sl': sl,
                            'tp': tp1,
                            'notes': f'CHOCH_OB_long|ob_height={(ob_high-ob_low)/self.pip:.1f}pips'
                        })
                        
                        state['entry_taken'] = True
                        self.debug['entries_long'] += 1
            
            # CHOCH Down -> Look for SHORT entry on retest
            elif choch_dir == 'down':
                # Check if price is in OB zone
                if in_zone(row['High'], ob_low, ob_high) or in_zone(row['Close'], ob_low, ob_high):
                    self.debug['retests'] += 1
                    
                    # Look for bearish rejection (close < open)
                    if row['Close'] < row['Open']:
                        self.debug['rejections'] += 1
                        state['retest_confirmed'] = True
                        
                        # Enter SHORT
                        sl = ob_high + (self.buffer_pips * self.pip)
                        entry = row['Close']
                        risk = sl - entry
                        tp1 = entry - (risk * self.tp1_r)
                        
                        signals.append({
                            'action': 'open',
                            'side': 'short',
                            'price': entry,
                            'sl': sl,
                            'tp': tp1,
                            'notes': f'CHOCH_OB_short|ob_height={(ob_high-ob_low)/self.pip:.1f}pips'
                        })
                        
                        state['entry_taken'] = True
                        self.debug['entries_short'] += 1
        
        return signals
    
    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        """Store df reference and add structure analysis."""
        self._df = df.copy()
        
        # Compute ATR
        self._df['ATR'] = compute_atr(self._df, period=14)
        
        # Identify swings
        self._df = swings(self._df, lookback=self.lookback)
        
        # Map market structure
        self._df = map_structure(self._df)
        
        # Add date for daily tracking
        self._df['date'] = self._df.index.date
        
        return self._df
