import os, json, math, datetime as dt
from pathlib import Path
import pandas as pd
from axfl.brokers.oanda_api import oanda_detect, OandaClient, fetch_oanda_candles

def daterange_utc(days:int):
    # list of (from_iso, to_iso) daily windows for the last N days, newest last
    end = dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc).replace(second=0, microsecond=0)
    start = end - dt.timedelta(days=days)
    cur = start
    out = []
    while cur < end:
        nxt = min(end, cur + dt.timedelta(days=1))
        out.append((cur.isoformat().replace("+00:00","Z"), nxt.isoformat().replace("+00:00","Z")))
        cur = nxt
    return out

def fetch_range(client: OandaClient, instrument: str, granularity: str, days: int) -> pd.DataFrame:
    # OANDA doesn't allow large count with from/to simultaneously; fetch per-day and concat
    frames = []
    for fiso, tiso in daterange_utc(days):
        code, payload = client._req("GET", f"/v3/instruments/{instrument}/candles?granularity={granularity}&price=M&from={fiso}&to={tiso}")
        if code != 200: 
            continue
        rows = payload.get("candles", [])
        if not rows: 
            continue
        # parse minimal to avoid importing private parser
        rec = []
        for b in rows:
            mid = b.get("mid", {})
            rec.append([b["time"], float(mid.get("o","nan")), float(mid.get("h","nan")), float(mid.get("l","nan")), float(mid.get("c","nan"))])
        df = pd.DataFrame(rec, columns=["time","open","high","low","close"])
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df = df.set_index("time")
        frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["open","high","low","close"])
    df = pd.concat(frames).sort_index()
    df = df[~df.index.duplicated(keep='first')]  # prevent dupes
    return df

def main():
    os.makedirs("data", exist_ok=True)
    instr = os.environ.get("OANDA_INSTR", "EUR_USD")
    days = int(os.environ.get("AXFL_FETCH_DAYS","14"))
    key, acct, env = oanda_detect()
    if not key or not acct:
        # no creds: write a synthetic file so downstream steps proceed
        import numpy as np
        n = 288 * max(days,1)  # ~bars per day
        dt_idx = pd.date_range("2024-02-01", periods=n, freq="5min", tz="UTC")
        steps = np.random.default_rng(9).normal(0, 0.00022, size=n).cumsum()
        close = 1.082 + steps
        high = close + np.random.default_rng(9).uniform(0, 0.0006, size=n)
        low  = close - np.random.default_rng(9).uniform(0, 0.0006, size=n)
        open_ = pd.Series(close).shift(1).fillna(close[0]).values
        df = pd.DataFrame({"open":open_,"high":high,"low":low,"close":close}, index=dt_idx)
        out = f"data/{instr}_M5_synth.csv"
        df.to_csv(out)
        print(f"M7_FETCH mode=SIM instrument={instr} granularity=M5 bars={len(df)} from={df.index[0].isoformat()} to={df.index[-1].isoformat()} file={out}")
        return
    cli = OandaClient(key, acct, env)
    df = fetch_range(cli, instr, "M5", days)
    if df.empty:
        print(f"M7_FETCH mode=OANDA instrument={instr} granularity=M5 bars=0 from=NA to=NA file=NA fallback=USED")
        return
    out = f"data/{instr}_M5_{df.index[0].date()}_{df.index[-1].date()}.csv"
    df.to_csv(out)
    print(f"M7_FETCH mode=OANDA instrument={instr} granularity=M5 bars={len(df)} from={df.index[0].isoformat()} to={df.index[-1].isoformat()} file={out}")

if __name__ == "__main__":
    main()
