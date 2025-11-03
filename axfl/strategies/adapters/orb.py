from __future__ import annotations
import numpy as np, pandas as pd
from ..base import Strategy, OrderPlan

class ORB(Strategy):
    name = "orb"
    def __init__(self, box_minutes=30, buffer_pips=2.0):
        self.box_minutes = box_minutes
        self.buffer = buffer_pips * 0.0001

    def signal(self, df: pd.DataFrame) -> OrderPlan | None:
        # Legacy placeholder - no signals
        return None

    def generate(self, df: pd.DataFrame, **kw) -> pd.DataFrame:
        out = df.copy()
        # TODO: wire to your real Opening Range Breakout logic.
        out["signal"] = 0
        out["sl"] = np.nan
        out["tp"] = np.nan
        out["units"] = np.nan
        out["reason"] = "ORB placeholder"
        return out[["signal","sl","tp","units","reason"]]

