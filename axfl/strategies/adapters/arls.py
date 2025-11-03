from __future__ import annotations
import numpy as np, pandas as pd
from ..base import Strategy, OrderPlan

class ARLS(Strategy):
    name = "arls"
    def __init__(self): pass

    def signal(self, df: pd.DataFrame) -> OrderPlan | None:
        # Legacy placeholder - no signals
        return None

    def generate(self, df: pd.DataFrame, **kw) -> pd.DataFrame:
        out = df.copy()
        # TODO: call your real ARLS logic here; this is a safe placeholder
        out["signal"] = 0
        out["sl"] = np.nan
        out["tp"] = np.nan
        out["units"] = np.nan
        out["reason"] = "ARLS placeholder"
        return out[["signal","sl","tp","units","reason"]]

