"""
Smoke test for CHOCH + OB strategy.
"""
import pytest
import pandas as pd
from axfl.data.provider import DataProvider
from axfl.strategies.choch_ob import CHOCHOBStrategy
from axfl.core.backtester import Backtester


def test_choch_ob_smoke():
    """Smoke test: CHOCH OB strategy completes without errors."""
    
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
        'confirm_with_body': True,
        'retest_window_m': 60,
        'buffer_pips': 2,
        'min_ob_height_pips': 2,
        'risk_perc': 0.5,
    }
    strategy = CHOCHOBStrategy(symbol=symbol, params=params)
    
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
    print("\n=== CHOCH OB Debug Counters ===")
    for key, val in strategy.debug.items():
        print(f"{key}: {val}")
    
    print(f"\nTrade Count: {metrics['trade_count']}")
    print(f"Win Rate: {metrics.get('win_rate', 0.0):.2%}")
