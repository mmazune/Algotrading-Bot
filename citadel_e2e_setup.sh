#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Citadel-Level Bot — End-to-End Verification & Health Pack
# Uses Twelve Data + Finnhub + MinIO (no Jupyter required)
# Creates a full harness to test: data pipeline (daily & intraday),
# storage (MinIO), scheduler freshness, backtests (SMA+RSI), WFO,
# and emits CSV/PNG/JSON artifacts + a single health summary.
# ============================================================

ROOT="verify_pro"
mkdir -p "$ROOT/out" "$ROOT/providers" "$ROOT/pipeline" "$ROOT/checks" "$ROOT/backtest"

# ---------------- requirements.txt ----------------
cat > "$ROOT/requirements.txt" << 'EOF'
pandas>=2.0
numpy>=1.25
requests>=2.31
python-dotenv>=1.0
pyyaml>=6.0
loguru>=0.7
pyarrow>=16.0.0
minio>=7.2.7
matplotlib>=3.8
backtesting==0.3.3
scipy>=1.11
dateparser>=1.2.0
EOF

# ---------------- .env.example ----------------
cat > "$ROOT/.env.example" << 'EOF'
# Twelve Data & Finnhub API Keys
TWELVE_DATA_KEY=replace_me
FINNHUB_KEY=replace_me

# MinIO / S3 storage
MINIO_ENDPOINT=127.0.0.1:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_SECURE=false
MINIO_BUCKET=market-data

# Symbols & defaults
DEFAULT_FX_SYMBOL=EUR/USD           # Twelve Data symbol
DEFAULT_FX_SYMBOL_FINNHUB=OANDA:EUR_USD
DEFAULT_INTRADAY_RES=60             # minutes for Finnhub
COLLECT_DAYS_INTRADAY=10
START_DATE=2015-01-01
END_DATE=2025-08-31

# Health thresholds
FRESHNESS_DAYS_DAILY=3
FRESHNESS_HOURS_INTRADAY=24
EOF

# ---------------- config.yaml ----------------
cat > "$ROOT/config.yaml" << 'EOF'
symbols:
  - "EUR/USD"

finnhub_symbols:
  - "OANDA:EUR_USD"

start: "2015-01-01"
end: "2025-08-31"
intraday_resolution: 60
intraday_days: 10

storage:
  bucket: "market-data"
  daily_key_fmt: "processed/daily/{symbol}.parquet"
  intraday_key_fmt: "processed/intraday/{symbol}_{res}m.parquet"

health:
  freshness_days_daily: 3
  freshness_hours_intraday: 24

wfo:
  train_months: 24
  test_months: 6
  step_months: 6
  param_grid:
    fast_sma: [8, 10, 12, 14]
    slow_sma: [26, 30, 34, 40]
    rsi_period: [10, 14, 20]
    rsi_threshold: [65, 68, 70, 72]
EOF

# ---------------- README.md ----------------
cat > "$ROOT/README.md" << 'EOF'
# Citadel-Level Bot — E2E Verification & Health Pack

## What this does
- Verifies **data pipeline** (Twelve Data daily, Finnhub intraday)
- Verifies **MinIO** storage (parquet round-trip)
- Tracks **scheduler freshness** (was the daily job running?)
- Runs **backtest** (Hybrid SMA+RSI) and **WFO** on stored data
- Emits **CSV/PNG/JSON** artifacts + a single **health summary**

## Quick start
```bash
cd verify_pro
python -m venv .venv && source .venv/bin/activate
pip install -U pip && pip install -r requirements.txt
cp .env.example .env  # edit keys and MinIO endpoint
bash run_all.sh
```

Artifacts appear in `verify_pro/out/`.

### health_summary.json — one-glance status of pipeline + tests
### daily_info.json, intraday_info.json — data ranges/freshness
### backtest_summary.json, wfo_summary.json — performance
### *.csv trades/results, *.png equity & drawdown

## Scheduling (example)
Add to crontab (daily collection at 02:10 UTC):

