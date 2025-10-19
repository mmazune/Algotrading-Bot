"""
Risk management and daily limits for backtesting.
"""
from dataclasses import dataclass, field
from typing import Dict
from datetime import date


@dataclass
class RiskRules:
    """Risk management rules for daily trading limits."""
    max_trades_per_day: int = 5
    daily_loss_stop_r: float = -3.0  # Stop trading if cumulative R <= -3
    daily_win_stop_r: float = 6.0    # Lock gains after big day


@dataclass
class DayRiskState:
    """Track risk state for a single day."""
    trades: int = 0
    cum_r: float = 0.0
    halted: bool = False


class RiskManager:
    """
    Manages daily risk limits and trade counting.
    """
    
    def __init__(self, rules: RiskRules = None):
        """
        Initialize risk manager.
        
        Args:
            rules: RiskRules instance (uses defaults if None)
        """
        self.rules = rules or RiskRules()
        self.day_states: Dict[date, DayRiskState] = {}
    
    def _get_state(self, dt: date) -> DayRiskState:
        """Get or create state for a date."""
        if dt not in self.day_states:
            self.day_states[dt] = DayRiskState()
        return self.day_states[dt]
    
    def can_open(self, dt: date) -> bool:
        """
        Check if new trades are allowed for this date.
        
        Args:
            dt: Trading date
        
        Returns:
            True if trading is allowed
        """
        state = self._get_state(dt)
        
        # Check if halted
        if state.halted:
            return False
        
        # Check trade limit
        if state.trades >= self.rules.max_trades_per_day:
            return False
        
        # Check loss stop
        if state.cum_r <= self.rules.daily_loss_stop_r:
            state.halted = True
            return False
        
        # Check win stop (optional)
        if state.cum_r >= self.rules.daily_win_stop_r:
            state.halted = True
            return False
        
        return True
    
    def on_open(self, dt: date) -> None:
        """
        Record a trade opening.
        
        Args:
            dt: Trading date
        """
        state = self._get_state(dt)
        state.trades += 1
    
    def on_close(self, dt: date, r_multiple: float) -> None:
        """
        Record a trade closing with its R-multiple.
        
        Args:
            dt: Trading date
            r_multiple: R-multiple of the closed trade
        """
        state = self._get_state(dt)
        state.cum_r += r_multiple
        
        # Check if limits breached
        if state.cum_r <= self.rules.daily_loss_stop_r:
            state.halted = True
        elif state.cum_r >= self.rules.daily_win_stop_r:
            state.halted = True
    
    def get_summary(self, last_n: int = 5) -> Dict:
        """
        Get risk summary for last N dates.
        
        Args:
            last_n: Number of recent dates to include
        
        Returns:
            Dictionary with daily risk statistics
        """
        if not self.day_states:
            return {}
        
        sorted_dates = sorted(self.day_states.keys(), reverse=True)[:last_n]
        
        summary = {}
        for dt in sorted_dates:
            state = self.day_states[dt]
            summary[str(dt)] = {
                'trades': state.trades,
                'cum_r': round(state.cum_r, 2),
                'halted': state.halted
            }
        
        return summary
