import os, json, math
import pandas as pd
from pathlib import Path
import numpy as np

from axfl.engine.executor import run_sim
from axfl.strategies.registry import REGISTRY

def load_df(path:str) -> pd.DataFrame:
    if not Path(path).exists():
        # fallback: small synthetic
        idx = pd.date_range("2024-03-01", periods=3000, freq="5min", tz="UTC")
        rng = np.random.default_rng(42)
        close = 1.08 + rng.normal(0, 0.00022, size=len(idx)).cumsum()
        high = close + rng.uniform(0, 0.0006, size=len(idx))
        low  = close - rng.uniform(0, 0.0006, size=len(idx))
        open_ = np.r_[close[0], close[:-1]]
        return pd.DataFrame({"open":open_,"high":high,"low":low,"close":close}, index=idx)
    df = pd.read_csv(path)
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df = df.set_index("time")
    return df

def score(M:dict) -> tuple:
    # higher PF, then higher TotalR, then more Trades
    pf = M.get("pf",0.0); tr = M.get("totalR",0.0); n = M.get("n",0)
    return (pf, tr, n)

def main():
    os.makedirs("reports", exist_ok=True)
    instr = os.environ.get("OANDA_INSTR","EUR_USD")
    # find a data file in /data
    candidates = sorted(Path("data").glob(f"{instr}_M5_*.csv"))
    path = str(candidates[-1]) if candidates else f"data/{instr}_M5_synth.csv"
    df = load_df(path)

    spread_grid = [float(x) for x in os.environ.get("AXFL_SPREAD_GRID","0.1,0.2,0.3").split(",")]
    slip_grid   = [float(x) for x in os.environ.get("AXFL_SLIP_GRID","0.0,0.1,0.2").split(",")]

    names = ["ema_trend","bollinger_mean_rev","price_action_breakout"]
    rows = []
    best = None
    best_key = None

    for sp in spread_grid:
        for sl in slip_grid:
            os.environ["AXFL_SPREAD_PIPS"] = str(sp)
            os.environ["AXFL_SLIPPAGE_PIPS"] = str(sl)
            _, fills, M, _ = run_sim(df, names, balance=200.0, risk_pct=0.01)
            rows.append(dict(spread_pips=sp, slippage_pips=sl, **M))
            key = (M["pf"], M["totalR"], M["n"])
            if (best is None) or (key > best_key):
                best, best_key = (sp, sl, M), key

    pd.DataFrame(rows).to_csv("reports/m7_calibration.csv", index=False)

    # final backtest with best settings
    if best is None:
        print("M7_CALIB best spread_pips=NA slippage_pips=NA PF=NA Win%=NA Trades=0")
        print(f"M7_BACKTEST instrument={instr} PF=NA Win%=NA Trades=0 TotalR=NA file=reports/m7_calibration.csv")
        return

    sp, sl, M = best
    os.environ["AXFL_SPREAD_PIPS"] = str(sp)
    os.environ["AXFL_SLIPPAGE_PIPS"] = str(sl)
    _, fills2, M2, _ = run_sim(df, names, balance=200.0, risk_pct=0.01)
    print(f"M7_CALIB best spread_pips={sp} slippage_pips={sl} PF={M['pf']:.2f} Win%={M['win']:.1f} Trades={M['n']}")
    print(f"M7_BACKTEST instrument={instr} PF={M2['pf']:.2f} Win%={M2['win']:.1f} Trades={M2['n']} TotalR={M2['totalR']:.2f} file=reports/m7_calibration.csv")

if __name__ == "__main__":
    main()
