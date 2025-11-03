from __future__ import annotations
import numpy as np
import pandas as pd

def ema(a: pd.Series, n: int) -> pd.Series:
    return a.ewm(span=n, adjust=False).mean()

def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df['high'], df['low'], df['close']
    tr = np.maximum(h - l, np.maximum((h - c.shift()).abs(), (l - c.shift()).abs()))
    return tr.rolling(n).mean()

def bbands(s: pd.Series, n: int = 20, k: float = 2.0):
    ma = s.rolling(n).mean()
    sd = s.rolling(n).std(ddof=0)
    upper, lower = ma + k * sd, ma - k * sd
    return ma, upper, lower, (upper - lower)

def position_units_from_risk(
    balance: float,
    risk_pct: float,
    entry: float,
    sl: float,
    pip_value_per_unit: float = 0.0001,  # ~EURUSD per-unit pip value if acct in USD
) -> int:
    if sl is None or np.isnan(sl) or entry is None or np.isnan(entry):
        return 0
    stop_pips = abs(entry - sl) / 0.0001
    if stop_pips <= 0:
        return 0
    units = int(np.floor((balance * risk_pct) / (stop_pips * pip_value_per_unit)))
    return max(units, 0)
