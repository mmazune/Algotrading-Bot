from __future__ import annotations
import numpy as np, pandas as pd
from .base import Strategy, OrderPlan
from .utils import ema, atr

class EmaTrend(Strategy):
    name = "ema_trend"

    def __init__(
        self,
        fast:int=10, slow:int=30,
        pullback:int=4,
        atr_len:int=14, sl_atr:float=1.6, tp_atr:float=2.2,
        slope_pips:float=3.0, slope_lookback:int=3
    ):
        self.fast, self.slow = fast, slow
        self.pullback = pullback
        self.atr_len, self.sl_atr, self.tp_atr = atr_len, sl_atr, tp_atr
        self.slope_pips = slope_pips
        self.slope_lookback = slope_lookback

    def signal(self, df: pd.DataFrame) -> OrderPlan | None:
        """M3-compatible signal method"""
        if len(df) < max(self.fast, self.slow, self.atr_len, self.pullback, self.slope_lookback+1):
            return None

        ema_f = ema(df['close'], self.fast)
        ema_s = ema(df['close'], self.slow)
        a_val = atr(df, self.atr_len).iloc[-1]

        # Crossover detection
        cross_up = (ema_f.iloc[-2] <= ema_s.iloc[-2]) and (ema_f.iloc[-1] > ema_s.iloc[-1])
        cross_down = (ema_f.iloc[-2] >= ema_s.iloc[-2]) and (ema_f.iloc[-1] < ema_s.iloc[-1])

        # Pullback confirmation
        pb_long = (df['close'].iloc[-self.pullback:].min() <= ema_f.iloc[-self.pullback:].max())
        pb_short = (df['close'].iloc[-self.pullback:].max() >= ema_f.iloc[-self.pullback:].min())

        # Slope filter
        slope_thr = self.slope_pips * 0.0001
        ema_slope = abs(ema_f.iloc[-1] - ema_f.iloc[-1-self.slope_lookback])
        ema_slope_ok = ema_slope > slope_thr

        if cross_up and pb_long and ema_slope_ok:
            sl_pips = (self.sl_atr * a_val) / 0.0001
            tp_pips = (self.tp_atr * a_val) / 0.0001
            return OrderPlan(side=1, sl_pips=sl_pips, tp_pips=tp_pips, tag="EMA_bull_cross")
        elif cross_down and pb_short and ema_slope_ok:
            sl_pips = (self.sl_atr * a_val) / 0.0001
            tp_pips = (self.tp_atr * a_val) / 0.0001
            return OrderPlan(side=-1, sl_pips=sl_pips, tp_pips=tp_pips, tag="EMA_bear_cross")

        return None

    def generate(self, df: pd.DataFrame, **_) -> pd.DataFrame:
        out = df.copy()
        out['ema_f'] = ema(out['close'], self.fast)
        out['ema_s'] = ema(out['close'], self.slow)
        out['A'] = atr(out, self.atr_len)

        cross_up   = (out['ema_f'].shift(1) <= out['ema_s'].shift(1)) & (out['ema_f'] > out['ema_s'])
        cross_down = (out['ema_f'].shift(1) >= out['ema_s'].shift(1)) & (out['ema_f'] < out['ema_s'])

        pb_long  = (out['close'].rolling(self.pullback).min() <= out['ema_f'].rolling(self.pullback).max())
        pb_short = (out['close'].rolling(self.pullback).max() >= out['ema_f'].rolling(self.pullback).min())

        slope_thr = self.slope_pips * 0.0001
        ema_slope = (out['ema_f'] - out['ema_f'].shift(self.slope_lookback)).abs()
        ema_slope_ok = ema_slope > slope_thr

        long_trig  = cross_up & pb_long & ema_slope_ok
        short_trig = cross_down & pb_short & ema_slope_ok

        out['signal'] = 0
        out.loc[long_trig, 'signal'] = 1
        out.loc[short_trig, 'signal'] = -1

        out['sl'] = np.where(out['signal']==1, out['close'] - self.sl_atr*out['A'],
                       np.where(out['signal']==-1, out['close'] + self.sl_atr*out['A'], np.nan))
        out['tp'] = np.where(out['signal']==1, out['close'] + self.tp_atr*out['A'],
                       np.where(out['signal']==-1, out['close'] - self.tp_atr*out['A'], np.nan))
        out['units'] = np.nan
        out['reason'] = np.where(out['signal']==1, "EMA bull cross+PB",
                          np.where(out['signal']==-1, "EMA bear cross+PB", ""))
        return out[['signal','sl','tp','units','reason']]
