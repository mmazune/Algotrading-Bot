"""
Broker adapters for live trading execution.

This module provides broker integrations for mirroring AXFL paper trades
to real/practice accounts. All adapters are best-effort - AXFL remains
the source of truth for PnL tracking.
"""

from axfl.brokers.oanda import OandaPractice

__all__ = ['OandaPractice']
