#!/usr/bin/env python3
"""
Send test Discord alerts for visual QA.

Usage:
    python scripts/send_test_alert.py --sample all
    python scripts/send_test_alert.py --sample summary
    python scripts/send_test_alert.py --sample placed
"""

import os
import sys
import argparse
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from axfl.monitor import alerts


def send_order_placed():
    """Send sample order placed alert."""
    ctx = {
        'symbol': 'EURUSD',
        'strategy': 'lsg',
        'side': 'long',
        'units': 1000,
        'entry': 1.09500,
        'sl': 1.09400,
        'tp': 1.09700,
        'tag': 'AXFL::lsg::EURUSD::20251025120000::abc12345',
        'timestamp': datetime.utcnow()
    }
    alerts.alert_order_placed(ctx)
    print("✓ Sent: Order Placed")


def send_order_filled():
    """Send sample order filled alert."""
    ctx = {
        'symbol': 'EURUSD',
        'side': 'long',
        'units': 1000,
        'fill_price': 1.09502,
        'entry': 1.09500,
        'slippage': 0.2,
        'timestamp': datetime.utcnow()
    }
    alerts.alert_order_filled(ctx)
    print("✓ Sent: Order Filled")


def send_order_canceled():
    """Send sample order canceled alert."""
    ctx = {
        'symbol': 'EURUSD',
        'side': 'long',
        'timestamp': datetime.utcnow()
    }
    alerts.alert_order_canceled(ctx, reason="MARKET_HALTED")
    print("✓ Sent: Order Canceled (MARKET_HALTED)")


def send_order_failed():
    """Send sample order failed alert."""
    ctx = {
        'symbol': 'GBPUSD',
        'side': 'short',
        'units': 500,
        'timestamp': datetime.utcnow()
    }
    alerts.alert_order_failed(ctx, error="HTTP 400: Invalid stop loss price")
    print("✓ Sent: Order Failed")


def send_trade_closed():
    """Send sample trade closed alert."""
    # Winning trade
    ctx_win = {
        'symbol': 'EURUSD',
        'strategy': 'lsg',
        'side': 'long',
        'entry': 1.09500,
        'exit': 1.09650,
        'pnl': 15.00,
        'r': 1.5,
        'holding_time': '2h 15m',
        'fees': 0.50,
        'daily_pnl': 23.50,
        'daily_r': 2.1,
        'timestamp': datetime.utcnow()
    }
    alerts.alert_trade_closed(ctx_win)
    print("✓ Sent: Trade Closed (Profit)")
    
    # Losing trade
    ctx_loss = {
        'symbol': 'GBPUSD',
        'strategy': 'orb',
        'side': 'short',
        'entry': 1.25000,
        'exit': 1.25050,
        'pnl': -8.50,
        'r': -1.0,
        'holding_time': '45m',
        'daily_pnl': 15.00,
        'daily_r': 1.1,
        'timestamp': datetime.utcnow()
    }
    alerts.alert_trade_closed(ctx_loss)
    print("✓ Sent: Trade Closed (Loss)")


def send_daily_summary():
    """Send sample daily summary alert."""
    summary = {
        'date': '2025-10-25',
        'total_pnl': 125.50,
        'total_r': 3.5,
        'win_rate': 66.7,
        'trades': 6,
        'best_r': 2.2,
        'worst_r': -1.5,
        'per_symbol_r': {
            'EURUSD': 2.1,
            'GBPUSD': 0.8,
            'XAUUSD': 0.6
        },
        'per_strategy_r': {
            'lsg': 2.5,
            'orb': 0.7,
            'arls': 0.3
        }
    }
    alerts.alert_daily_summary(summary)
    print("✓ Sent: Daily Summary")


def main():
    parser = argparse.ArgumentParser(description='Send test Discord alerts')
    parser.add_argument(
        '--sample',
        choices=['all', 'placed', 'filled', 'canceled', 'failed', 'closed', 'summary'],
        default='all',
        help='Which sample alert(s) to send'
    )
    
    args = parser.parse_args()
    
    # Check webhook URL
    webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
    if not webhook_url:
        print("ERROR: DISCORD_WEBHOOK_URL environment variable not set")
        print("\nSet it with:")
        print("  export DISCORD_WEBHOOK_URL='https://discord.com/api/webhooks/...'")
        sys.exit(1)
    
    print(f"Sending test alerts to Discord...\n")
    
    # Send requested samples
    if args.sample == 'all':
        send_order_placed()
        send_order_filled()
        send_order_canceled()
        send_order_failed()
        send_trade_closed()
        send_daily_summary()
    elif args.sample == 'placed':
        send_order_placed()
    elif args.sample == 'filled':
        send_order_filled()
    elif args.sample == 'canceled':
        send_order_canceled()
    elif args.sample == 'failed':
        send_order_failed()
    elif args.sample == 'closed':
        send_trade_closed()
    elif args.sample == 'summary':
        send_daily_summary()
    
    print(f"\nDone! Check your Discord channel.")


if __name__ == '__main__':
    main()
