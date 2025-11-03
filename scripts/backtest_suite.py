import os, sys, json, math, csv
import numpy as np
import pandas as pd

sys.path.append(".")

from axfl.strategies.price_action_breakout import PriceActionBreakout
from axfl.strategies.ema_trend import EmaTrend
from axfl.strategies.bollinger_mean_rev import BollingerMeanRev

PIP = 0.0001

def synth_eurusd(n=1500, seed=42):
    rng = np.random.default_rng(seed)
    dt = pd.date_range("2024-01-01", periods=n, freq="5min")
    steps = rng.normal(0, 0.00025, size=n)
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
        return {"pf":0.0,"win":0.0,"avgR":0.0,"ddR":0.0,"totalR":0.0,"n":0}
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
    df = synth_eurusd()
    
    grids = {
        "price_action_breakout": [
            {"lookback":12,"buffer_pips":0.5,"min_break_pips":3,"min_atr_pips":2,"use_htf_filter":False},
            {"lookback":20,"buffer_pips":0.5,"min_break_pips":3,"min_atr_pips":2,"use_htf_filter":False},
            {"lookback":15,"buffer_pips":0.8,"min_break_pips":4,"min_atr_pips":2,"use_htf_filter":False},
            {"lookback":15,"buffer_pips":0.5,"min_break_pips":3,"min_atr_pips":2,"use_htf_filter":False},
            {"lookback":18,"buffer_pips":0.6,"min_break_pips":3,"min_atr_pips":2,"use_htf_filter":False},
        ],
        "ema_trend": [
            {"fast":10,"slow":30,"pullback":4,"slope_pips":3.0},
            {"fast":12,"slow":35,"pullback":4,"slope_pips":3.0},
            {"fast":15,"slow":40,"pullback":5,"slope_pips":3.5},
            {"fast":8,"slow":25,"pullback":3,"slope_pips":2.5},
            {"fast":10,"slow":28,"pullback":4,"slope_pips":3.0},
        ],
        "bollinger_mean_rev": [
            {"n":20,"k":2.0},
            {"n":18,"k":2.0},
            {"n":22,"k":2.2},
            {"n":20,"k":1.8},
            {"n":24,"k":2.0},
        ],
    }
    
    results = []
    best_per_strategy = {}
    
    for strat_name, param_list in grids.items():
        best = None
        for params in param_list:
            if strat_name == "price_action_breakout":
                strat = PriceActionBreakout(**params)
            elif strat_name == "ema_trend":
                strat = EmaTrend(**params)
            elif strat_name == "bollinger_mean_rev":
                strat = BollingerMeanRev(**params)
            else:
                continue
            
            res = run_backtest_one(df, strat)
            results.append({
                "strategy": strat_name,
                "params_json": json.dumps(params),
                "pf": res["pf"],
                "win": res["win"],
                "avgR": res["avgR"],
                "ddR": res["ddR"],
                "totalR": res["totalR"],
                "trades": res["n"]
            })
            
            if best is None:
                best = (res, params)
            else:
                # Compare: higher PF, then higher totalR, then more trades
                better = False
                if res["pf"] > best[0]["pf"] + 0.01:
                    better = True
                elif abs(res["pf"] - best[0]["pf"]) <= 0.01:
                    if res["totalR"] > best[0]["totalR"] + 0.1:
                        better = True
                    elif abs(res["totalR"] - best[0]["totalR"]) <= 0.1 and res["n"] > best[0]["n"]:
                        better = True
                if better:
                    best = (res, params)
        
        best_per_strategy[strat_name] = best
    
    # Write CSV
    os.makedirs("reports", exist_ok=True)
    with open("reports/m2_grid_results.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["strategy","params_json","pf","win","avgR","ddR","totalR","trades"])
        writer.writeheader()
        writer.writerows(results)
    
    # Print best per strategy
    for strat_name in ["price_action_breakout", "ema_trend", "bollinger_mean_rev"]:
        res, params = best_per_strategy[strat_name]
        print(f"M2 {strat_name} best PF={res['pf']:.2f} Win%={res['win']:.1f} Trades={res['n']} Params={json.dumps(params)}")
    
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
