import os, json
import numpy as np, pandas as pd
from pathlib import Path
from axfl.strategies.session_breakout import SessionBreakout
from axfl.strategies.vol_contraction import VolatilityContraction
from axfl.engine.broker_sim import SimBroker
from axfl.strategies.utils import position_units_from_risk

def _load_latest(instr="EUR_USD"):
    cand = sorted(Path("data").glob(f"{instr}_M5_*.csv"))
    if cand:
        df = pd.read_csv(cand[-1])
        if "time" in df.columns:
            df["time"] = pd.to_datetime(df["time"], utc=True)
            df = df.set_index("time")
        return df
    # fallback small synth
    idx = pd.date_range("2024-04-01", periods=500, freq="5min", tz="UTC")
    rng = np.random.default_rng(21)
    close = 1.09 + rng.normal(0, 0.00022, size=len(idx)).cumsum()
    high = close + rng.uniform(0, 0.0006, size=len(idx))
    low  = close - rng.uniform(0, 0.0006, size=len(idx))
    open_ = np.r_[close[0], close[:-1]]
    return pd.DataFrame({"open":open_,"high":high,"low":low,"close":close}, index=idx)

def _quick_backtest(df, strat, balance=200.0, risk_pct=0.01):
    sig = strat.generate(df).reindex(df.index)
    broker = SimBroker(risk_dollars=balance*risk_pct, spread_pips=0.2, slippage_pips=0.1)
    fills = []
    for i in range(2, len(df)):
        row = df.iloc[i]
        if broker.pos:
            newfills = broker.step_bar(row["high"], row["low"], row["close"])
            fills += newfills
            continue
        s = sig.iloc[i]
        if s["signal"]==0 or pd.isna(s["sl"]) or pd.isna(s["tp"]): continue
        entry, sl, tp = float(row["close"]), float(s["sl"]), float(s["tp"])
        units = position_units_from_risk(balance, risk_pct, entry, sl, 0.0001)
        if units<=0: continue
        from axfl.engine.broker_base import Order
        broker.place(Order(int(s["signal"]), units, entry, sl, tp, "test"))
        fills += broker.step_bar(row["high"], row["low"], row["close"])
    if broker.pos:
        fills += broker.close_all(df["close"].iloc[-1])
    
    if not fills: return {"pf":0.0,"win":0.0,"avgR":0.0,"ddR":0.0,"totalR":0.0,"n":0,"pnl":0.0}
    R = [f.r_multiple for f in fills]
    wins = [x for x in R if x>0]; losses = [x for x in R if x<=0]
    pf = (sum(wins)/abs(sum(losses))) if losses else (999.0 if wins else 0.0)
    return {"pf":pf,"win":100.0*len(wins)/len(R),"avgR":sum(R)/len(R),
            "ddR":float((pd.Series(R).cumsum().cummax()-pd.Series(R).cumsum()).max()),
            "totalR":sum(R),"n":len(R),"pnl":sum(f.pnl_usd for f in fills)}

def main():
    os.makedirs("reports", exist_ok=True)
    df = _load_latest(os.environ.get("OANDA_INSTR","EUR_USD"))

    grids = {
      "session_breakout": [
        {"start_hhmm":0,"end_hhmm":500,"buffer_pips":2.0,"use_dynamic_buffer":True,"dyn_buffer_atr_frac":0.20,"sl_atr":1.4,"tp_atr":2.0},
        {"start_hhmm":600,"end_hhmm":800,"buffer_pips":2.0,"use_dynamic_buffer":True,"dyn_buffer_atr_frac":0.20,"sl_atr":1.4,"tp_atr":2.1},
        {"start_hhmm":0,"end_hhmm":500,"buffer_pips":1.5,"use_dynamic_buffer":True,"dyn_buffer_atr_frac":0.25,"sl_atr":1.5,"tp_atr":2.2},
      ],
      "volatility_contraction": [
        {"atr_pctile":35.0,"lookback":10,"buffer_pips":1.0,"sl_atr":1.2,"tp_atr":1.8,"min_range_atr_frac":0.40},
        {"atr_pctile":30.0,"lookback":12,"buffer_pips":1.2,"sl_atr":1.2,"tp_atr":1.9,"min_range_atr_frac":0.45},
        {"atr_pctile":40.0,"lookback":9,"buffer_pips":0.8,"sl_atr":1.1,"tp_atr":1.7,"min_range_atr_frac":0.35},
      ]
    }

    results = []; best = {}
    for name in ["session_breakout", "volatility_contraction"]:
        Cls = SessionBreakout if name=="session_breakout" else VolatilityContraction
        best_key = None; best_row = None
        for p in grids[name]:
            M = _quick_backtest(df, Cls(**p))
            row = {"strategy":name, "params":json.dumps(p, separators=(',',':'))}
            row.update(M)
            results.append(row)
            key = (M["pf"], M["totalR"], M["n"])
            if (best_key is None) or (key > best_key):
                best_key, best_row = key, row
        best[name] = best_row

    pd.DataFrame(results).to_csv("reports/m9_tune_results.csv", index=False)
    sb, vc = best["session_breakout"], best["volatility_contraction"]
    print(f"M9_TUNE session_breakout best PF={sb['pf']:.2f} Win%={sb['win']:.1f} Trades={int(sb['n'])} Params={sb['params']}")
    print(f"M9_TUNE volatility_contraction best PF={vc['pf']:.2f} Win%={vc['win']:.1f} Trades={int(vc['n'])} Params={vc['params']}")

if __name__ == "__main__":
    main()

