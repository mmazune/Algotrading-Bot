"""
Portfolio capital allocation and risk budgets.

Implements:
- Per-strategy risk budgets
- Daily risk limits
- Volatility targeting (future)
- Kelly fraction caps (future)
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class PortfolioBudgets:
    """
    Portfolio-level risk budgets and capital allocation.
    
    Attributes:
        equity_usd: Total account equity in USD
        daily_risk_fraction: Maximum daily risk as fraction of equity (e.g., 0.02 = 2%)
        per_strategy_fraction: Risk allocation per strategy (e.g., 0.34 = 34% for 3 strategies)
        per_trade_fraction: Risk per individual trade (e.g., 0.005 = 0.5%)
        volatility_target_annual: Annual volatility target for vol scaling (future use)
    
    Example:
        >>> budgets = PortfolioBudgets(equity_usd=100000, daily_risk_fraction=0.02)
        >>> budgets.daily_r_total()
        2000.0  # $100k * 2% = $2000 daily risk limit
    """
    equity_usd: float = 100000.0
    daily_risk_fraction: float = 0.02          # 2% total daily risk
    per_strategy_fraction: float = 0.34        # ~33% per strategy (3 strategies)
    per_trade_fraction: float = 0.005          # 0.5% per trade
    volatility_target_annual: float = 0.10     # 10% annual vol target (future use)
    
    def daily_r_total(self) -> float:
        """Total daily risk budget in USD."""
        return self.equity_usd * self.daily_risk_fraction
    
    def per_strategy_r(self) -> float:
        """Risk budget per strategy in USD."""
        return self.equity_usd * self.per_strategy_fraction
    
    def per_trade_r(self) -> float:
        """Risk per trade in USD."""
        return self.equity_usd * self.per_trade_fraction


def compute_budgets(
    symbols: List[str],
    strategies: List[str],
    spreads: Optional[Dict[str, float]] = None,
    equity_usd: float = 100000.0,
    daily_risk_fraction: float = 0.02,
    per_trade_fraction: float = 0.005
) -> dict:
    """
    Compute portfolio risk budgets with strategy allocation.
    
    Current implementation uses simple equal split across strategies.
    Future enhancements:
    - Risk parity weighting by historical volatility
    - Sharpe-weighted allocation
    - Adaptive budgets based on recent performance
    
    Args:
        symbols: List of trading symbols
        strategies: List of strategy names
        spreads: Optional spread costs per symbol
        equity_usd: Total portfolio equity
        daily_risk_fraction: Daily risk limit (fraction of equity)
        per_trade_fraction: Risk per trade (fraction of equity)
    
    Returns:
        Dictionary with budget breakdown:
        {
            "equity_usd": 100000.0,
            "daily_r_total": 2000.0,
            "per_strategy": {"lsg": 680.0, "orb": 680.0, "arls": 680.0},
            "per_trade_r": 500.0,
            "notes": "Simple equal split; risk-parity hooks ready"
        }
    """
    budgets = PortfolioBudgets(
        equity_usd=equity_usd,
        daily_risk_fraction=daily_risk_fraction,
        per_trade_fraction=per_trade_fraction
    )
    
    # Simple equal split across strategies
    num_strategies = len(strategies) if strategies else 1
    per_strategy_fraction = 1.0 / num_strategies if num_strategies > 0 else 0.34
    
    per_strategy_dict = {}
    for strat in strategies:
        # Each strategy gets equal share of daily budget
        # e.g., 3 strategies: each gets 1/3 of 2% = 0.67% of equity
        per_strategy_dict[strat] = equity_usd * (daily_risk_fraction / num_strategies)
    
    return {
        "equity_usd": equity_usd,
        "daily_r_total": budgets.daily_r_total(),
        "per_strategy": per_strategy_dict,
        "per_trade_r": budgets.per_trade_r(),
        "daily_risk_fraction": daily_risk_fraction,
        "per_trade_fraction": per_trade_fraction,
        "notes": "Simple equal split; risk-parity hooks ready"
    }


def kelly_cap(win_rate: float, avg_win: float, avg_loss: float, max_fraction: float = 0.25) -> float:
    """
    Calculate Kelly fraction with safety cap.
    
    Kelly formula: f* = (p*b - q) / b
    where:
        p = win rate
        q = 1 - p (loss rate)
        b = avg_win / avg_loss (win/loss ratio)
    
    Args:
        win_rate: Historical win rate (0-1)
        avg_win: Average win size
        avg_loss: Average loss size (positive)
        max_fraction: Maximum allowed fraction (safety cap, default 25%)
    
    Returns:
        Kelly fraction clamped to [0, max_fraction]
    
    Examples:
        >>> # 55% win rate, 1.5:1 RR
        >>> kelly_cap(0.55, 1.5, 1.0)
        0.25  # (0.55*1.5 - 0.45) / 1.5 = 0.35, capped at 0.25
        
        >>> # 40% win rate, 2:1 RR
        >>> kelly_cap(0.40, 2.0, 1.0)
        0.1  # (0.40*2 - 0.60) / 2 = 0.1
    """
    if avg_loss <= 0:
        return 0.0
    
    # Avoid division by zero
    if avg_loss < 1e-6:
        avg_loss = 1e-6
    
    b = avg_win / avg_loss  # Win/loss ratio
    p = win_rate
    q = 1.0 - win_rate
    
    # Kelly formula
    kelly = (p * b - q) / b
    
    # Clamp to [0, max_fraction]
    kelly = max(0.0, min(kelly, max_fraction))
    
    return kelly


def adjust_for_volatility(
    base_size: int,
    current_vol: float,
    target_vol: float,
    min_scale: float = 0.5,
    max_scale: float = 2.0
) -> int:
    """
    Adjust position size based on realized vs target volatility.
    
    Volatility scaling: scale position size inversely with volatility.
    When vol is high, reduce size. When vol is low, increase size.
    
    Args:
        base_size: Base position size in units
        current_vol: Current realized volatility (e.g., 20-day std dev)
        target_vol: Target volatility
        min_scale: Minimum scaling factor (default 0.5 = 50%)
        max_scale: Maximum scaling factor (default 2.0 = 200%)
    
    Returns:
        Adjusted position size in units
    
    Examples:
        >>> # Volatility is 2x target, halve position
        >>> adjust_for_volatility(1000, 0.20, 0.10)
        500
        
        >>> # Volatility is half target, double position
        >>> adjust_for_volatility(1000, 0.05, 0.10)
        2000
    """
    if current_vol <= 0 or target_vol <= 0:
        return base_size
    
    # Scale inversely with volatility ratio
    vol_ratio = current_vol / target_vol
    scale_factor = 1.0 / vol_ratio
    
    # Apply limits
    scale_factor = max(min_scale, min(scale_factor, max_scale))
    
    # Apply to base size
    adjusted_size = int(base_size * scale_factor)
    adjusted_size = max(1, adjusted_size)
    
    return adjusted_size
