"""
session_breakout.py - Session range breakout strategy with dynamic buffer
"""
from __future__ import annotations
import numpy as np, pandas as pd
from .base import Strategy
from .utils import atr

class SessionBreakout(Strategy):
    name = "session_breakout"
    def __init__(
        self,
        start_hhmm:int=0, end_hhmm:int=500,
        buffer_pips:float=2.0,
        atr_len:int=14, sl_atr:float=1.4, tp_atr:float=2.0,
        min_range_pips:float=6.0,
        use_dynamic_buffer:bool=True,
        dyn_buffer_atr_frac:float=0.20,  # 20% of ATR (in pips)
        cool_minutes:int=30              # advisory only; live runner enforces
    ):
        self.start, self.end = start_hhmm, end_hhmm
        self.buffer_pips = buffer_pips
        self.atr_len, self.sl_atr, self.tp_atr = atr_len, sl_atr, tp_atr
        self.min_rng = min_range_pips*0.0001
        self.use_dynamic_buffer = use_dynamic_buffer
        self.dyn_buffer_atr_frac = dyn_buffer_atr_frac
        self.cool_minutes = cool_minutes

    def _hhmm(self, ts: pd.Timestamp) -> int:
        ts = ts.tz_convert("UTC") if ts.tzinfo else ts.tz_localize("UTC")
        return ts.hour*100 + ts.minute

    def generate(self, df: pd.DataFrame, **_) -> pd.DataFrame:
        out = df.copy()
        out["A"] = atr(out, self.atr_len)
        # dynamic buffer (pips -> price)
        atr_pips = (out["A"] / 0.0001).clip(lower=0)
        dyn_buf = (self.dyn_buffer_atr_frac * atr_pips).fillna(0)
        buf_pips = np.maximum(self.buffer_pips, dyn_buf)
        buffer = buf_pips * 0.0001

        idx = out.index
        hhmm = pd.Series([self._hhmm(t) for t in idx], index=idx)
        is_in = (hhmm >= self.start) & (hhmm <= self.end)

        # session highs/lows per day
        day = pd.to_datetime(idx, utc=True).date
        day_series = pd.Series(day, index=idx)
        shigh = pd.Series(np.nan, index=idx)
        slow  = pd.Series(np.nan, index=idx)
        for d in np.unique(day_series.values):
            mask = (day_series==d) & is_in
            if mask.any():
                shigh.loc[mask] = out.loc[mask, "high"].cummax()
                slow.loc[mask]  = out.loc[mask, "low"].cummin()
        sh, sl = shigh.ffill(), slow.ffill()

        after = hhmm > self.end
        rng = (sh - sl)
        rng_ok = rng >= self.min_rng

        long_trig  = after & rng_ok & (out["close"] > (sh + buffer))
        short_trig = after & rng_ok & (out["close"] < (sl - buffer))

        out["signal"] = 0
        out.loc[long_trig, "signal"] = 1
        out.loc[short_trig, "signal"] = -1

        out["sl"] = np.where(out["signal"]==1, out["close"] - self.sl_atr*out["A"],
                       np.where(out["signal"]==-1, out["close"] + self.sl_atr*out["A"], np.nan))
        out["tp"] = np.where(out["signal"]==1, out["close"] + self.tp_atr*out["A"],
                       np.where(out["signal"]==-1, out["close"] - self.tp_atr*out["A"], np.nan))
        out["units"] = np.nan
        out["reason"] = np.where(out["signal"]==1, "Session high break",
                           np.where(out["signal"]==-1, "Session low break", ""))
        return out[["signal","sl","tp","units","reason"]]
