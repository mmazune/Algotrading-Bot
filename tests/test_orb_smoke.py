"""
Smoke test for ORB strategy.
"""
import pytest
import pandas as pd
import os
from axfl.data.provider import DataProvider
from axfl.strategies.orb import ORBStrategy
from axfl.core.backtester import Backtester


def test_orb_smoke():
    """
    Smoke test: run ORB on 20-30 days of EURUSD 5m data with auto provider.
    """
    symbol = "EURUSD"
    interval = "5m"
    days = 30
    
    # Check if API keys are available
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts', 'config.py')
    if not os.path.exists(config_path):
        pytest.skip("API configuration not available")
    
    # Initialize provider with auto-selection
    provider = DataProvider(source="auto", rotate=True)
    
    # Load data
    try:
        df = provider.get_intraday(symbol, interval=interval, days=days)
    except Exception as e:
        pytest.skip(f"Could not load data (provider/rate-limit issue): {e}")
    
    if df.empty or len(df) < 200:
        pytest.skip(f"Insufficient data: only {len(df)} bars")
    
    # Initialize strategy with defaults
    strategy = ORBStrategy(symbol, {})
    
    # Run backtest
    backtester = Backtester(symbol, initial_capital=100000.0, risk_percent=0.5)
    trades_df, equity_curve_df, metrics = backtester.run(df, strategy)
    
    # Basic assertions
    assert isinstance(trades_df, pd.DataFrame), "trades_df should be a DataFrame"
    assert isinstance(equity_curve_df, pd.DataFrame), "equity_curve_df should be a DataFrame"
    assert isinstance(metrics, dict), "metrics should be a dict"
    
    # Check metrics keys
    expected_keys = ['total_return', 'cagr', 'max_drawdown', 'sharpe', 
                     'trade_count', 'win_rate', 'avg_r', 'expectancy_r']
    for key in expected_keys:
        assert key in metrics, f"Missing metric: {key}"
    
    # Trade count should be >= 0 (tolerant - allow 0 trades)
    assert metrics['trade_count'] >= 0, "trade_count should be non-negative"
    
    # Check debug info if available
    if 'debug' in metrics:
        debug = metrics['debug']
        print(f"\n✓ ORB smoke test passed: {metrics['trade_count']} trades over {days} days")
        print(f"  Total return: {metrics['total_return']*100:.2f}%")
        print(f"  Provider: {provider.last_source_used}")
        print(f"  Debug: days={debug.get('days_considered', 0)}, "
              f"breaks_up={debug.get('breaks_up', 0)}, "
              f"breaks_down={debug.get('breaks_down', 0)}, "
              f"entries_long={debug.get('entries_long', 0)}, "
              f"entries_short={debug.get('entries_short', 0)}")


if __name__ == '__main__':
    test_orb_smoke()
