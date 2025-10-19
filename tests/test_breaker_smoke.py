"""
Smoke test for Breaker strategy.
"""
import pytest
import pandas as pd
from axfl.data.provider import DataProvider
from axfl.strategies.breaker import BreakerStrategy
from axfl.core.backtester import Backtester


def test_breaker_smoke():
    """Smoke test: Breaker strategy completes without errors."""
    
    symbol = "EURUSD"
    interval = "5m"
    days = 30
    
    # Try to get data with auto fallback
    provider = DataProvider(source="auto")
    
    try:
        df = provider.get_intraday(symbol, interval, days)
    except Exception as e:
        pytest.skip(f"Provider failed: {e}")
    
    if df.empty:
        pytest.skip("No data returned from provider")
    
    # Initialize strategy
    params = {
        'lookback': 2,
        'min_zone_height_pips': 2,
        'retest_window_m': 120,
        'buffer_pips': 2,
        'risk_perc': 0.5,
    }
    strategy = BreakerStrategy(symbol=symbol, params=params)
    
    # Run backtest
    bt = Backtester(symbol)
    trades_df, equity_curve_df, metrics = bt.run(df, strategy)
    
    # Assertions (tolerant - just check structure)
    assert isinstance(trades_df, pd.DataFrame)
    assert isinstance(equity_curve_df, pd.DataFrame)
    assert isinstance(metrics, dict)
    assert 'trade_count' in metrics
    assert metrics['trade_count'] >= 0
    
    # Print debug counters
    print("\n=== Breaker Debug Counters ===")
    for key, val in strategy.debug.items():
        print(f"{key}: {val}")
    
    print(f"\nTrade Count: {metrics['trade_count']}")
    print(f"Win Rate: {metrics.get('win_rate', 0.0):.2%}")
