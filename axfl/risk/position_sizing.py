"""
Position sizing based on ATR, stop distance, and equity risk.

Implements dynamic position sizing that adjusts trade size based on:
- Account equity
- Risk per trade (fraction of equity)
- Stop loss distance (in pips)
- Symbol-specific pip values
"""
import math
from typing import Optional
from ..data.symbols import pip_size


def pip_value(symbol: str) -> float:
    """
    Get pip value in USD per standard lot (100k units) for a symbol.
    
    Simplified constants for common symbols:
    - EURUSD, GBPUSD: $10 per pip per 100k units
    - XAUUSD (Gold): $1 per $0.1 move per 100 units (= $1000 per 100k units per pip)
    
    For precise calculation, would need real-time quote currency conversion.
    These constants are typical approximations.
    
    Args:
        symbol: Trading symbol (e.g., "EURUSD", "GBPUSD", "XAUUSD")
    
    Returns:
        Pip value in USD per 100k units
    
    Examples:
        >>> pip_value("EURUSD")
        10.0
        >>> pip_value("XAUUSD")
        1000.0
    """
    norm_symbol = symbol.upper().replace("=X", "").split(":")[-1]
    
    # Standard forex pairs (quote currency USD)
    if norm_symbol in ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"]:
        return 10.0
    
    # Gold (special case: $1 per $0.1 move per 100 units)
    # For 100k units: $1 * 1000 = $1000 per pip
    if "XAU" in norm_symbol or "GOLD" in norm_symbol:
        return 1000.0
    
    # USD quote pairs (approximate, assumes USD as base)
    if norm_symbol in ["USDJPY", "USDCHF", "USDCAD"]:
        # Approximate: ~$10 per pip (ignoring conversion)
        return 10.0
    
    # Default fallback
    return 10.0


def units_from_risk(
    symbol: str,
    entry: float,
    sl: float,
    equity_usd: float,
    risk_fraction: float = 0.005
) -> int:
    """
    Calculate position size (units) based on stop loss distance and risk parameters.
    
    Formula:
        1. risk_amount = equity_usd * risk_fraction
        2. sl_distance_pips = abs(entry - sl) / pip_size(symbol)
        3. per_unit_loss = sl_distance_pips * pip_value(symbol) / 100000
        4. units = floor(risk_amount / per_unit_loss)
    
    Args:
        symbol: Trading symbol (e.g., "EURUSD")
        entry: Entry price
        sl: Stop loss price
        equity_usd: Current account equity in USD
        risk_fraction: Risk per trade as fraction of equity (default 0.5% = 0.005)
    
    Returns:
        Position size in units (minimum 1)
    
    Examples:
        >>> # Risk $50 (0.5% of $10k) on EURUSD with 20 pip stop
        >>> units_from_risk("EURUSD", 1.1000, 1.0980, 10000, 0.005)
        2500  # $50 / (20 pips * $10/pip / 100k) = 2500 units
        
        >>> # Risk $100 (1% of $10k) on XAUUSD with 10 pip stop
        >>> units_from_risk("XAUUSD", 2650.0, 2649.0, 10000, 0.01)
        10  # $100 / (10 pips * $1000/pip / 100k) = 10 units
    """
    # Normalize symbol
    norm_symbol = symbol.upper().replace("=X", "").split(":")[-1]
    
    # Calculate risk amount in USD
    risk_amount = equity_usd * risk_fraction
    
    # Calculate stop loss distance in pips
    pip = pip_size(norm_symbol)
    sl_distance_pips = abs(entry - sl) / pip
    
    # Avoid division by zero
    if sl_distance_pips < 0.1:
        sl_distance_pips = 0.1
    
    # Calculate per-unit loss in USD
    # pip_value returns $/pip per 100k units, so divide by 100k to get per-unit
    pv = pip_value(norm_symbol)
    per_unit_loss = sl_distance_pips * pv / 100000.0
    
    # Avoid division by zero
    if per_unit_loss < 1e-9:
        per_unit_loss = 1e-9
    
    # Calculate units
    units = risk_amount / per_unit_loss
    
    # Floor and ensure minimum of 1
    units = int(math.floor(units))
    units = max(1, units)
    
    return units


def compute_position_size(
    symbol: str,
    entry: float,
    sl: float,
    equity_usd: float,
    risk_fraction: float = 0.005,
    max_units: Optional[int] = None
) -> dict:
    """
    Compute position size with detailed breakdown.
    
    Args:
        symbol: Trading symbol
        entry: Entry price
        sl: Stop loss price
        equity_usd: Current equity in USD
        risk_fraction: Risk per trade (default 0.5%)
        max_units: Optional maximum units cap
    
    Returns:
        Dictionary with size breakdown:
        {
            "units": int,
            "risk_usd": float,
            "sl_distance_pips": float,
            "pip_value": float,
            "capped": bool
        }
    """
    units = units_from_risk(symbol, entry, sl, equity_usd, risk_fraction)
    
    # Apply cap if specified
    capped = False
    if max_units and units > max_units:
        units = max_units
        capped = True
    
    # Calculate actual risk
    pip = pip_size(symbol)
    sl_distance_pips = abs(entry - sl) / pip
    pv = pip_value(symbol)
    actual_risk_usd = units * sl_distance_pips * pv / 100000.0
    
    return {
        "units": units,
        "risk_usd": actual_risk_usd,
        "sl_distance_pips": sl_distance_pips,
        "pip_value": pv,
        "capped": capped
    }
