import os, sys, json, math, argparse
import numpy as np
import pandas as pd

sys.path.append(".")

from axfl.strategies.registry import REGISTRY
from axfl.strategies.utils import position_units_from_risk

PIP = 0.0001

def synth_eurusd(n=1500, seed=42):
    rng = np.random.default_rng(seed)
    dt = pd.date_range("2024-01-01", periods=n, freq="5min")
    steps = rng.normal(0, 0.00025, size=n)  # ~2.5 pips std
    price = 1.08 + np.cumsum(steps)
    close = price
    high = close + rng.uniform(0, 0.0006, size=n)
    low  = close - rng.uniform(0, 0.0006, size=n)
    open_ = np.r_[close[0], close[:-1]]
    df = pd.DataFrame({"open":open_, "high":high, "low":low, "close":close}, index=dt)
    return df

def run_backtest_one(df, strat):
    sig = strat.generate(df).copy().reindex(df.index)
    in_pos = False
    entry = sl = tp = np.nan
    side = 0
    trades = []
    for i in range(len(df)):
        row = df.iloc[i]
        srow = sig.iloc[i]
        if (not in_pos) and (srow["signal"] != 0) and (not math.isnan(srow["sl"])) and (not math.isnan(srow["tp"])):
            in_pos = True
            side = int(srow["signal"])
            entry = row["close"]; sl = float(srow["sl"]); tp = float(srow["tp"])
            for j in range(i+1, len(df)):
                r2 = df.iloc[j]; hit = None
                if side == 1:
                    if r2["high"] >= tp: hit = ("TP", tp, j)
                    elif r2["low"] <= sl: hit = ("SL", sl, j)
                else:
                    if r2["low"] <= tp: hit = ("TP", tp, j)
                    elif r2["high"] >= sl: hit = ("SL", sl, j)
                if hit:
                    tag, exit_price, k = hit
                    risk_pips = (entry - sl)/PIP if side==1 else (sl - entry)/PIP
                    reward_pips = (exit_price - entry)/PIP if side==1 else (entry - exit_price)/PIP
                    R = (reward_pips / risk_pips) if risk_pips>0 else 0.0
                    trades.append({"tag":tag, "R":R}); i = k; break
            in_pos = False; side = 0
    if not trades:
        return {"pf":1.0,"win":0.0,"avgR":0.0,"ddR":0.0,"totalR":0.0,"n":0}
    Rs = [t["R"] for t in trades]
    wins = [r for r in Rs if r>0]; losses = [r for r in Rs if r<=0]
    pf = (sum(wins) / abs(sum(losses))) if losses else float("inf")
    win = (len(wins)/len(Rs))*100.0
    avgR = float(np.mean(Rs))
    eq = np.cumsum(Rs); peak = np.maximum.accumulate(eq); dd = peak - eq
    ddR = float(np.max(dd)) if len(dd)>0 else 0.0
    totalR = float(np.sum(Rs))
    return {"pf":pf,"win":win,"avgR":avgR,"ddR":ddR,"totalR":totalR,"n":len(Rs)}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", type=str, default=None)
    parser.add_argument("--params", type=str, default=None)
    args = parser.parse_args()
    
    df = synth_eurusd()
    
    if args.strategy and args.params:
        # Custom strategy with params
        params = json.loads(args.params)
        strat_class = REGISTRY[args.strategy].__class__
        strat = strat_class(**params)
        keys = [args.strategy]
        custom_registry = {args.strategy: strat}
    else:
        # Default behavior
        keys = ["price_action_breakout","ema_trend","bollinger_mean_rev"]
        custom_registry = REGISTRY
    
    print("=== REGISTRY CHECK ===")
    print("REGISTRY contains:", ", ".join(sorted(REGISTRY.keys())))
    print("=== BACKTEST SUMMARY ===")
    for k in keys:
        res = run_backtest_one(df, custom_registry[k])
        print(f"{k}: PF={res['pf']:.2f} Win%={res['win']:.1f} AvgR={res['avgR']:.2f} MaxDD(R)={res['ddR']:.2f} TotalR={res['totalR']:.2f} Trades={res['n']}")
    print("=== SIZING DEMO ===")
    units = position_units_from_risk(200, 0.01, 1.0800, 1.0780, 0.0001)
    notional = units * 1.0800
    margin_50 = notional/50; margin_200 = notional/200
    print(f"SIZED units={units}, margin@1:50=${margin_50:.2f}, margin@1:200=${margin_200:.2f}, risk$=2.00, stop=20pips")
    print("AXFL_M1_OK"); return 0

if __name__ == "__main__":
    raise SystemExit(main())
