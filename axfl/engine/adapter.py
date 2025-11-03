# Minimal adapter shim to announce a single "target" for execution.
# For backtests we always use SIM; live trading uses OANDA via scripts/live_trade_oanda.py.
from __future__ import annotations
import os
from typing import Literal

Target = Literal["SIM","OANDA"]

def resolve_target_for_backtest() -> Target:
    # Always SIM for backtests
    return "SIM"

def resolve_target_for_live() -> Target:
    key = os.environ.get("OANDA_API_KEY") or os.environ.get("OANDA_TOKEN")
    acct = os.environ.get("OANDA_ACCOUNT_ID")
    return "OANDA" if (key and acct) else "SIM"

def print_ready(target: Target):
    print(f"ADAPTER_READY target={target}")
