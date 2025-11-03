from __future__ import annotations
from dataclasses import dataclass
from abc import ABC, abstractmethod
import pandas as pd

@dataclass
class OrderPlan:
    side: int          # +1 long, -1 short, 0 flat
    sl_pips: float     # risk in pips (for execution engine)
    tp_pips: float     # reward in pips (for execution engine)
    tag: str = ""      # strategy label
    # Legacy fields for compatibility with old generate() methods
    sl: float | None = None   # price
    tp: float | None = None   # price
    units: int | None = None  # OANDA uses units, can be negative for short
    reason: str = ""

class Strategy(ABC):
    name: str
    @abstractmethod
    def generate(self, df: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """
        Return df with columns:
          - signal: {1,-1,0}
          - sl, tp: floats (price) or NaN
          - units: int (optional; engine may size at execution)
          - reason: string (optional)
        Expects df with 'open','high','low','close' (UTC-indexed).
        """
        ...
