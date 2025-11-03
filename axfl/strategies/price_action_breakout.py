from __future__ import annotations
import numpy as np, pandas as pd
from .base import Strategy, OrderPlan
from .utils import atr, ema

class PriceActionBreakout(Strategy):
    name = "price_action_breakout"

    def __init__(
        self,
        lookback:int=15,
        buffer_pips:float=0.5,
        atr_len:int=14,
        sl_atr:float=1.5,
        tp_atr:float=2.5,
        htf_fast:int=50,
        htf_slow:int=200,
        use_htf_filter:bool=False,
        min_break_pips:int=3,
        min_atr_pips:int=2,
    ):
        self.lookback = lookback
        self.buffer = buffer_pips*0.0001
        self.atr_len = atr_len
        self.sl_atr = sl_atr
        self.tp_atr = tp_atr
        self.htf_fast = htf_fast
        self.htf_slow = htf_slow
        self.use_htf_filter = use_htf_filter
        self.min_break = min_break_pips * 0.0001
        self.min_atr = min_atr_pips * 0.0001

    def signal(self, df: pd.DataFrame) -> OrderPlan | None:
        """M3-compatible signal method - returns OrderPlan for last bar"""
        if len(df) < max(self.lookback, self.atr_len):
            return None
        
        row = df.iloc[-1]
        hh = df['high'].iloc[-self.lookback:].max()
        ll = df['low'].iloc[-self.lookback:].min()
        a_val = atr(df, self.atr_len).iloc[-1]

        # Filters
        rng_ok = (hh - ll) >= self.min_break
        atr_ok = a_val >= self.min_atr
        if not (rng_ok and atr_ok):
            return None

        # Trend filter (optional)
        if self.use_htf_filter:
            ema_f = ema(df['close'], self.htf_fast).iloc[-1]
            ema_s = ema(df['close'], self.htf_slow).iloc[-1]
            bias = 1 if ema_f > ema_s else -1
        else:
            bias = 0

        # Breakout logic
        c = row['close']
        long_trig = (c > hh + self.buffer)
        short_trig = (c < ll - self.buffer)

        if self.use_htf_filter:
            long_trig = long_trig and (bias == 1)
            short_trig = short_trig and (bias == -1)

        if long_trig:
            sl_pips = (self.sl_atr * a_val) / 0.0001
            tp_pips = (self.tp_atr * a_val) / 0.0001
            return OrderPlan(side=1, sl_pips=sl_pips, tp_pips=tp_pips, tag="HH_breakout")
        elif short_trig:
            sl_pips = (self.sl_atr * a_val) / 0.0001
            tp_pips = (self.tp_atr * a_val) / 0.0001
            return OrderPlan(side=-1, sl_pips=sl_pips, tp_pips=tp_pips, tag="LL_breakout")
        
        return None

    def generate(self, df: pd.DataFrame, **_) -> pd.DataFrame:
        out = df.copy()
        out['hh'] = out['high'].rolling(self.lookback).max()
        out['ll'] = out['low'].rolling(self.lookback).min()
        out['A'] = atr(out, self.atr_len)

        if self.use_htf_filter:
            out['ema_fast'] = ema(out['close'], self.htf_fast)
            out['ema_slow'] = ema(out['close'], self.htf_slow)
            out['bias'] = np.where(out['ema_fast'] > out['ema_slow'], 1, -1)
        else:
            out['bias'] = 0

        rng_ok = (out['hh'] - out['ll']) >= self.min_break
        atr_ok = out['A'] >= self.min_atr

        long_trig  = (out['close'] > (out['hh'] + self.buffer))
        short_trig = (out['close'] < (out['ll'] - self.buffer))

        if self.use_htf_filter:
            long_trig  &= (out['bias'] == 1)
            short_trig &= (out['bias'] == -1)

        long_trig  &= rng_ok & atr_ok
        short_trig &= rng_ok & atr_ok

        out['signal'] = 0
        out.loc[long_trig, 'signal'] = 1
        out.loc[short_trig, 'signal'] = -1

        out['sl'] = np.where(
            out['signal'] == 1, out['close'] - self.sl_atr * out['A'],
            np.where(out['signal'] == -1, out['close'] + self.sl_atr * out['A'], np.nan)
        )
        out['tp'] = np.where(
            out['signal'] == 1, out['close'] + self.tp_atr * out['A'],
            np.where(out['signal'] == -1, out['close'] - self.tp_atr * out['A'], np.nan)
        )
        out['units'] = np.nan
        out['reason'] = np.where(out['signal']==1, "HH breakout",
                          np.where(out['signal']==-1, "LL breakout", ""))
        return out[['signal','sl','tp','units','reason']]
