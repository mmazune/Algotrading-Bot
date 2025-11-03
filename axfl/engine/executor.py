from __future__ import annotations
import json, os
import pandas as pd
from typing import Dict, List, Optional
from axfl.strategies.registry import REGISTRY
from axfl.strategies.utils import position_units_from_risk
from .broker_sim import SimBroker
from .broker_base import Order, Fill
from .risk import RiskConfig, allow_entry
from axfl.brokers import OandaClient, fetch_oanda_candles, oanda_detect

PIP = 0.0001

def _synth_eurusd(n=2200, seed=7):
    import numpy as np, pandas as pd
    rng = np.random.default_rng(seed)
    dt = pd.date_range("2024-01-02", periods=n, freq="5min")
    steps = rng.normal(0, 0.00022, size=n)
    close = 1.082 + steps.cumsum()
    high = close + rng.uniform(0, 0.0006, size=n)
    low  = close - rng.uniform(0, 0.0006, size=n)
    open_ = pd.Series(close).shift(1).fillna(close[0]).values
    return pd.DataFrame({"open":open_, "high":high, "low":low, "close":close}, index=dt)

def maybe_oanda_df() -> (str, pd.DataFrame, Optional[str], Optional[str]):
    key, acct, env = oanda_detect()
    instr = os.environ.get("OANDA_INSTR","EUR_USD")
    if not key or not acct:
        return ("SIM", _synth_eurusd(), None, None)
    cli = OandaClient(key, acct, env)
    code, _ = cli.account_summary()
    if code != 200:
        return ("SIM", _synth_eurusd(), None, None)
    code, df = fetch_oanda_candles(cli, instrument=instr, granularity="M5", count=1500)
    if code != 200 or df.empty:
        return ("SIM", _synth_eurusd(), None, None)
    return ("OANDA", df, acct, env)

def _metrics(fills: List[Fill]) -> Dict[str, float]:
    import numpy as np
    if not fills:
        return dict(pf=1.0, win=0.0, avgR=0.0, ddR=0.0, totalR=0.0, n=0, pnl=0.0)
    R = [f.r_multiple for f in fills]
    wins = [x for x in R if x>0]; losses = [x for x in R if x<=0]
    pf = (sum(wins)/abs(sum(losses))) if losses else float("inf")
    win = 100.0*len(wins)/len(R)
    avgR = float(sum(R)/len(R))
    eq = pd.Series(R).cumsum()
    ddR = float((eq.cummax()-eq).max()) if len(eq)>0 else 0.0
    totalR = float(sum(R))
    pnl = float(sum(f.pnl_usd for f in fills))
    return dict(pf=pf, win=win, avgR=avgR, ddR=ddR, totalR=totalR, n=len(R), pnl=pnl)

