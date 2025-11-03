from __future__ import annotations
import numpy as np, pandas as pd
from .base import Strategy, OrderPlan
from .utils import bbands, atr

class BollingerMeanRev(Strategy):
    name = "bollinger_mean_rev"

    def __init__(
        self, n:int=20, k:float=2.0,
        atr_len:int=14, sl_atr:float=1.2, tp_to_mid:bool=True
    ):
        self.n, self.k = n, k
        self.atr_len, self.sl_atr, self.tp_to_mid = atr_len, sl_atr, tp_to_mid

    def signal(self, df: pd.DataFrame) -> OrderPlan | None:
        """M3-compatible signal method"""
        if len(df) < max(self.n, self.atr_len, 20):
            return None

        ma, up, lo, width = bbands(df['close'], self.n, self.k)
        a_val = atr(df, self.atr_len).iloc[-1]
        c = df['close'].iloc[-1]

        # Triggers
        long_trig = c < lo.iloc[-1]
        short_trig = c > up.iloc[-1]

        # Band expansion filter
        band_expanding = width.iloc[-1] > width.rolling(10).mean().iloc[-1] * 1.25
        if band_expanding:
            return None

        # Width contraction filter
        width_med = width.rolling(20).median().iloc[-1]
        contract = width.iloc[-1] <= width_med * 1.10
        if not contract:
            return None

        if long_trig:
            sl_pips = (self.sl_atr * a_val) / 0.0001
            if self.tp_to_mid:
                tp_price = ma.iloc[-1]
                tp_pips = abs(tp_price - c) / 0.0001
            else:
                tp_pips = (1.8 * a_val) / 0.0001
            return OrderPlan(side=1, sl_pips=sl_pips, tp_pips=tp_pips, tag="BB_low_breach")
        elif short_trig:
            sl_pips = (self.sl_atr * a_val) / 0.0001
            if self.tp_to_mid:
                tp_price = ma.iloc[-1]
                tp_pips = abs(c - tp_price) / 0.0001
            else:
                tp_pips = (1.8 * a_val) / 0.0001
            return OrderPlan(side=-1, sl_pips=sl_pips, tp_pips=tp_pips, tag="BB_upper_breach")

        return None

    def generate(self, df: pd.DataFrame, **_) -> pd.DataFrame:
        out = df.copy()
        ma, up, lo, width = bbands(out['close'], self.n, self.k)
        out['ma'], out['up'], out['lo'], out['width'] = ma, up, lo, width
        out['A'] = atr(out, self.atr_len)

        long_trig  = out['close'] < out['lo']
        short_trig = out['close'] > out['up']

        # Kill when volatility is expanding fast (trend resuming)
        band_expanding = out['width'] > out['width'].rolling(10).mean() * 1.25
        long_trig  &= ~band_expanding
        short_trig &= ~band_expanding

        # Add width contraction filter for better entries
        width_med = out['width'].rolling(20).median()
        contract = out['width'] <= width_med * 1.10
        long_trig &= contract
        short_trig &= contract

        out['signal'] = 0
        out.loc[long_trig, 'signal']  = 1
        out.loc[short_trig, 'signal'] = -1

        out['sl'] = np.where(out['signal']==1, out['close'] - self.sl_atr*out['A'],
                       np.where(out['signal']==-1, out['close'] + self.sl_atr*out['A'], np.nan))
        if self.tp_to_mid:
            out['tp'] = np.where(out['signal']!=0, out['ma'], np.nan)
        else:
            out['tp'] = np.where(out['signal']==1, out['close'] + 1.8*out['A'],
                           np.where(out['signal']==-1, out['close'] - 1.8*out['A'], np.nan))
        out['units'] = np.nan
        out['reason'] = np.where(out['signal']==1, "BB low breach",
                          np.where(out['signal']==-1, "BB upper breach", ""))
        return out[['signal','sl','tp','units','reason']]
