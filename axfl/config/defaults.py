"""
Strategy default parameters from tuning results.
"""
from typing import Dict, Any, Optional


# Tuned defaults from walk-forward optimization
TUNED_DEFAULTS = {
    ("lsg", "EURUSD", "5m"): {
        "tol_pips": 2,
        "sweep_pips": 3,
        "reentry_window_m": 30,
        "bos_buffer_pips": 0.5,
        "confirm_body_required": True,
        "second_move_only": True,
        "bos_required": True,
    },
}


def get_strategy_defaults(strategy: str, symbol: str, interval: str) -> Dict[str, Any]:
    """
    Get tuned default parameters for a strategy/symbol/interval combination.
    
    Args:
        strategy: Strategy name (e.g., 'lsg', 'orb')
        symbol: Trading symbol (normalized, e.g., 'EURUSD')
        interval: Timeframe (e.g., '5m')
    
    Returns:
        Dictionary of default parameters
    """
    # Normalize symbol (remove venue prefix and =X suffix)
    norm_symbol = symbol.upper().replace("=X", "").split(":")[-1]
    
    key = (strategy.lower(), norm_symbol, interval.lower())
    return TUNED_DEFAULTS.get(key, {}).copy()


def resolve_params(base_params: Optional[Dict[str, Any]], 
                   strategy: str, 
                   symbol: str, 
                   interval: str) -> Dict[str, Any]:
    """
    Resolve final parameters by overlaying user params on tuned defaults.
    
    Args:
        base_params: User-provided parameters (can be None or incomplete)
        strategy: Strategy name
        symbol: Trading symbol
        interval: Timeframe
    
    Returns:
        Complete parameter dictionary
    """
    defaults = get_strategy_defaults(strategy, symbol, interval)
    
    if base_params is None:
        return defaults
    
    # Merge: defaults first, then overlay user params
    final_params = defaults.copy()
    final_params.update(base_params)
    
    return final_params
