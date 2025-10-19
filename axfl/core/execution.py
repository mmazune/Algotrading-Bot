"""
Execution model with spread, slippage and commission.
"""
import pandas as pd
import numpy as np
from typing import Optional
from .utils import compute_atr


# Default spread configuration (pips)
DEFAULT_FX_SPREAD_PIPS = 0.6  # EURUSD typical


def apply_costs(price: float, side: str, pip: float, 
                action: str = 'open',
                spread_pips: float = DEFAULT_FX_SPREAD_PIPS,
                atr: Optional[float] = None) -> float:
    """
    Apply spread and slippage costs to an execution price.
    
    Cost model:
    - Spread: bid-ask spread (entry pays half, exit pays half)
    - Slippage: max(1 * pip, ATR/1000) - market impact
    
    Args:
        price: Base execution price (mid-price)
        side: 'long' or 'short'
        pip: Pip size for the instrument
        action: 'open' or 'close'
        spread_pips: Bid-ask spread in pips
        atr: Average True Range value (optional)
    
    Returns:
        Adjusted price with spread and slippage
    """
    spread = spread_pips * pip
    half_spread = spread / 2.0
    
    # Calculate slippage
    slippage = pip  # Default: 1 pip
    if atr is not None and not np.isnan(atr):
        atr_slippage = atr / 1000.0
        slippage = max(slippage, atr_slippage)
    
    # Apply costs based on side and action
    if side == 'long':
        if action == 'open':
            # Buy at ask + slippage
            return price + half_spread + slippage
        else:  # close
            # Sell at bid - slippage
            return price - half_spread - slippage
    elif side == 'short':
        if action == 'open':
            # Sell at bid - slippage
            return price - half_spread - slippage
        else:  # close
            # Buy at ask + slippage
            return price + half_spread + slippage
    else:
        return price


def apply_slippage(price: float, side: str, pip: float, 
                   atr: Optional[float] = None) -> float:
    """
    Legacy function - Apply slippage only (for backwards compatibility).
    
    Args:
        price: Base execution price
        side: 'long' or 'short'
        pip: Pip size for the instrument
        atr: Average True Range value (optional)
    
    Returns:
        Adjusted price with slippage
    """
    # Default slippage: 1 pip
    slippage = pip
    
    # Use ATR-based slippage if available
    if atr is not None and not np.isnan(atr):
        atr_slippage = atr / 1000.0
        slippage = max(slippage, atr_slippage)
    
    # Apply slippage: add for longs (worse fill), subtract for shorts (worse fill)
    if side == 'long':
        return price + slippage
    elif side == 'short':
        return price - slippage
    else:
        return price


def calculate_commission(size: float, price: float) -> float:
    """
    Calculate commission for a trade.
    
    For FX, commission is typically 0 or very small.
    
    Args:
        size: Position size (lots or units)
        price: Execution price
    
    Returns:
        Commission amount (0 for FX)
    """
    return 0.0
