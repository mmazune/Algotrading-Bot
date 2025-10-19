"""
Symbol normalization and utilities for different data providers.
"""
from typing import Optional


def normalize(symbol: str, source: str, venue: Optional[str] = None) -> str:
    """
    Normalize symbol format for different data providers.
    
    Args:
        symbol: Base symbol (e.g., "EURUSD", "EUR/USD", "EURUSD=X", "XAUUSD")
        source: Data source ("twelvedata", "finnhub", "yf", "auto")
        venue: Optional venue for finnhub (e.g., "OANDA")
    
    Returns:
        Normalized symbol string
    
    Examples:
        normalize("EURUSD", "twelvedata") -> "EUR/USD"
        normalize("GBPUSD", "twelvedata") -> "GBP/USD"
        normalize("XAUUSD", "twelvedata") -> "XAU/USD"
        normalize("EURUSD", "finnhub", "OANDA") -> "OANDA:EUR_USD"
        normalize("EURUSD", "yf") -> "EURUSD=X"
    """
    # Clean the input symbol
    base_symbol = symbol.upper().replace("/", "").replace("=X", "").replace("_", "").replace(":", "").split(":")[-1]
    
    if source == "auto":
        return symbol  # Provider will decide
    
    elif source == "twelvedata":
        # TwelveData uses "EUR/USD" format
        if len(base_symbol) == 6:
            return f"{base_symbol[:3]}/{base_symbol[3:]}"
        return symbol
    
    elif source == "finnhub":
        # Finnhub uses "VENUE:EUR_USD" format
        if len(base_symbol) == 6:
            normalized = f"{base_symbol[:3]}_{base_symbol[3:]}"
            if venue:
                return f"{venue}:{normalized}"
            else:
                return f"OANDA:{normalized}"  # Default to OANDA
        return symbol
    
    elif source == "yf":
        # Yahoo Finance uses "EURUSD=X" format
        if len(base_symbol) == 6:
            return f"{base_symbol}=X"
        return symbol
    
    return symbol


def pip_size(symbol: str) -> float:
    """
    Get pip size for a given symbol.
    
    Args:
        symbol: Trading symbol (any format)
    
    Returns:
        Pip size (0.0001 for major FX pairs, 0.01 for JPY pairs, 0.1 for gold)
    """
    symbol_upper = symbol.upper()
    
    # Gold (XAU) - treat $0.10 as 1 pip for R calculations
    if 'XAU' in symbol_upper:
        return 0.1
    
    # JPY pairs have different pip size
    if 'JPY' in symbol_upper:
        return 0.01
    
    # Default for major FX pairs
    return 0.0001


def default_spread(symbol: str) -> float:
    """
    Get default spread in pips for a symbol.
    
    Args:
        symbol: Trading symbol (any format)
    
    Returns:
        Default spread in pips
    """
    symbol_upper = symbol.upper()
    
    if 'XAU' in symbol_upper:
        return 2.5  # Gold ~$2.5 spread
    elif 'GBP' in symbol_upper:
        return 0.9  # Cable ~0.9 pips
    elif 'EUR' in symbol_upper:
        return 0.6  # EUR pairs ~0.6 pips
    else:
        return 1.0  # Generic default
