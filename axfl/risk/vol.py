"""
Volatility measurement and risk-parity allocation.

Implements ATR-based volatility estimation and inverse-volatility weighting
for portfolio risk allocation across multiple symbols.
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, List


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Compute Average True Range (ATR) for OHLC data.
    
    Args:
        df: DataFrame with 'high', 'low', 'close' columns
        period: ATR smoothing period (default 14)
    
    Returns:
        pd.Series: ATR values (same index as df)
    
    Formula:
        TR = max(high - low, abs(high - prev_close), abs(low - prev_close))
        ATR = EMA(TR, period)
    """
    if df.empty or len(df) < 2:
        return pd.Series(dtype=float, index=df.index)
    
    high = df['high']
    low = df['low']
    close = df['close']
    prev_close = close.shift(1)
    
    # True Range components
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    
    # True Range = max of the three
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # ATR = exponential moving average of TR
    atr = tr.ewm(span=period, adjust=False, min_periods=period).mean()
    
    return atr


def realized_vol_pips(
    df_5m: pd.DataFrame,
    lookback_d: int,
    pip: float,
    session_start_hour: int = 7,
    session_end_hour: int = 16
) -> float:
    """
    Compute realized volatility in pips from intraday data.
    
    Filters to active trading session (default 07:00-16:00 UTC, union of London+NY),
    computes mean ATR over lookback period, and converts to pips.
    
    Args:
        df_5m: DataFrame with OHLC data (5-minute bars or finer)
        lookback_d: Number of days to look back
        pip: Pip size for the symbol (e.g., 0.0001 for EURUSD)
        session_start_hour: Session start hour UTC (default 7)
        session_end_hour: Session end hour UTC (default 16)
    
    Returns:
        float: Mean ATR in pips over lookback period
    
    Example:
        vol = realized_vol_pips(eurusd_data, lookback_d=20, pip=0.0001)
        # Returns: 12.5 (pips average ATR)
    """
    if df_5m.empty:
        return 0.0
    
    # Ensure datetime index
    if not isinstance(df_5m.index, pd.DatetimeIndex):
        df_5m = df_5m.copy()
        if 'timestamp' in df_5m.columns:
            df_5m.index = pd.to_datetime(df_5m['timestamp'])
        elif 'time' in df_5m.columns:
            df_5m.index = pd.to_datetime(df_5m['time'])
    
    # Filter to lookback period
    cutoff = df_5m.index.max() - pd.Timedelta(days=lookback_d)
    df_recent = df_5m[df_5m.index >= cutoff].copy()
    
    if df_recent.empty:
        return 0.0
    
    # Filter to session hours (07:00-16:00 UTC)
    df_recent['hour'] = df_recent.index.hour
    df_session = df_recent[
        (df_recent['hour'] >= session_start_hour) & 
        (df_recent['hour'] < session_end_hour)
    ]
    
    if df_session.empty or len(df_session) < 14:
        # Fallback to full day if session filter too aggressive
        df_session = df_recent
    
    # Resample to 5-minute bars if finer granularity
    if len(df_session) > lookback_d * 288:  # More than 288 bars per day (5-min)
        df_session = df_session.resample('5min').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last'
        }).dropna()
    
    # Compute ATR
    atr_series = compute_atr(df_session, period=14)
    
    if atr_series.empty or atr_series.isna().all():
        return 0.0
    
    # Mean ATR in price units
    mean_atr_price = atr_series.mean()
    
    # Convert to pips
    if pip > 0:
        mean_atr_pips = mean_atr_price / pip
    else:
        mean_atr_pips = mean_atr_price
    
    return float(mean_atr_pips)


def inv_vol_weights(
    symbols: List[str],
    data_map: Dict[str, pd.DataFrame],
    lookback_d: int,
    pip_map: Dict[str, float],
    floor: float = 0.15,
    cap: float = 0.60
) -> Tuple[Dict[str, float], Dict[str, float]]:
    """
    Compute inverse-volatility weights for risk-parity allocation.
    
    Allocates capital proportional to 1/volatility, ensuring diversification
    across symbols with different volatility profiles.
    
    Args:
        symbols: List of symbol names
        data_map: Dict mapping symbol -> DataFrame with OHLC data
        lookback_d: Number of days for volatility estimation
        pip_map: Dict mapping symbol -> pip size
        floor: Minimum weight per symbol (default 0.15 = 15%)
        cap: Maximum weight per symbol (default 0.60 = 60%)
    
    Returns:
        Tuple of:
            - weights: Dict[symbol, weight] (sum to 1.0)
            - vols: Dict[symbol, volatility_pips] (diagnostics)
    
    Algorithm:
        1. Compute vol_i = realized_vol_pips(data_i, lookback_d)
        2. w_i = 1 / vol_i (inverse volatility)
        3. Clamp w_i to [floor, cap]
        4. Normalize to sum = 1.0
    
    Example:
        weights, vols = inv_vol_weights(
            symbols=["EURUSD", "GBPUSD", "XAUUSD"],
            data_map={...},
            lookback_d=20,
            pip_map={"EURUSD": 0.0001, "GBPUSD": 0.0001, "XAUUSD": 0.01},
            floor=0.15,
            cap=0.60
        )
        # Returns: {"EURUSD": 0.35, "GBPUSD": 0.40, "XAUUSD": 0.25}
    """
    vols = {}
    raw_weights = {}
    
    # Step 1: Compute volatilities
    for symbol in symbols:
        df = data_map.get(symbol, pd.DataFrame())
        pip = pip_map.get(symbol, 0.0001)
        
        if df.empty:
            # Default fallback volatility
            vols[symbol] = 10.0  # Conservative default
        else:
            vol = realized_vol_pips(df, lookback_d, pip)
            vols[symbol] = max(vol, 0.1)  # Floor at 0.1 pips to avoid division by zero
    
    # Step 2: Compute inverse-volatility weights
    for symbol in symbols:
        raw_weights[symbol] = 1.0 / vols[symbol]
    
    # Step 3: Clamp to [floor, cap]
    clamped_weights = {}
    for symbol in symbols:
        w = raw_weights[symbol]
        clamped_weights[symbol] = max(floor, min(cap, w))
    
    # Step 4: Normalize to sum = 1.0
    total = sum(clamped_weights.values())
    
    if total > 0:
        normalized_weights = {
            symbol: w / total
            for symbol, w in clamped_weights.items()
        }
    else:
        # Equal weights fallback
        normalized_weights = {symbol: 1.0 / len(symbols) for symbol in symbols}
    
    return normalized_weights, vols


