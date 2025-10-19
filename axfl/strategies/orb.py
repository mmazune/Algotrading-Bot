"""
London Opening Range Breakout (ORB) Strategy.

Trades breakouts from the first 5-minute bar of the London session.
"""
import pandas as pd
import numpy as np
from typing import List, Dict, Any

from .base import Strategy
from ..core.sessions import is_in_window
from ..core.utils import compute_atr
from ..data.symbols import pip_size


class ORBStrategy(Strategy):
    """London Opening Range Breakout (5m) strategy implementation."""
    
    name = "ORB"
    
    def __init__(self, symbol: str, params: Dict[str, Any]):
        """
        Initialize ORB strategy.
        
        Default params:
        - thr_break_pips: 3 (minimum break distance from OR)
        - retest: True (require retest of OR edge)
        - retest_tol_pips: 2 (tolerance for retest)
        - buffer_pips: 1 (SL buffer beyond OR edge)
        - risk_perc: 0.5 (risk per trade)
        - time_stop_m: 120 (max trade duration)
        - filter_min_or_pips: 4 (minimum OR size)
        - use_trend_filter: True (EMA trend filter)
        """
        super().__init__(symbol, params)
        
        # Set defaults
        self.thr_break_pips = params.get('thr_break_pips', 3)
        self.retest = params.get('retest', True)
        self.retest_tol_pips = params.get('retest_tol_pips', 2)
        self.buffer_pips = params.get('buffer_pips', 1)
        self.risk_perc = params.get('risk_perc', 0.5)
        self.time_stop_m = params.get('time_stop_m', 120)
        self.filter_min_or_pips = params.get('filter_min_or_pips', 4)
        self.use_trend_filter = params.get('use_trend_filter', True)
        
        self.pip = pip_size(symbol)
        
        # Debug counters
        self.debug = {
            'days_considered': 0,
            'entries_long': 0,
            'entries_short': 0,
            'rejects_small_or': 0,
            'rejects_trend': 0,
            'breaks_up': 0,
            'breaks_down': 0,
            'retests_hit': 0,
        }
    
    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add indicators and Opening Range data."""
        df = df.copy()
        
        # Compute ATR
        df['ATR'] = compute_atr(df, period=14)
        
        # Compute EMAs for trend filter
        if self.use_trend_filter:
            df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
            df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
        else:
            df['EMA20'] = 0
            df['EMA50'] = 0
        
        # Identify Opening Range bars (07:00-07:05 UTC, should be single 5m bar)
        df['date'] = df.index.date
        df['hour'] = df.index.hour
        df['minute'] = df.index.minute
        
        # Opening Range: 07:00:00 to 07:04:59 (closes at 07:05)
        df['is_or_bar'] = (df['hour'] == 7) & (df['minute'] == 0)
        
        # Get OR high/low for each day
        or_bars = df[df['is_or_bar']].copy()
        or_daily = or_bars.groupby('date').agg({
            'High': 'max',
            'Low': 'min',
            'Open': 'first',
            'Close': 'last'
        }).rename(columns={'High': 'or_high', 'Low': 'or_low', 
                           'Open': 'or_open', 'Close': 'or_close'})
        
        # Merge back
        df = df.merge(or_daily, left_on='date', right_index=True, how='left')
        
        # Calculate OR range in pips
        df['or_range_pips'] = (df['or_high'] - df['or_low']) / self.pip
        
        # Count days
        self.debug['days_considered'] = len(or_daily)
        
        return df
    
    def generate_signals(self, i: int, row: pd.Series, state: Dict) -> List[Dict]:
        """
        Generate ORB signals.
        
        State tracking:
        - current_date: date being processed
        - or_established: bool
        - break_detected: 'up' or 'down' or None
        - break_time: timestamp of break
        - retest_pending: bool
        - entry_taken: bool
        """
        signals = []
        
        # Extract data
        current_time = row.name
        date = current_time.date()
        hour = current_time.hour
        
        or_high = row.get('or_high')
        or_low = row.get('or_low')
        or_range_pips = row.get('or_range_pips', 0)
        
        # Initialize state for new day
        if state.get('current_date') != date:
            state['current_date'] = date
            state['or_established'] = False
            state['break_detected'] = None
            state['break_time'] = None
            state['retest_pending'] = False
            state['entry_taken'] = False
        
        # Skip if OR not valid
        if pd.isna(or_high) or pd.isna(or_low):
            return signals
        
        # Establish OR after 07:05
        if not state['or_established'] and hour >= 7 and current_time.minute >= 5:
            # Check OR size filter
            if or_range_pips < self.filter_min_or_pips:
                self.debug['rejects_small_or'] += 1
                state['entry_taken'] = True  # Skip this day
                return signals
            
            state['or_established'] = True
        
        if not state['or_established']:
            return signals
        
        # Only trade during 07:05-10:00 window
        if not is_in_window(current_time, 7, 10):
            return signals
        
        # Skip if already entered
        if state.get('entry_taken'):
            return signals
        
        # Detect breakout
        if state.get('break_detected') is None:
            # Upward break
            if row['High'] > or_high:
                breach_pips = (row['High'] - or_high) / self.pip
                if breach_pips >= self.thr_break_pips:
                    self.debug['breaks_up'] += 1
                    state['break_detected'] = 'up'
                    state['break_time'] = current_time
                    state['retest_pending'] = self.retest
            
            # Downward break
            elif row['Low'] < or_low:
                breach_pips = (or_low - row['Low']) / self.pip
                if breach_pips >= self.thr_break_pips:
                    self.debug['breaks_down'] += 1
                    state['break_detected'] = 'down'
                    state['break_time'] = current_time
                    state['retest_pending'] = self.retest
        
        # Check for entry after break
        if state.get('break_detected') is not None:
            break_dir = state['break_detected']
            
            # Upward break -> LONG
            if break_dir == 'up':
                # Check retest if required
                if state['retest_pending']:
                    # Check if price pulled back near OR high
                    retest_level = or_high + (self.retest_tol_pips * self.pip)
                    if row['Low'] <= retest_level:
                        self.debug['retests_hit'] += 1
                        state['retest_pending'] = False
                
                # Enter if retest satisfied (or not required)
                if not state['retest_pending']:
                    # Check close above OR high
                    if row['Close'] > or_high:
                        # Trend filter
                        if self.use_trend_filter:
                            if row['EMA20'] <= row['EMA50']:
                                self.debug['rejects_trend'] += 1
                                state['entry_taken'] = True
                                return signals
                        
                        # Calculate SL/TP
                        sl = or_low - (self.buffer_pips * self.pip)
                        entry = row['Close']
                        risk = entry - sl
                        tp1 = entry + risk  # 1R
                        
                        signals.append({
                            'action': 'open',
                            'side': 'long',
                            'price': entry,
                            'sl': sl,
                            'tp': tp1,
                            'notes': f'ORB_long|or_range={or_range_pips:.1f}pips'
                        })
                        
                        state['entry_taken'] = True
                        self.debug['entries_long'] += 1
            
            # Downward break -> SHORT
            elif break_dir == 'down':
                # Check retest if required
                if state['retest_pending']:
                    # Check if price pulled back near OR low
                    retest_level = or_low - (self.retest_tol_pips * self.pip)
                    if row['High'] >= retest_level:
                        self.debug['retests_hit'] += 1
                        state['retest_pending'] = False
                
                # Enter if retest satisfied (or not required)
                if not state['retest_pending']:
                    # Check close below OR low
                    if row['Close'] < or_low:
                        # Trend filter
                        if self.use_trend_filter:
                            if row['EMA20'] >= row['EMA50']:
                                self.debug['rejects_trend'] += 1
                                state['entry_taken'] = True
                                return signals
                        
                        # Calculate SL/TP
                        sl = or_high + (self.buffer_pips * self.pip)
                        entry = row['Close']
                        risk = sl - entry
                        tp1 = entry - risk  # 1R
                        
                        signals.append({
                            'action': 'open',
                            'side': 'short',
                            'price': entry,
                            'sl': sl,
                            'tp': tp1,
                            'notes': f'ORB_short|or_range={or_range_pips:.1f}pips'
                        })
                        
                        state['entry_taken'] = True
                        self.debug['entries_short'] += 1
        
        return signals
