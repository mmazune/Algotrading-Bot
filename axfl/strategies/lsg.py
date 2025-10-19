"""
Liquidity Sweep + Grab (LSG) Strategy.

Detects equal highs/lows, sweeps, and counter-trend grab opportunities.
"""
import pandas as pd
import numpy as np
from typing import List, Dict, Any, Tuple

from .base import Strategy
from ..core.sessions import is_in_window, day_range
from ..core.utils import compute_atr
from ..data.symbols import pip_size


class LSGStrategy(Strategy):
    """Liquidity Sweep + Grab strategy implementation."""
    
    name = "LSG"
    
    def __init__(self, symbol: str, params: Dict[str, Any]):
        """
        Initialize LSG strategy.
        
        Default params:
        - tol_pips: 2 (tolerance for equal highs/lows)
        - sweep_pips: 3 (minimum sweep distance)
        - reentry_window_m: 30 (minutes to wait for grab)
        - buffer_pips: 2 (SL buffer)
        - risk_perc: 0.5 (risk per trade)
        - time_stop_m: 120 (max trade duration)
        - min_cluster_count: 2 (minimum swings in cluster)
        - bos_required: True (require BOS confirmation)
        - bos_buffer_pips: 1.0 (BOS close beyond swing buffer)
        - confirm_body_required: True (confirmation candle directional)
        - second_move_only: True (skip first break, wait for second)
        """
        super().__init__(symbol, params)
        
        # Set defaults
        self.tol_pips = params.get('tol_pips', 2)
        self.sweep_pips = params.get('sweep_pips', 3)
        self.reentry_window_m = params.get('reentry_window_m', 30)
        self.buffer_pips = params.get('buffer_pips', 2)
        self.risk_perc = params.get('risk_perc', 0.5)
        self.time_stop_m = params.get('time_stop_m', 120)
        self.min_cluster_count = params.get('min_cluster_count', 2)
        self.bos_required = params.get('bos_required', True)
        self.bos_buffer_pips = params.get('bos_buffer_pips', 1.0)
        self.confirm_body_required = params.get('confirm_body_required', True)
        self.second_move_only = params.get('second_move_only', True)
        
        self.pip = pip_size(symbol)
        
        # Debug counters
        self.debug = {
            'clusters_high': 0,
            'clusters_low': 0,
            'sweeps_high': 0,
            'sweeps_low': 0,
            'bos_up': 0,
            'bos_down': 0,
            'confirmations_high': 0,
            'confirmations_low': 0,
            'second_move_armed': 0,
            'second_move_fired': 0,
            'entries_short': 0,
            'entries_long': 0,
        }
    
    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add swing analysis and cluster detection."""
        df = df.copy()
        
        # Compute ATR
        df['ATR'] = compute_atr(df, period=14)
        
        # Identify swing highs and lows (simple local maxima/minima)
        window = 2
        df['swing_high'] = False
        df['swing_low'] = False
        
        for i in range(window, len(df) - window):
            # Swing high: higher than neighbors
            if df['High'].iloc[i] >= df['High'].iloc[i-window:i+window+1].max():
                df.loc[df.index[i], 'swing_high'] = True
            
            # Swing low: lower than neighbors
            if df['Low'].iloc[i] <= df['Low'].iloc[i-window:i+window+1].min():
                df.loc[df.index[i], 'swing_low'] = True
        
        # Add date for daily analysis
        df['date'] = df.index.date
        
        # Detect clusters per day in pre-session (00:00-06:59 UTC)
        df['cluster_high'] = None
        df['cluster_low'] = None
        
        for date in df['date'].unique():
            # Get pre-session bars
            day_mask = df['date'] == date
            presession_mask = day_mask & (df.index.hour <= 6)
            
            if presession_mask.sum() < 10:
                continue
            
            day_df = df[presession_mask].copy()
            
            # Find swing highs and cluster them
            swing_highs = day_df[day_df['swing_high']]['High'].values
            if len(swing_highs) >= self.min_cluster_count:
                cluster = self._find_cluster(swing_highs, self.tol_pips * self.pip)
                if cluster is not None:
                    self.debug['clusters_high'] += 1
                    df.loc[day_mask, 'cluster_high'] = cluster
            
            # Find swing lows and cluster them
            swing_lows = day_df[day_df['swing_low']]['Low'].values
            if len(swing_lows) >= self.min_cluster_count:
                cluster = self._find_cluster(swing_lows, self.tol_pips * self.pip)
                if cluster is not None:
                    self.debug['clusters_low'] += 1
                    df.loc[day_mask, 'cluster_low'] = cluster
        
        return df
    
    def _find_cluster(self, values: np.ndarray, tolerance: float) -> float:
        """
        Find cluster of equal highs/lows within tolerance.
        
        Returns the median value of the cluster, or None if no cluster found.
        """
        if len(values) < self.min_cluster_count:
            return None
        
        # Sort values
        sorted_vals = np.sort(values)
        
        # Find largest cluster within tolerance
        best_cluster = []
        for i in range(len(sorted_vals)):
            cluster = [sorted_vals[i]]
            for j in range(i+1, len(sorted_vals)):
                if abs(sorted_vals[j] - sorted_vals[i]) <= tolerance:
                    cluster.append(sorted_vals[j])
            
            if len(cluster) >= self.min_cluster_count and len(cluster) > len(best_cluster):
                best_cluster = cluster
        
        if len(best_cluster) >= self.min_cluster_count:
            return np.median(best_cluster)
        
        return None
    
    def generate_signals(self, i: int, row: pd.Series, state: Dict) -> List[Dict]:
        """
        Generate LSG signals (v2 with BOS and second-move logic).
        
        State tracking:
        - current_date: date being processed
        - sweep_detected: 'high' or 'low' or None
        - sweep_time: timestamp of sweep
        - sweep_extreme: price extreme during sweep
        - bos_confirmed: bool (BOS requirement met)
        - confirmation_bar: bar that closed back in range
        - first_break_seen: bool (for second_move_only)
        - entry_taken: bool
        """
        signals = []
        
        # Extract data
        current_time = row.name
        date = current_time.date()
        
        cluster_high = row.get('cluster_high')
        cluster_low = row.get('cluster_low')
        
        # Initialize state for new day
        if state.get('current_date') != date:
            state['current_date'] = date
            state['sweep_detected'] = None
            state['sweep_time'] = None
            state['sweep_extreme'] = None
            state['bos_confirmed'] = False
            state['confirmation_bar'] = None
            state['first_break_seen'] = False
            state['entry_taken'] = False
            state['last_swing_high'] = None
            state['last_swing_low'] = None
        
        # Track recent swings for BOS detection
        if row.get('swing_high', False):
            state['last_swing_high'] = row['High']
        if row.get('swing_low', False):
            state['last_swing_low'] = row['Low']
        
        # Only trade during London session (07:00-10:00 UTC)
        if not is_in_window(current_time, 7, 10):
            return signals
        
        # Skip if already entered
        if state.get('entry_taken'):
            return signals
        
        # Detect sweep
        if state.get('sweep_detected') is None:
            # High sweep
            if not pd.isna(cluster_high) and row['High'] > cluster_high:
                sweep_dist = (row['High'] - cluster_high) / self.pip
                if sweep_dist >= self.sweep_pips:
                    self.debug['sweeps_high'] += 1
                    state['sweep_detected'] = 'high'
                    state['sweep_time'] = current_time
                    state['sweep_extreme'] = row['High']
                    state['bos_confirmed'] = not self.bos_required  # Skip BOS if not required
            
            # Low sweep
            elif not pd.isna(cluster_low) and row['Low'] < cluster_low:
                sweep_dist = (cluster_low - row['Low']) / self.pip
                if sweep_dist >= self.sweep_pips:
                    self.debug['sweeps_low'] += 1
                    state['sweep_detected'] = 'low'
                    state['sweep_time'] = current_time
                    state['sweep_extreme'] = row['Low']
                    state['bos_confirmed'] = not self.bos_required  # Skip BOS if not required
        
        # Check for BOS after sweep (if required and not yet confirmed)
        elif state.get('sweep_detected') is not None and not state.get('bos_confirmed') and self.bos_required:
            sweep_type = state['sweep_detected']
            sweep_time = state['sweep_time']
            
            # Check if still within reentry window
            time_since_sweep = (current_time - sweep_time).total_seconds() / 60.0
            if time_since_sweep > self.reentry_window_m:
                state['sweep_detected'] = None
                return signals
            
            bos_buffer = self.bos_buffer_pips * self.pip
            
            # High sweep -> require down BOS (close below last swing low)
            if sweep_type == 'high':
                if state.get('last_swing_low') is not None:
                    if row['Close'] < (state['last_swing_low'] - bos_buffer):
                        self.debug['bos_down'] += 1
                        state['bos_confirmed'] = True
            
            # Low sweep -> require up BOS (close above last swing high)
            elif sweep_type == 'low':
                if state.get('last_swing_high') is not None:
                    if row['Close'] > (state['last_swing_high'] + bos_buffer):
                        self.debug['bos_up'] += 1
                        state['bos_confirmed'] = True
        
        # Check for grab (close back in range) after sweep + BOS
        elif state.get('sweep_detected') is not None and state.get('bos_confirmed') and state.get('confirmation_bar') is None:
            sweep_type = state['sweep_detected']
            sweep_time = state['sweep_time']
            
            # Check if still within reentry window
            time_since_sweep = (current_time - sweep_time).total_seconds() / 60.0
            if time_since_sweep > self.reentry_window_m:
                state['sweep_detected'] = None
                return signals
            
            # High sweep -> look for close back below cluster
            if sweep_type == 'high' and not pd.isna(cluster_high):
                if row['Close'] < cluster_high:
                    # Check body requirement
                    body_ok = (row['Close'] < row['Open']) if self.confirm_body_required else True
                    if body_ok:
                        self.debug['confirmations_high'] += 1
                        state['confirmation_bar'] = {
                            'time': current_time,
                            'high': row['High'],
                            'low': row['Low'],
                            'close': row['Close']
                        }
            
            # Low sweep -> look for close back above cluster
            elif sweep_type == 'low' and not pd.isna(cluster_low):
                if row['Close'] > cluster_low:
                    # Check body requirement
                    body_ok = (row['Close'] > row['Open']) if self.confirm_body_required else True
                    if body_ok:
                        self.debug['confirmations_low'] += 1
                        state['confirmation_bar'] = {
                            'time': current_time,
                            'high': row['High'],
                            'low': row['Low'],
                            'close': row['Close']
                        }
        
        # Check for entry on break of confirmation bar (with second-move logic)
        elif state.get('confirmation_bar') is not None:
            sweep_type = state['sweep_detected']
            sweep_extreme = state['sweep_extreme']
            conf = state['confirmation_bar']
            
            # High sweep + bearish confirmation -> SHORT on break of conf low
            if sweep_type == 'high':
                if row['Low'] < conf['low']:
                    # Second-move logic
                    if self.second_move_only and not state.get('first_break_seen'):
                        # Skip first break
                        state['first_break_seen'] = True
                        self.debug['second_move_armed'] += 1
                    else:
                        # Enter SHORT (either second move or not using second_move_only)
                        self.debug['second_move_fired'] += 1
                        sl = sweep_extreme + (self.buffer_pips * self.pip)
                        entry = conf['low']
                        risk = sl - entry
                        tp1 = entry - risk  # 1R
                        
                        signals.append({
                            'action': 'open',
                            'side': 'short',
                            'price': entry,
                            'sl': sl,
                            'tp': tp1,
                            'notes': f'LSG_v2_short'
                        })
                        
                        state['entry_taken'] = True
                        self.debug['entries_short'] += 1
            
            # Low sweep + bullish confirmation -> LONG on break of conf high
            elif sweep_type == 'low':
                if row['High'] > conf['high']:
                    # Second-move logic
                    if self.second_move_only and not state.get('first_break_seen'):
                        # Skip first break
                        state['first_break_seen'] = True
                        self.debug['second_move_armed'] += 1
                    else:
                        # Enter LONG (either second move or not using second_move_only)
                        self.debug['second_move_fired'] += 1
                        sl = sweep_extreme - (self.buffer_pips * self.pip)
                        entry = conf['high']
                        risk = entry - sl
                        tp1 = entry + risk  # 1R
                        
                        signals.append({
                            'action': 'open',
                            'side': 'long',
                            'price': entry,
                            'sl': sl,
                            'tp': tp1,
                            'notes': f'LSG_v2_long'
                        })
                        
                        state['entry_taken'] = True
                        self.debug['entries_long'] += 1
        
        return signals
