"""
Asia Range Liquidity Sweep (ARLS) Strategy.

Concept:
- Identify Asia session range (00:00-06:59 UTC)
- During London open (07:00-10:00 UTC), detect liquidity sweeps
- Enter counter-trend when price re-enters range
- Use tight stops and multi-tier profit targets
"""
import pandas as pd
import numpy as np
from typing import List, Dict, Any

from .base import Strategy
from ..core.sessions import day_range, is_in_window
from ..core.utils import compute_atr
from ..data.symbols import pip_size


class ARLSStrategy(Strategy):
    """Asia Range Liquidity Sweep strategy implementation."""
    
    name = "ARLS"
    
    def __init__(self, symbol: str, params: Dict[str, Any]):
        """
        Initialize ARLS strategy.
        
        Default params (relaxed for better detection):
        - sweep_pips: 3 (minimum pip breach to confirm sweep)
        - use_atr_confirm: True (require ATR-based confirmation)
        - atr_multiplier: 0.10 (sweep must be >= ATR * multiplier)
        - reentry_window_m: 45 (minutes to wait for reentry)
        - buffer_pips: 2 (SL buffer beyond sweep extreme)
        - risk_perc: 0.5 (risk per trade)
        - time_stop_m: 120 (maximum trade duration)
        - min_range_pips: 3 (minimum Asia range size)
        """
        super().__init__(symbol, params)
        
        # Set defaults (relaxed thresholds)
        self.sweep_pips = params.get('sweep_pips', 3)
        self.use_atr_confirm = params.get('use_atr_confirm', True)
        self.atr_multiplier = params.get('atr_multiplier', 0.10)
        self.reentry_window_m = params.get('reentry_window_m', 45)
        self.buffer_pips = params.get('buffer_pips', 2)
        self.risk_perc = params.get('risk_perc', 0.5)
        self.time_stop_m = params.get('time_stop_m', 120)
        self.min_range_pips = params.get('min_range_pips', 3)
        
        self.pip = pip_size(symbol)
        
        # Debug counters
        self.debug = {
            'days_considered': 0,
            'days_skipped_tiny_range': 0,
            'days_skipped_missing_bars': 0,
            'sweep_candidates_high': 0,
            'sweep_candidates_low': 0,
            'confirmations_high': 0,
            'confirmations_low': 0,
            'entries_short': 0,
            'entries_long': 0,
        }
    
    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add Asia range and ATR to the dataframe."""
        df = df.copy()
        
        # Compute ATR
        df['ATR'] = compute_atr(df, period=14)
        
        # Get Asia range for each day (00:00 to 06:59 UTC)
        asia_ranges = day_range(df, start_h=0, end_h=6)
        
        # Filter out days with insufficient Asia session bars (< 30)
        df['date'] = df.index.date
        asia_bars_per_day = df[df.index.hour <= 6].groupby('date').size()
        
        for date, count in asia_bars_per_day.items():
            if count < 30:
                self.debug['days_skipped_missing_bars'] += 1
                asia_ranges = asia_ranges[asia_ranges.index != date]
        
        # Merge Asia range data back to intraday bars
        df = df.merge(
            asia_ranges[['high', 'low']].rename(columns={'high': 'asia_high', 'low': 'asia_low'}),
            left_on='date',
            right_index=True,
            how='left'
        )
        
        # Calculate Asia range in pips
        df['asia_range_pips'] = (df['asia_high'] - df['asia_low']) / self.pip
        
        # Count total days considered
        self.debug['days_considered'] = len(asia_ranges)
        
        return df
    
    def generate_signals(self, i: int, row: pd.Series, state: Dict) -> List[Dict]:
        """
        Generate ARLS signals.
        
        State tracking:
        - current_date: date being processed
        - sweep_detected: 'bull' or 'bear' or None
        - sweep_time: timestamp of sweep detection
        - sweep_extreme: price extreme during sweep
        - entry_taken: bool to prevent multiple entries per day
        """
        signals = []
        
        # Extract data
        current_time = row.name
        date = current_time.date()
        hour = current_time.hour
        
        asia_high = row.get('asia_high')
        asia_low = row.get('asia_low')
        asia_range_pips = row.get('asia_range_pips', 0)
        atr = row.get('ATR', 0)
        
        # Initialize state for new day
        if state.get('current_date') != date:
            state['current_date'] = date
            state['sweep_detected'] = None
            state['sweep_time'] = None
            state['sweep_extreme'] = None
            state['entry_taken'] = False
        
        # Skip if Asia range is invalid
        if pd.isna(asia_high) or pd.isna(asia_low):
            return signals
        
        # Skip if Asia range is too small
        if asia_range_pips < self.min_range_pips:
            if state.get('current_date') != date:
                self.debug['days_skipped_tiny_range'] += 1
            return signals
        
        # Only trade during London open window (07:00-10:00 UTC)
        if not is_in_window(current_time, 7, 10):
            return signals
        
        # Skip if already entered today
        if state.get('entry_taken'):
            return signals
        
        # Check for sweep detection
        if state.get('sweep_detected') is None:
            # Bull sweep: price breaks above Asia high
            if row['High'] > asia_high:
                breach_pips = (row['High'] - asia_high) / self.pip
                self.debug['sweep_candidates_high'] += 1
                
                # Check pip threshold
                if breach_pips >= self.sweep_pips:
                    # Check ATR confirmation if enabled
                    if self.use_atr_confirm:
                        if breach_pips >= atr * self.atr_multiplier / self.pip:
                            state['sweep_detected'] = 'bull'
                            state['sweep_time'] = current_time
                            state['sweep_extreme'] = row['High']
                            state['sweep_breach_pips'] = breach_pips
                            self.debug['confirmations_high'] += 1
                    else:
                        state['sweep_detected'] = 'bull'
                        state['sweep_time'] = current_time
                        state['sweep_extreme'] = row['High']
                        state['sweep_breach_pips'] = breach_pips
                        self.debug['confirmations_high'] += 1
            
            # Bear sweep: price breaks below Asia low
            elif row['Low'] < asia_low:
                breach_pips = (asia_low - row['Low']) / self.pip
                self.debug['sweep_candidates_low'] += 1
                
                # Check pip threshold
                if breach_pips >= self.sweep_pips:
                    # Check ATR confirmation if enabled
                    if self.use_atr_confirm:
                        if breach_pips >= atr * self.atr_multiplier / self.pip:
                            state['sweep_detected'] = 'bear'
                            state['sweep_time'] = current_time
                            state['sweep_extreme'] = row['Low']
                            state['sweep_breach_pips'] = breach_pips
                            self.debug['confirmations_low'] += 1
                    else:
                        state['sweep_detected'] = 'bear'
                        state['sweep_time'] = current_time
                        state['sweep_extreme'] = row['Low']
                        state['sweep_breach_pips'] = breach_pips
                        self.debug['confirmations_low'] += 1
        
        # Check for reentry after sweep
        elif state.get('sweep_detected') is not None:
            sweep_type = state['sweep_detected']
            sweep_time = state['sweep_time']
            sweep_extreme = state['sweep_extreme']
            sweep_breach_pips = state.get('sweep_breach_pips', 0)
            
            # Check if still within reentry window
            time_since_sweep = (current_time - sweep_time).total_seconds() / 60.0
            if time_since_sweep > self.reentry_window_m:
                # Reset sweep if window expired
                state['sweep_detected'] = None
                return signals
            
            # Bull sweep -> look for SHORT entry
            if sweep_type == 'bull':
                # Check if close is back inside Asia range
                if row['Close'] < asia_high:
                    # Confirm with bearish candle
                    if row['Close'] < row['Open']:
                        # Calculate stop-loss above sweep extreme
                        sl = sweep_extreme + (self.buffer_pips * self.pip)
                        
                        # Calculate take-profit levels (1R and 2R)
                        entry = row['Close']
                        risk = sl - entry
                        tp1 = entry - risk  # 1R
                        tp2 = entry - (2 * risk)  # 2R
                        
                        signals.append({
                            'action': 'open',
                            'side': 'short',
                            'price': entry,
                            'sl': sl,
                            'tp': tp1,  # Initial target at 1R
                            'notes': f'ARLS_bull_sweep_short|sweep_pips={sweep_breach_pips:.1f}'
                        })
                        
                        state['entry_taken'] = True
                        self.debug['entries_short'] += 1
            
            # Bear sweep -> look for LONG entry
            elif sweep_type == 'bear':
                # Check if close is back inside Asia range
                if row['Close'] > asia_low:
                    # Confirm with bullish candle
                    if row['Close'] > row['Open']:
                        # Calculate stop-loss below sweep extreme
                        sl = sweep_extreme - (self.buffer_pips * self.pip)
                        
                        # Calculate take-profit levels (1R and 2R)
                        entry = row['Close']
                        risk = entry - sl
                        tp1 = entry + risk  # 1R
                        tp2 = entry + (2 * risk)  # 2R
                        
                        signals.append({
                            'action': 'open',
                            'side': 'long',
                            'price': entry,
                            'sl': sl,
                            'tp': tp1,  # Initial target at 1R
                            'notes': f'ARLS_bear_sweep_long|sweep_pips={sweep_breach_pips:.1f}'
                        })
                        
                        state['entry_taken'] = True
                        self.debug['entries_long'] += 1
        
        return signals