```
10 2 * * * /path/to/verify_pro/run_collect_only.sh >> /path/to/verify_pro/out/cron.log 2>&1
```
EOF

# ---------------- utils.py ----------------
cat > "$ROOT/utils.py" << 'EOF'
import os, io, json, math, time, re, sys
from datetime import datetime, timedelta, timezone
from typing import Dict, Any
import pandas as pd
import numpy as np
import yaml
from loguru import logger
from dotenv import load_dotenv

logger.remove()
logger.add(sys.stderr, level="INFO",
           format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | {message}")

def load_cfg(path="config.yaml") -> Dict[str, Any]:
    with open(path, "r") as f:
        return yaml.safe_load(f)

def load_env():
    load_dotenv()

def utcnow() -> datetime:
    return datetime.utcnow().replace(tzinfo=timezone.utc)

def ts(dt: datetime) -> int:
    return int(dt.timestamp())

def to_naive_utc_index(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index, utc=True, errors="coerce")
    else:
        # If index already has tz, convert to UTC; if naive, localize to UTC first
        df.index = df.index.tz_convert("UTC") if df.index.tz is not None else df.index.tz_localize("UTC")
    df.index = df.index.tz_localize(None)
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="last")]
    return df

def ensure_cols(df: pd.DataFrame, cols=("open","high","low","close","volume")) -> pd.DataFrame:
    for c in cols:
        if c not in df.columns:
            df[c] = np.nan
    return df[list(cols)]

def save_json(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, indent=2, default=lambda x: float(x) if isinstance(x, (np.floating,)) else x)

def business_days_missing(dates: pd.DatetimeIndex) -> int:
    if dates.empty: return 0
    s, e = dates.min(), dates.max()
    bd = pd.bdate_range(s, e, freq="C")  # custom business days
    return int(len(set(bd.date) - set(dates.date)))

def daterange_info(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"empty": True}
    return {
        "empty": False,
        "rows": int(len(df)),
        "start": str(df.index.min().date()),
        "end": str(df.index.max().date()),
    }
EOF

# ---------------- providers/minio_store.py ----------------
cat > "$ROOT/providers/minio_store.py" << 'EOF'
from minio import Minio
from minio.error import S3Error
import io, os
import pandas as pd

def client():
    endpoint = os.getenv("MINIO_ENDPOINT", "127.0.0.1:9000")
    access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    secure = os.getenv("MINIO_SECURE", "false").lower() == "true"
    return Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)

def ensure_bucket(bucket: str):
    c = client()
    found = c.bucket_exists(bucket)
    if not found:
        c.make_bucket(bucket)

def put_parquet(df: pd.DataFrame, bucket: str, key: str):
    c = client()
    ensure_bucket(bucket)
    buf = io.BytesIO()
    df.to_parquet(buf, index=True)
    buf.seek(0)
    c.put_object(bucket, key, buf, length=buf.getbuffer().nbytes, content_type="application/octet-stream")

def get_parquet(bucket: str, key: str) -> pd.DataFrame:
    c = client()
    resp = c.get_object(bucket, key)
    data = resp.read()
    resp.close(); resp.release_conn()
    return pd.read_parquet(io.BytesIO(data))

def list_keys(bucket: str, prefix: str):
    c = client()
    return [obj.object_name for obj in c.list_objects(bucket, prefix=prefix, recursive=True)]

def stat_key(bucket: str, key: str):
    c = client()
    return c.stat_object(bucket, key)
EOF

# ---------------- providers/twelvedata_client.py ----------------
cat > "$ROOT/providers/twelvedata_client.py" << 'EOF'
import os, requests, pandas as pd
from utils import to_naive_utc_index, ensure_cols

BASE = "https://api.twelvedata.com/time_series"

