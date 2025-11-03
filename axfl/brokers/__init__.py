"""
Broker adapters for live trading execution.

This module provides broker integrations for mirroring AXFL paper trades
to real/practice accounts. All adapters are best-effort - AXFL remains
the source of truth for PnL tracking.
"""

from .oanda_api import OandaClient, fetch_oanda_candles, oanda_detect


__all__ = ['OandaPractice']