def run_sim(
    df: pd.DataFrame,
    strat_names: List[str],
    balance: float = 200.0,
    risk_pct: float = 0.01,
    pip_value_per_unit: float = 0.0001,
    first_order_marker: bool = True,
    risk_cfg: Optional[RiskConfig] = None,
):
    risk_cfg = risk_cfg or RiskConfig(risk_pct=risk_pct)
    strategies = {n: REGISTRY[n]() for n in strat_names}
    sigs = {n: s.generate(df).reindex(df.index) for n, s in strategies.items()}
    spread_pips = float(os.environ.get("AXFL_SPREAD_PIPS","0.2"))
    slippage_pips = float(os.environ.get("AXFL_SLIPPAGE_PIPS","0.1"))
    broker = SimBroker(risk_dollars=balance*risk_pct, spread_pips=spread_pips, slippage_pips=slippage_pips)
    fills_all: List[Fill] = []
    first_order_line = None
    eq_R = 0.0
    open_positions = 0

    for i in range(2, len(df)):
        row = df.iloc[i]
        # advance any open pos
        if broker.pos is not None:
            newfills = broker.step_bar(row["high"], row["low"], row["close"])
            if newfills:
                for f in newfills:
                    eq_R += f.r_multiple
                open_positions = 0
            fills_all += newfills
            continue

        # risk guard
        if not allow_entry(df, i, eq_R, open_positions, risk_cfg):
            continue

        for name in strat_names:
            sig = sigs[name].iloc[i]
            if sig["signal"] == 0 or pd.isna(sig["sl"]) or pd.isna(sig["tp"]):
                continue
            entry = float(row["close"]); sl = float(sig["sl"]); tp = float(sig["tp"])
            units = position_units_from_risk(balance=balance, risk_pct=risk_cfg.risk_pct,
                                             entry=entry, sl=sl, pip_value_per_unit=pip_value_per_unit)
            if units <= 0:
                continue
            side = int(sig["signal"])
            pos = broker.place(Order(side=side, units=units, entry=entry, sl=sl, tp=tp, tag=name))
            open_positions = 1
            if first_order_marker and first_order_line is None:
                first_order_line = f"FIRST_ORDER id={pos.order_id} side={side} units={units} entry={entry:.5f} sl={sl:.5f} tp={tp:.5f} tag={name}"
            break

        fills_all += broker.step_bar(row["high"], row["low"], row["close"])
        if fills_all and fills_all[-1].order_id:
            # update equity when fills happen
            pass

    if broker.pos is not None:
        last = df.iloc[-1]
        newfills = broker.close_all(last["close"])
        for f in newfills:
            eq_R += f.r_multiple
        fills_all += newfills

    M = _metrics(fills_all)
    return strategies, fills_all, M, first_order_line

# expose a convenience that auto-selects OANDA vs SIM
def run_auto(strat_names: List[str], balance: float = 200.0, risk_pct: float = 0.01):
    mode, df, acct, env = maybe_oanda_df()
    risk_cfg = RiskConfig(risk_pct=risk_pct)
    strategies, fills, M, first_line = run_sim(df, strat_names, balance=balance, risk_pct=risk_pct, risk_cfg=risk_cfg)
    return mode, acct, env, strategies, fills, M, first_line

# Legacy function for M3 compatibility
def run_sim_legacy(df: pd.DataFrame, strat, broker: SimBroker,
            base_risk_pct: float = 0.02, account_usd: float = 10_000.0) -> pd.DataFrame:
    """
    Wire strategies -> orders -> broker fills
      - df must have columns: time, open, high, low, close
      - strat emits OrderPlan(side, sl_pips, tp_pips, tag)
      - We convert to Order(side, units, entry, sl, tp, tag)
      - Broker checks TP/SL on each bar
    """
    equity_rows = []
    for i in range(len(df)):
        # Extract bar
        row = df.iloc[i]
        h, l, c = row["high"], row["low"], row["close"]

        # Step broker for existing position
        fills = broker.step_bar(h, l, c)

        # Ask strategy for new signal (if no position)
        if broker.pos is None:
            snippet = df.iloc[max(0, i-100):i+1]
            plan = strat.signal(snippet)
            if plan is not None:
                # position sizing
                risk_dollars = account_usd * base_risk_pct
                risk_pips = plan.sl_pips
                reward_pips = plan.tp_pips
                if risk_pips > 0:
                    pip_value = 0.10  # For EUR/USD mini-lot = $0.10/pip
                    units = int(risk_dollars / (risk_pips * pip_value))
                    # build SL/TP
                    entry = c
                    if plan.side == 1:
                        sl_price = c - plan.sl_pips*PIP
                        tp_price = c + plan.tp_pips*PIP
                    else:
                        sl_price = c + plan.sl_pips*PIP
                        tp_price = c - plan.tp_pips*PIP

                    order = Order(side=plan.side, units=units, entry=entry,
                                  sl=sl_price, tp=tp_price, tag=plan.tag or "")
                    try:
                        broker.place(order)
                    except Exception:
                        pass  # If already open, skip

        # Track equity
        equity_rows.append({"bar": i, "unrealized": 0.0, "realized": sum(f.pnl_usd for f in broker.realized())})

    # Force close any open position
    if len(df) > 0:
        last_c = df.iloc[-1]["close"]
        broker.close_all(last_c)

    return pd.DataFrame(equity_rows)
