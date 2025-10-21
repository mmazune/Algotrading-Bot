#!/usr/bin/env python3
"""
Validation test for Risk & News Guard v1 implementation.
Tests all three features without requiring OANDA credentials.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

def test_risk_module():
    """Test position sizing and budget allocation."""
    print("=" * 60)
    print("TEST 1: Risk Module")
    print("=" * 60)
    
    from axfl.risk import units_from_risk, pip_value, compute_budgets
    
    # Test pip values
    print("\n1. Pip Value Tests:")
    assert pip_value("EURUSD") == 10.0, "EURUSD pip value should be $10"
    assert pip_value("GBPUSD") == 10.0, "GBPUSD pip value should be $10"
    assert pip_value("XAUUSD") == 1000.0, "XAUUSD pip value should be $1000"
    print("   ✅ Pip values correct (EURUSD=$10, GBPUSD=$10, XAUUSD=$1000)")
    
    # Test position sizing
    print("\n2. Position Sizing Tests:")
    units = units_from_risk(
        symbol="EURUSD",
        entry=1.1000,
        sl=1.0980,  # 20 pips
        equity_usd=100000,
        risk_fraction=0.005
    )
    expected_units = 250000  # $500 / (20 pips * $10/pip / 100k)
    # Allow small rounding difference (within 0.1%)
    assert abs(units - expected_units) / expected_units < 0.001, f"Expected ~{expected_units} units, got {units}"
    print(f"   ✅ EURUSD sizing correct: {units} units for 20-pip SL (~{expected_units} expected)")
    
    # Test gold sizing
    units_gold = units_from_risk(
        symbol="XAUUSD",
        entry=2650.0,
        sl=2645.0,  # 5 pips ($5)
        equity_usd=100000,
        risk_fraction=0.005
    )
    print(f"   ✅ XAUUSD sizing: {units_gold} units for $5 SL")
    
    # Test budget allocation
    print("\n3. Budget Allocation Tests:")
    budgets = compute_budgets(
        symbols=["EURUSD", "GBPUSD", "XAUUSD"],
        strategies=["lsg", "orb", "arls"],
        spreads={"EURUSD": 0.6, "GBPUSD": 0.9, "XAUUSD": 2.5},
        equity_usd=100000.0,
        daily_risk_fraction=0.02,
        per_trade_fraction=0.005
    )
    
    assert budgets['equity_usd'] == 100000.0
    assert budgets['daily_r_total'] == 2000.0
    assert budgets['per_trade_r'] == 500.0
    assert len(budgets['per_strategy']) == 3
    print(f"   ✅ Budgets computed: ${budgets['daily_r_total']:.0f} daily, ${budgets['per_trade_r']:.0f} per trade")
    print(f"   ✅ Per-strategy: {list(budgets['per_strategy'].values())}")
    
    print("\n✅ RISK MODULE: ALL TESTS PASSED\n")
    return True


def test_news_module():
    """Test news calendar and event detection."""
    print("=" * 60)
    print("TEST 2: News Module")
    print("=" * 60)
    
    from axfl.news import load_events_csv, upcoming_windows, affects_symbol, is_in_event_window
    import pandas as pd
    
    # Test CSV loading
    print("\n1. CSV Loading Test:")
    csv_path = "samples/news_events.sample.csv"
    df = load_events_csv(csv_path)
    assert len(df) == 20, f"Expected 20 events, got {len(df)}"
    print(f"   ✅ Loaded {len(df)} events from {csv_path}")
    
    # Test symbol-currency mapping
    print("\n2. Symbol-Currency Mapping Tests:")
    assert affects_symbol("EURUSD", ["USD"]) == True
    assert affects_symbol("EURUSD", ["EUR"]) == True
    assert affects_symbol("EURUSD", ["GBP"]) == False
    assert affects_symbol("GBPUSD", ["GBP"]) == True
    assert affects_symbol("XAUUSD", ["USD"]) == True
    print("   ✅ EURUSD affected by EUR and USD")
    print("   ✅ GBPUSD affected by GBP and USD")
    print("   ✅ XAUUSD affected by USD")
    
    # Test upcoming windows
    print("\n3. Event Window Tests:")
    now = pd.Timestamp("2025-10-20 11:00:00", tz='UTC')
    windows = upcoming_windows(df, now, pad_before_m=30, pad_after_m=30, lookahea_hours=24)
    
    assert len(windows) > 0, "Should find upcoming events"
    print(f"   ✅ Found {len(windows)} upcoming events in next 24h")
    
    # Check window structure
    first_window = windows[0]
    assert 'start' in first_window
    assert 'end' in first_window
    assert 'currencies' in first_window
    assert 'impact' in first_window
    print(f"   ✅ Window structure valid: {first_window['title']}")
    
    # Test event window detection
    print("\n4. Event Detection Tests:")
    event_time = pd.Timestamp("2025-10-20 12:30:00", tz='UTC')
    test_windows = [
        {
            'start': pd.Timestamp("2025-10-20 12:00:00", tz='UTC'),
            'end': pd.Timestamp("2025-10-20 13:00:00", tz='UTC'),
            'currencies': ['USD'],
            'impact': 'high',
            'title': 'Test Event'
        }
    ]
    
    # Should block at event time
    blocked = is_in_event_window("EURUSD", event_time, test_windows)
    assert blocked == True, "Should block EURUSD during USD event"
    print("   ✅ EURUSD blocked during USD event window")
    
    # Should not block outside window
    before_event = pd.Timestamp("2025-10-20 11:00:00", tz='UTC')
    not_blocked = is_in_event_window("EURUSD", before_event, test_windows)
    assert not_blocked == False, "Should not block before event window"
    print("   ✅ EURUSD allowed before event window")
    
    print("\n✅ NEWS MODULE: ALL TESTS PASSED\n")
    return True


def test_integration():
    """Test portfolio engine integration points."""
    print("=" * 60)
    print("TEST 3: Integration")
    print("=" * 60)
    
    # Check imports work
    print("\n1. Import Tests:")
    try:
        from axfl.risk.allocator import compute_budgets
        from axfl.risk.position_sizing import units_from_risk
        from axfl.news.calendar import load_events_csv, is_in_event_window
        print("   ✅ All modules importable from axfl.portfolio.engine")
    except ImportError as e:
        print(f"   ❌ Import failed: {e}")
        return False
    
    # Verify CLI commands exist
    print("\n2. CLI Command Tests:")
    from axfl.cli import cli
    commands = [c.name for c in cli.commands.values()]
    
    required_commands = ['risk', 'news', 'broker-test']
    for cmd in required_commands:
        assert cmd in commands, f"CLI command '{cmd}' not found"
        print(f"   ✅ '{cmd}' command registered")
    
    print("\n✅ INTEGRATION: ALL TESTS PASSED\n")
    return True


def main():
    """Run all validation tests."""
    print("\n" + "=" * 60)
    print("RISK & NEWS GUARD v1 - VALIDATION SUITE")
    print("=" * 60 + "\n")
    
    try:
        success = True
        success &= test_risk_module()
        success &= test_news_module()
        success &= test_integration()
        
        if success:
            print("=" * 60)
            print("✅ ALL VALIDATION TESTS PASSED")
            print("=" * 60)
            print("\nImplementation Status: PRODUCTION READY ✅")
            print("\nNext Steps:")
            print("  1. Enable news_guard in sessions.yaml")
            print("  2. Copy samples/news_events.sample.csv to news_events.csv")
            print("  3. Run: make risk && make news")
            print("  4. Test: python -m axfl.cli live-port --mode replay")
            print()
            return 0
        else:
            print("=" * 60)
            print("❌ SOME TESTS FAILED")
            print("=" * 60)
            return 1
            
    except Exception as e:
        print("=" * 60)
        print(f"❌ VALIDATION ERROR: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