def risk_parity_diagnostics(
    weights: Dict[str, float],
    vols: Dict[str, float],
    equity_usd: float,
    per_trade_fraction: float
) -> Dict:
    """
    Generate diagnostic report for risk-parity allocation.
    
    Args:
        weights: Symbol weights from inv_vol_weights()
        vols: Symbol volatilities from inv_vol_weights()
        equity_usd: Portfolio equity
        per_trade_fraction: Base per-trade risk (e.g., 0.005 for 0.5%)
    
    Returns:
        Dict with diagnostics for display/logging
    """
    diagnostics = {
        'weights': weights,
        'volatilities_pips': vols,
        'per_symbol_risk_usd': {},
        'per_symbol_risk_pct': {}
    }
    
    for symbol, weight in weights.items():
        scaled_risk_pct = per_trade_fraction * weight
        scaled_risk_usd = equity_usd * scaled_risk_pct
        
        diagnostics['per_symbol_risk_usd'][symbol] = round(scaled_risk_usd, 2)
        diagnostics['per_symbol_risk_pct'][symbol] = round(scaled_risk_pct * 100, 3)
    
    return diagnostics


# ============================================================================
# Testing utilities
# ============================================================================

def generate_test_ohlc(
    n_bars: int = 1000,
    volatility: float = 10.0,
    start_price: float = 1.1000
) -> pd.DataFrame:
    """
    Generate synthetic OHLC data for testing.
    
    Args:
        n_bars: Number of bars to generate
        volatility: Price volatility (in pips)
        start_price: Starting price
    
    Returns:
        DataFrame with OHLC columns and datetime index
    """
    np.random.seed(42)
    
    # Generate random returns
    returns = np.random.normal(0, volatility * 0.0001, n_bars)
    prices = start_price * (1 + returns).cumprod()
    
    # Generate OHLC from close prices
    df = pd.DataFrame({
        'close': prices,
        'open': prices * (1 + np.random.normal(0, 0.0001, n_bars)),
        'high': prices * (1 + np.abs(np.random.normal(0, 0.0002, n_bars))),
        'low': prices * (1 - np.abs(np.random.normal(0, 0.0002, n_bars)))
    })
    
    # Add datetime index (5-minute bars)
    start_time = pd.Timestamp('2025-10-01 00:00:00', tz='UTC')
    df.index = pd.date_range(start=start_time, periods=n_bars, freq='5min')
    
    return df[['open', 'high', 'low', 'close']]


if __name__ == "__main__":
    # Quick test
    print("Testing ATR and risk-parity allocation...")
    
    # Generate test data
    eurusd = generate_test_ohlc(n_bars=2000, volatility=10.0, start_price=1.1000)
    gbpusd = generate_test_ohlc(n_bars=2000, volatility=15.0, start_price=1.2700)
    xauusd = generate_test_ohlc(n_bars=2000, volatility=50.0, start_price=2650.0)
    
    # Compute weights
    weights, vols = inv_vol_weights(
        symbols=["EURUSD", "GBPUSD", "XAUUSD"],
        data_map={"EURUSD": eurusd, "GBPUSD": gbpusd, "XAUUSD": xauusd},
        lookback_d=20,
        pip_map={"EURUSD": 0.0001, "GBPUSD": 0.0001, "XAUUSD": 0.01},
        floor=0.15,
        cap=0.60
    )
    
    print("\nVolatilities (pips):")
    for sym, vol in vols.items():
        print(f"  {sym}: {vol:.2f}")
    
    print("\nRisk-Parity Weights:")
    for sym, w in weights.items():
        print(f"  {sym}: {w:.2%}")
    
    print(f"\nSum of weights: {sum(weights.values()):.4f}")
    
    # Diagnostics
    diag = risk_parity_diagnostics(weights, vols, equity_usd=100000, per_trade_fraction=0.005)
    print("\nPer-Symbol Risk (0.5% base):")
    for sym, risk_usd in diag['per_symbol_risk_usd'].items():
        risk_pct = diag['per_symbol_risk_pct'][sym]
        print(f"  {sym}: ${risk_usd:.2f} ({risk_pct:.3f}%)")
