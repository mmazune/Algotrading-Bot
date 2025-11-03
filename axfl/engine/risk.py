from __future__ import annotations
from dataclasses import dataclass
import pandas as pd

@dataclass
class RiskConfig:
    risk_pct: float = 0.01
    daily_stop_R: float = 4.0
    max_open_positions: int = 1
    atr_guard_len: int = 14
    atr_guard_min_pips: float = 3.0  # if ATR below this, skip entries (too quiet)

def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    tr = (h - l).abs().combine((h - c.shift()).abs(), max).combine((l - c.shift()).abs(), max)
    return tr.rolling(n).mean()

def allow_entry(df: pd.DataFrame, i: int, eq_R: float, open_positions: int, cfg: RiskConfig) -> bool:
    if abs(eq_R) >= cfg.daily_stop_R:
        return False
    if open_positions >= cfg.max_open_positions:
        return False
    A = atr(df, cfg.atr_guard_len)
    thr = cfg.atr_guard_min_pips * 0.0001
    if pd.isna(A.iloc[i]) or A.iloc[i] < thr:
        return False
    return True
