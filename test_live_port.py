import yaml
import json

# Create minimal test config
test_config = {
    'symbols': ['EURUSD'],
    'interval': '5m',
    'source': 'auto',
    'venue': 'OANDA',
    'warmup_days': 0,
    'status_every_s': 1,
    'risk': {
        'global_daily_stop_r': -5.0,
        'max_open_positions': 1,
        'per_strategy_daily_trades': 3,
        'per_strategy_daily_stop_r': -2.0,
    },
    'spreads': {'EURUSD': 0.6},
    'strategies': [
        {
            'name': 'lsg',
            'params': {},
            'windows': []
        }
    ]
}

from axfl.portfolio.engine import PortfolioEngine

print("=== Quick LIVE-PORT Test ===\n")

try:
    engine = PortfolioEngine(test_config, mode='replay', broker=None)
    
    # Just print status immediately
    engine._print_status()
    
    print("\n✓ LIVE-PORT block generated successfully")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