def fetch_daily(symbol: str, start: str, end: str, api_key: str=None) -> pd.DataFrame:
    api_key = api_key or os.getenv("TWELVE_DATA_KEY")
    if not api_key:
        raise RuntimeError("TWELVE_DATA_KEY missing")
    params = {
        "symbol": symbol,
        "interval": "1day",
        "start_date": start,
        "end_date": end,
        "order": "ASC",
        "timezone": "UTC",
        "apikey": api_key
    }
    r = requests.get(BASE, params=params, timeout=60)
    r.raise_for_status()
    js = r.json()
    if "values" not in js:
        # Either error or empty payload
        return pd.DataFrame(columns=["open","high","low","close","volume"])
    vals = js["values"]
    df = pd.DataFrame(vals)
    # Columns: datetime, open, high, low, close, volume
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    df = df.rename(columns=str.lower).set_index("datetime")
    for col in ["open","high","low","close","volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = to_naive_utc_index(df)
    df = ensure_cols(df)
    return df
EOF

# ---------------- providers/finnhub_client.py ----------------
cat > "$ROOT/providers/finnhub_client.py" << 'EOF'
import os, requests, pandas as pd
from datetime import datetime, timedelta, timezone
from utils import to_naive_utc_index, ensure_cols, ts

BASE = "https://finnhub.io/api/v1/forex/candle"

def fetch_candles(symbol: str, resolution: int, days: int, api_key: str=None) -> pd.DataFrame:
    """
    symbol like 'OANDA:EUR_USD', resolution in minutes (1,5,15,30,60), last N days
    """
    api_key = api_key or os.getenv("FINNHUB_KEY")
    if not api_key:
        raise RuntimeError("FINNHUB_KEY missing")
    now = datetime.utcnow().replace(tzinfo=timezone.utc)
    frm = now - timedelta(days=days)
    params = {
        "symbol": symbol,
        "resolution": str(resolution),
        "from": ts(frm),
        "to": ts(now),
        "token": api_key
    }
    r = requests.get(BASE, params=params, timeout=60)
    r.raise_for_status()
    js = r.json()
    if js.get("s") != "ok":
        return pd.DataFrame(columns=["open","high","low","close","volume"])
    df = pd.DataFrame({
        "time": pd.to_datetime(js["t"], unit="s", utc=True),
        "open": js["o"],
        "high": js["h"],
        "low": js["l"],
        "close": js["c"],
        "volume": js.get("v", [0]*len(js["t"]))
    })
    df = df.set_index("time")
    df = to_naive_utc_index(df)
    df = ensure_cols(df)
    return df
EOF

# ---------------- pipeline/collect_daily.py ----------------
cat > "$ROOT/pipeline/collect_daily.py" << 'EOF'
import os, argparse, json
from loguru import logger
import pandas as pd
from dotenv import load_dotenv
from utils import load_cfg, daterange_info, save_json
from providers.twelvedata_client import fetch_daily
from providers.minio_store import put_parquet, get_parquet, stat_key, ensure_bucket

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--symbols", nargs="*", default=None)
    args = ap.parse_args()
    
    load_dotenv()
    cfg = load_cfg(args.config)
    symbols = args.symbols or cfg.get("symbols", ["EUR/USD"])
    start = os.getenv("START_DATE", cfg.get("start"))
    end = os.getenv("END_DATE", cfg.get("end"))
    bucket = cfg["storage"]["bucket"]
    key_fmt = cfg["storage"]["daily_key_fmt"]
    
    ensure_bucket(bucket)
    report = {}
    for sym in symbols:
        df = fetch_daily(sym, start, end)
        key = key_fmt.format(symbol=sym.replace("/", "_"))
        put_parquet(df, bucket, key)
        try:
            size = stat_key(bucket, key).size
        except Exception:
            size = None
        info = daterange_info(df)
        info.update({"bucket": bucket, "key": key, "bytes": size})
        report[sym] = info
        logger.info(f"[DAILY] {sym}: {info}")
    
    os.makedirs("out", exist_ok=True)
    save_json("out/daily_info.json", report)
    print("[DONE] daily collection complete. See out/daily_info.json")

if __name__ == "__main__":
    main()
EOF

# ---------------- pipeline/collect_intraday.py ----------------
cat > "$ROOT/pipeline/collect_intraday.py" << 'EOF'
import os, argparse
from loguru import logger
from dotenv import load_dotenv
from utils import load_cfg, daterange_info, save_json
from providers.finnhub_client import fetch_candles
from providers.minio_store import put_parquet, stat_key, ensure_bucket

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--symbols", nargs="*", default=None)
    ap.add_argument("--res", type=int, default=None)
    ap.add_argument("--days", type=int, default=None)
    args = ap.parse_args()
    
    load_dotenv()
    cfg = load_cfg(args.config)
    symbols = args.symbols or cfg.get("finnhub_symbols", ["OANDA:EUR_USD"])
    res = args.res or int(cfg.get("intraday_resolution", 60))
    days = args.days or int(cfg.get("intraday_days", 10))
    bucket = cfg["storage"]["bucket"]
    key_fmt = cfg["storage"]["intraday_key_fmt"]
    
    ensure_bucket(bucket)
    report = {}
    for sym in symbols:
        df = fetch_candles(sym, res, days)
        key = key_fmt.format(symbol=sym.replace(":", "_"), res=res)
        put_parquet(df, bucket, key)
        try:
            size = stat_key(bucket, key).size
        except Exception:
            size = None
        info = daterange_info(df)
        info.update({"bucket": bucket, "key": key, "bytes": size})
        report[sym] = info
        logger.info(f"[INTRADAY] {sym}: {info}")
    
    os.makedirs("out", exist_ok=True)
    save_json("out/intraday_info.json", report)
    print("[DONE] intraday collection complete. See out/intraday_info.json")

if __name__ == "__main__":
    main()
EOF

# ---------------- checks/healthcheck.py ----------------
cat > "$ROOT/checks/healthcheck.py" << 'EOF'
import os, json, math
from datetime import datetime, timedelta
import pandas as pd
from dotenv import load_dotenv
from utils import load_cfg, save_json
from providers.minio_store import get_parquet

def main():
    load_dotenv()
    cfg = load_cfg("config.yaml")
    bucket = cfg["storage"]["bucket"]
    daily_fmt = cfg["storage"]["daily_key_fmt"]
    intra_fmt = cfg["storage"]["intraday_key_fmt"]
    
    freshness_days_daily = int(cfg["health"]["freshness_days_daily"])
    freshness_hours_intraday = int(cfg["health"]["freshness_hours_intraday"])
    
    # Daily
    daily_status = {}
    for sym in cfg.get("symbols", []):
        key = daily_fmt.format(symbol=sym.replace("/", "_"))
        try:
            df = get_parquet(bucket, key)
            last_date = None if df.empty else df.index.max()
            is_fresh = False
            if last_date is not None:
                age_days = (pd.Timestamp.utcnow().tz_localize(None) - last_date).days
                is_fresh = age_days <= freshness_days_daily
            daily_status[sym] = {
                "exists": True,
                "last_date": None if last_date is None else str(last_date.date()),
                "fresh": bool(is_fresh),
                "rows": int(len(df))
            }
        except Exception as e:
            daily_status[sym] = {"exists": False, "error": str(e)}
    
    # Intraday
    intra_status = {}
    for sym in cfg.get("finnhub_symbols", []):
        key = intra_fmt.format(symbol=sym.replace(":", "_"), res=int(cfg.get("intraday_resolution", 60)))
        try:
            df = get_parquet(bucket, key)
            last_ts = None if df.empty else df.index.max()
            is_fresh = False
            if last_ts is not None:
                delta = (pd.Timestamp.utcnow().tz_localize(None) - last_ts)
                is_fresh = (delta.total_seconds() / 3600.0) <= freshness_hours_intraday
            intra_status[sym] = {
                "exists": True,
                "last_timestamp": None if last_ts is None else last_ts.isoformat(sep=" "),
                "fresh": bool(is_fresh),
                "rows": int(len(df))
            }
        except Exception as e:
            intra_status[sym] = {"exists": False, "error": str(e)}
    
    summary = {
        "daily": daily_status,
        "intraday": intra_status
    }
    os.makedirs("out", exist_ok=True)
    save_json("out/health_status.json", summary)
    
    # Overall
    ok = True
    for s in daily_status.values():
        if not s.get("exists"): ok = False
        elif "fresh" in s and not s["fresh"]: ok = False
    for s in intra_status.values():
        if not s.get("exists"): ok = False
        elif "fresh" in s and not s["fresh"]: ok = False
    
    save_json("out/health_summary.json", {
        "ok": ok,
        "daily_symbols": list(daily_status.keys()),
        "intraday_symbols": list(intra_status.keys())
    })
    print("[DONE] health check. See out/health_status.json and out/health_summary.json")

if __name__ == "__main__":
    main()
EOF

# ---------------- backtest/strategy.py ----------------
cat > "$ROOT/backtest/strategy.py" << 'EOF'
import pandas as pd
from backtesting import Strategy
from backtesting.lib import crossover
from backtesting.test import SMA

def rsi(series: pd.Series, length=14):
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    roll_up = up.ewm(alpha=1/length, adjust=False).mean()
    roll_down = down.ewm(alpha=1/length, adjust=False).mean()
    rs = roll_up / (roll_down + 1e-12)
    return 100 - (100 / (1 + rs))

class HybridSmaCrossRSI(Strategy):
    fast_sma = 10
    slow_sma = 30
    rsi_period = 14
    rsi_threshold = 70
    
    def init(self):
        close = self.data.Close
        self.fast = self.I(SMA, close, self.fast_sma)
        self.slow = self.I(SMA, close, self.slow_sma)
        self.rsi_v = self.I(rsi, close, self.rsi_period)
    
    def next(self):
        if (not self.position and
            crossover(self.fast, self.slow) and
            self.rsi_v[-1] < self.rsi_threshold):
            self.buy()
        elif self.position and crossover(self.slow, self.fast):
            self.position.close()
EOF

# ---------------- backtest/run_backtest.py ----------------
cat > "$ROOT/backtest/run_backtest.py" << 'EOF'
import os, argparse, json
import pandas as pd
import matplotlib.pyplot as plt
from backtesting import Backtest
from dotenv import load_dotenv
from utils import load_cfg, save_json
from providers.minio_store import get_parquet
from backtest.strategy import HybridSmaCrossRSI

plt.switch_backend("Agg")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--symbol", default=None)
    ap.add_argument("--commission_bps", type=float, default=2.0)
    ap.add_argument("--slippage_bps", type=float, default=1.0)
    args = ap.parse_args()
    
    load_dotenv()
    cfg = load_cfg(args.config)
    bucket = cfg["storage"]["bucket"]
    key_fmt = cfg["storage"]["daily_key_fmt"]
    
    symbol = args.symbol or cfg.get("symbols", ["EUR/USD"])[0]
    key = key_fmt.format(symbol=symbol.replace("/", "_"))
    df = get_parquet(bucket, key)
    df = df.rename(columns=str.lower)
    df = df[["open","high","low","close","volume"]].dropna()
    
    bt = Backtest(df, HybridSmaCrossRSI,
                  cash=100_000,
                  commission=args.commission_bps/10000.0,
                  slippage=args.slippage_bps/10000.0,
                  trade_on_close=False,
                  exclusive_orders=True)
    stats = bt.run()
    eq = stats["_equity_curve"]["Equity"]
    dd = eq/eq.cummax() - 1.0
    
    os.makedirs("out", exist_ok=True)
    df_trades = stats._trades
    if df_trades is not None:
        df_trades.to_csv("out/backtest_trades.csv", index=False)
    save_json("out/backtest_summary.json", {
        "symbol": symbol,
        "return_pct": float(stats.get("Return [%]", float('nan'))),
        "sharpe": float(stats.get("Sharpe Ratio", float('nan'))),
        "max_dd_pct": float(stats.get("Max. Drawdown [%]", float('nan'))),
        "trades": int(stats.get("# Trades", 0)),
    })
    
    plt.figure(figsize=(10,4))
    plt.plot(eq.values)
    plt.title(f"Equity — {symbol}")
    plt.tight_layout(); plt.savefig("out/backtest_equity.png", dpi=140)
    
    plt.figure(figsize=(10,3))
    plt.plot(dd.values)
    plt.title("Drawdown")
    plt.tight_layout(); plt.savefig("out/backtest_drawdown.png", dpi=140)
    
    print("[DONE] backtest complete. See out/backtest_summary.json")

if __name__ == "__main__":
    main()
EOF

# ---------------- backtest/wfo.py ----------------
cat > "$ROOT/backtest/wfo.py" << 'EOF'
import os, argparse, numpy as np, pandas as pd, matplotlib.pyplot as plt
from dotenv import load_dotenv
from backtesting import Backtest
from utils import load_cfg, save_json
from providers.minio_store import get_parquet
from backtest.strategy import HybridSmaCrossRSI

plt.switch_backend("Agg")

def make_windows(idx, train_m, test_m, step_m):
    periods = pd.period_range(idx.min(), idx.max(), freq="M")
    if len(periods) == 0: return []
    wins = []
    start = periods.min()
    while True:
        tr_s = start.start_time
        tr_e = (start + train_m - 1).end_time
        te_s = (start + train_m).start_time
        te_e = (start + train_m + test_m - 1).end_time
        if te_e > idx.max(): break
        wins.append((tr_s, tr_e, te_s, te_e))
        start = start + step_m
    return wins

def run_bt(df, params, c_bps, s_bps):
    bt = Backtest(df, HybridSmaCrossRSI,
                  cash=100_000,
                  commission=c_bps/10000.0,
                  slippage=s_bps/10000.0,
                  trade_on_close=False,
                  exclusive_orders=True)
    return bt.run(**params)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--symbol", default=None)
    ap.add_argument("--commission_bps", type=float, default=2.0)
    ap.add_argument("--slippage_bps", type=float, default=1.0)
    args = ap.parse_args()
    
    load_dotenv()
    cfg = load_cfg(args.config)
    bucket = cfg["storage"]["bucket"]
    key_fmt = cfg["storage"]["daily_key_fmt"]
    symbol = args.symbol or cfg.get("symbols", ["EUR/USD"])[0]
    key = key_fmt.format(symbol=symbol.replace("/", "_"))
    
    df = get_parquet(bucket, key)
    df = df.rename(columns=str.lower)[["open","high","low","close","volume"]].dropna()
    
    grid = cfg["wfo"]["param_grid"]
    train_m = int(cfg["wfo"]["train_months"])
    test_m = int(cfg["wfo"]["test_months"])
    step_m = int(cfg["wfo"]["step_months"])
    
    wins = make_windows(df.index, train_m, test_m, step_m)
    rows = []
    oos_parts = []
    best_rows = []
    
    for (tr_s, tr_e, te_s, te_e) in wins:
        tr = df.loc[(df.index>=tr_s)&(df.index<=tr_e)]
        te = df.loc[(df.index>=te_s)&(df.index<=te_e)]
        if len(tr)<60 or len(te)<20: continue
        
        best_score = -np.inf; best=None
        for fs in grid["fast_sma"]:
            for ss in grid["slow_sma"]:
                if fs>=ss: continue
                for rp in grid["rsi_period"]:
                    for rt in grid["rsi_threshold"]:
                        params = dict(fast_sma=fs, slow_sma=ss, rsi_period=rp, rsi_threshold=rt)
                        st = run_bt(tr, params, args.commission_bps, args.slippage_bps)
                        score = float(st.get("Sharpe Ratio", np.nan))
                        if np.isnan(score): score = -np.inf
                        if score>best_score: best_score, best = score, params
        
        st = run_bt(te, best, args.commission_bps, args.slippage_bps)
        eq = st["_equity_curve"]["Equity"]
        oos_parts.append(eq)
        
        rows.append({
            "test_start": str(te_s.date()), "test_end": str(te_e.date()),
            "trades": int(st.get("# Trades", 0)),
            "win_rate_pct": float(st.get("Win Rate [%]", np.nan)),
            "ret_pct": float(st.get("Return [%]", np.nan)),
            "max_dd_pct": float(st.get("Max. Drawdown [%]", np.nan)),
            "sharpe": float(st.get("Sharpe Ratio", np.nan)),
            **best
        })
        best_rows.append({"train_start": str(tr_s.date()), "train_end": str(tr_e.date()), **best})
    
    os.makedirs("out", exist_ok=True)
    pd.DataFrame(rows).to_csv("out/wfo_results.csv", index=False)
    pd.DataFrame(best_rows).to_csv("out/wfo_best_params.csv", index=False)
    
    if oos_parts:
        oos = pd.concat(oos_parts).reset_index(drop=True)
        dd = oos/oos.cummax()-1.0
        plt.figure(figsize=(10,4)); plt.plot(oos.values); plt.title(f"OOS Equity — {symbol}"); plt.tight_layout(); plt.savefig("out/wfo_oos_equity.png", dpi=140)
        plt.figure(figsize=(10,3)); plt.plot(dd.values); plt.title("OOS Drawdown"); plt.tight_layout(); plt.savefig("out/wfo_oos_drawdown.png", dpi=140)
        summary = {
            "windows": len(rows),
            "oos_cum_return_pct": float((oos.iloc[-1]/oos.iloc[0]-1)*100) if len(oos)>1 else float("nan"),
            "oos_max_dd_pct": float(dd.min()*100) if len(dd)>1 else float("nan"),
            "total_trades": int(sum(r["trades"] for r in rows)) if rows else 0
        }
    else:
        summary = {"windows": 0, "oos_cum_return_pct": float("nan"), "oos_max_dd_pct": float("nan"), "total_trades": 0}
    
    save_json("out/wfo_summary.json", summary)
    print("[DONE] WFO complete. See out/wfo_summary.json")

if __name__ == "__main__":
    main()
EOF

# ---------------- run_all.sh ----------------
cat > "$ROOT/run_all.sh" << 'EOF'
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt

# 1) Collect daily (Twelve Data)
python pipeline/collect_daily.py --config config.yaml

# 2) Collect intraday (Finnhub)
python pipeline/collect_intraday.py --config config.yaml

# 3) Health check (freshness + existence)
python checks/healthcheck.py

# 4) Backtest on stored daily
python backtest/run_backtest.py --config config.yaml

# 5) Walk-forward on stored daily
python backtest/wfo.py --config config.yaml

echo "Artifacts in $(pwd)/out:"
ls -lh out
EOF
chmod +x "$ROOT/run_all.sh"

# ---------------- run_collect_only.sh ----------------
cat > "$ROOT/run_collect_only.sh" << 'EOF'
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt

python pipeline/collect_daily.py --config config.yaml
python pipeline/collect_intraday.py --config config.yaml
python checks/healthcheck.py

echo "Collection + healthcheck done at $(date -u +"%Y-%m-%d %H:%M:%S UTC")" | tee -a out/cron.log
EOF
chmod +x "$ROOT/run_collect_only.sh"

# ---------------- crontab_example.txt ----------------
cat > "$ROOT/crontab_example.txt" << 'EOF'
# Run daily collectors + healthcheck at 02:10 UTC
10 2 * * * /ABSOLUTE/PATH/verify_pro/run_collect_only.sh >> /ABSOLUTE/PATH/verify_pro/out/cron.log 2>&1
EOF

echo "✅ E2E verification & health pack created in ./$ROOT"
echo "Next steps:"
echo "  cd $ROOT && python -m venv .venv && source .venv/bin/activate && pip install -U pip && pip install -r requirements.txt"
echo "  cp .env.example .env  (fill TWELVE_DATA_KEY, FINNHUB_KEY, MinIO settings)"
echo "  bash run_all.sh"
