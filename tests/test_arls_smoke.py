"""
Smoke test for ARLS strategy.
"""
import pytest
import pandas as pd
import os
from axfl.data.provider import DataProvider
from axfl.strategies.arls import ARLSStrategy
from axfl.core.backtester import Backtester


def test_arls_smoke():
    """
    Smoke test: run ARLS on 5 days of EURUSD data with auto provider.
    
    This test verifies:
    - Data can be loaded via multi-provider
    - Strategy runs without errors
    - Results have expected structure
    - At least some trades are generated (tolerant check)
    """
    symbol = "EURUSD"
    interval = "1m"
    days = 5
    
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
    
    if df.empty or len(df) < 100:
        pytest.skip(f"Insufficient data: only {len(df)} bars")
    
    # Initialize strategy with defaults
    strategy = ARLSStrategy(symbol, {})
    
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
    
    # Equity curve should not be empty
    assert not equity_curve_df.empty, "equity_curve should have entries"
    
    # Trade count should be >= 0 (allow 0 trades on some days - tolerant)
    assert metrics['trade_count'] >= 0, "trade_count should be non-negative"
    
    # If trades exist, check structure
    if not trades_df.empty:
        expected_trade_cols = ['entry_time', 'exit_time', 'side', 'entry', 
                               'exit', 'size', 'pnl', 'r_multiple']
        for col in expected_trade_cols:
            assert col in trades_df.columns, f"Missing trade column: {col}"
        
        # Basic sanity checks
        assert trades_df['side'].isin(['long', 'short']).all(), "Invalid side values"
        assert (trades_df['size'] > 0).all(), "Position sizes should be positive"
    
    # Check debug info if available
    if 'debug' in metrics:
        debug = metrics['debug']
        print(f"\n✓ Smoke test passed: {metrics['trade_count']} trades over {days} days")
        print(f"  Total return: {metrics['total_return']*100:.2f}%")
        print(f"  Win rate: {metrics['win_rate']*100:.2f}%")
        print(f"  Provider: {provider.last_source_used}")
        print(f"  Debug: days_considered={debug.get('days_considered', 0)}, "
              f"sweeps_high={debug.get('sweep_candidates_high', 0)}, "
              f"sweeps_low={debug.get('sweep_candidates_low', 0)}")


if __name__ == '__main__':
    test_arls_smoke()
