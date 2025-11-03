"""
vol_contraction.py - Volatility contraction strategy with ATR-based range filter
"""
from __future__ import annotations
import numpy as np, pandas as pd
from .base import Strategy
from .utils import atr

class VolatilityContraction(Strategy):
    name = "volatility_contraction"
    def __init__(
        self,
        atr_len:int=14, atr_pctile:float=35.0,
        lookback:int=10,
        buffer_pips:float=1.0,
        sl_atr:float=1.2, tp_atr:float=1.8,
        min_range_pips:float=4.0,
        min_range_atr_frac:float=0.40,  # require range <= max(min_range_pips, 0.4*ATR pips)
    ):
        self.atr_len, self.atr_pctile = atr_len, atr_pctile
        self.lookback = lookback
        self.buffer_pips = buffer_pips
        self.sl_atr, self.tp_atr = sl_atr, tp_atr
        self.min_range_pips = min_range_pips
        self.min_range_atr_frac = min_range_atr_frac

    def generate(self, df: pd.DataFrame, **_) -> pd.DataFrame:
        out = df.copy()
        out["A"] = atr(out, self.atr_len)
        thr = out["A"].rolling(100).quantile(self.atr_pctile/100.0)
        contract = out["A"] <= thr

        rng_hi = out["high"].rolling(self.lookback).max()
        rng_lo = out["low"].rolling(self.lookback).min()
        rng_w = (rng_hi - rng_lo)

        atr_pips = (out["A"] / 0.0001).clip(lower=0)
        min_floor = np.maximum(self.min_range_pips, self.min_range_atr_frac * atr_pips) * 0.0001
        rng_ok = rng_w <= min_floor

        buffer = self.buffer_pips * 0.0001
        long_trig  = contract & rng_ok & (out["close"] > (rng_hi + buffer))
        short_trig = contract & rng_ok & (out["close"] < (rng_lo - buffer))

        out["signal"] = 0
        out.loc[long_trig, "signal"] = 1
        out.loc[short_trig, "signal"] = -1

        out["sl"] = np.where(out["signal"]==1, out["close"] - self.sl_atr*out["A"],
                       np.where(out["signal"]==-1, out["close"] + self.sl_atr*out["A"], np.nan))
        out["tp"] = np.where(out["signal"]==1, out["close"] + self.tp_atr*out["A"],
                       np.where(out["signal"]==-1, out["close"] - self.tp_atr*out["A"], np.nan))
        out["units"] = np.nan
        out["reason"] = np.where(out["signal"]==1, "VC breakout up",
                           np.where(out["signal"]==-1, "VC breakout down", ""))
        return out[["signal","sl","tp","units","reason"]]
