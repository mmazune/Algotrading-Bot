"""
Pricing utilities for OANDA instrument formatting and calculations.

Handles pip sizes, price precision, and conversions for broker API compliance.
"""


def pip_size_from_location(pip_location: int) -> float:
    """
    Convert OANDA pipLocation to actual pip size.
    
    Args:
        pip_location: OANDA pipLocation (e.g., -4 for EUR_USD)
    
    Returns:
        Pip size as float (e.g., 0.0001 for pipLocation=-4)
    
    Example:
        >>> pip_size_from_location(-4)
        0.0001
        >>> pip_size_from_location(-2)
        0.01
    """
    return 10 ** pip_location


def fmt_price(value: float, display_precision: int) -> str:
    """
    Format a price value to OANDA's required display precision.
    
    Args:
        value: Price or distance value
        display_precision: Number of decimal places (from instrument meta)
    
    Returns:
        Formatted price string
    
    Example:
        >>> fmt_price(1.23456, 5)
        '1.23456'
        >>> fmt_price(0.001, 5)
        '0.00100'
    """
    return f"{value:.{display_precision}f}"


def pips_to_distance(sl_pips: int, pip_location: int) -> float:
    """
    Convert stop loss pips to price distance units.
    
    Args:
        sl_pips: Number of pips for stop loss
        pip_location: OANDA pipLocation (e.g., -4)
    
    Returns:
        Distance in price units
    
    Example:
        >>> pips_to_distance(10, -4)
        0.001
        >>> pips_to_distance(20, -2)
        0.2
    """
    return sl_pips * pip_size_from_location(pip_location)
