import argparse
import csv
import datetime as dt
from importlib import import_module
from pathlib import Path
from typing import Dict, Iterable, List, Tuple, Optional

# Map short names -> "module.path:ClassName"
STRATEGY_CLASS_PATHS: Dict[str, str] = {
    "lsg": "axfl.strategies.lsg:LSGStrategy",
    "ema_trend": "axfl.strategies.ema_trend:EMATrendStrategy",
    "bollinger_mean_rev": "axfl.strategies.bollinger_mean_rev:BollingerMeanRev",
    "session_breakout": "axfl.strategies.session_breakout:SessionBreakout",
    "price_action_breakout": "axfl.strategies.price_action_breakout:PriceActionBreakout",
}

def _resolve_strategy(name: str):
    spec = STRATEGY_CLASS_PATHS[name]
    mod, cls = spec.split(":")
    return getattr(import_module(mod), cls)

def _get_strategy_map(requested: Optional[str]) -> Dict[str, type]:
    if requested:
        want = {s.strip().lower() for s in requested.split(",") if s.strip()}
    else:
        want = set(STRATEGY_CLASS_PATHS.keys())
    unknown = want - set(STRATEGY_CLASS_PATHS.keys())
    if unknown:
        raise SystemExit(f"Unknown strategy name(s): {', '.join(sorted(unknown))}")
    return {k: _resolve_strategy(k) for k in sorted(want)}

def _parse_since(s: str) -> dt.datetime:
    # Accept like "6h", "24h", "2d"
    s = s.strip().lower()
    now = dt.datetime.now(dt.timezone.utc)
    if s.endswith("h"):
        hours = int(s[:-1])
        return now - dt.timedelta(hours=hours)
    if s.endswith("d"):
        days = int(s[:-1])
        return now - dt.timedelta(days=days)
    # ISO fallback
    try:
        t = dt.datetime.fromisoformat(s)
        return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)
    except Exception:
        raise SystemExit(f"--since '{s}' not understood (try '6h', '2d' or ISO)")

def _read_csv(path: Path) -> List[Tuple[dt.datetime, float, float, float, float]]:
    rows: List[Tuple[dt.datetime, float, float, float, float]] = []
    with path.open(newline="") as f:
        r = csv.reader(f)
        for row in r:
            if not row or row[0].startswith("#"):
                continue
            # Expect: timestamp, open, high, low, close
            ts = row[0]
            t = dt.datetime.fromisoformat(ts)
            if t.tzinfo is None:
                t = t.replace(tzinfo=dt.timezone.utc)
            o, h, l, c = map(float, row[1:5])
            rows.append((t, o, h, l, c))
    return rows

def scan_symbols(
    instrument: str,
    granularity: str,
    bars: List[Tuple[dt.datetime, float, float, float, float]],
    strategies: Dict[str, type],
    since: Optional[dt.datetime] = None,
) -> List[Tuple[str, dt.datetime, str]]:
    out: List[Tuple[str, dt.datetime, str]] = []
    # Minimal adapter: for each strategy class, build instance and feed bars
    for name, cls in strategies.items():
        strat = cls(symbol=instrument, granularity=granularity)  # constructor in repo expects these
        # assume strategies expose feed_bar(t,o,h,l,c) and maybe signal_at(t)
        for t, o, h, l, c in bars:
            strat.feed_bar(t, o, h, l, c)  # no-op if strategy handles windowing
            if since and t < since:
                continue
            sig = getattr(strat, "signal_at", None)
            if callable(sig):
                s = sig(t)
                if s:  # e.g., "BUY", "SELL" or dict/text
                    out.append((name, t, str(s)))
    return out

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="axfl.tools.signal_scan", description="Scan CSV bars for strategy signals.")
    ap.add_argument("--instrument", required=True)
    ap.add_argument("--granularity", required=True)
    ap.add_argument("--csv", required=True, help="Path to CSV with columns: timestamp,open,high,low,close")
    ap.add_argument("--since", default="6h", help="Lookback window, e.g. '6h', '2d', or ISO timestamp")
    ap.add_argument("--strategies", default=None,
                    help="Comma list (e.g. 'lsg,ema_trend'). Defaults to all.")
    args = ap.parse_args(argv)

    csv_path = Path(args.csv)
    if not csv_path.exists():
        raise SystemExit(f"CSV not found: {csv_path}")

    bars = _read_csv_tolerant(csv_path)
    if not bars:
        raise SystemExit("No rows found in CSV")

    since_ts = _parse_since(args.since) if args.since else None
    s_map = _get_strategy_map(args.strategies)

    results = scan_symbols(args.instrument, args.granularity, bars, s_map, since_ts)

    if not results:
        print("NO_SIGNALS")
        return 0

    # Pretty print
    print("strategy,timestamp,signal")
    for name, t, sig in results:
        print(f"{name},{t.isoformat()},{sig}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
# --- tolerant CSV reader (appended) ---
def _read_csv_tolerant(path: Path) -> list[Bar]:
    """Load bars from CSV. Tolerates header and blank/malformed rows.
    Expected columns: time,open,high,low,close (time ISO8601)."""
    with path.open(newline="") as f:
        r = csv.reader(f)
        bars: list[Bar] = []
        for row in r:
            if not row:
                continue
            row = [c.strip() for c in row]
            # skip header or missing timestamp
            if not row[0] or row[0].lower() in {"time", "timestamp"}:
                continue
            if len(row) < 5:
                continue
            ts, o, h, l, c = row[:5]
            try:
                t = dt.datetime.fromisoformat(ts)
                bars.append(Bar(t, float(o), float(h), float(l), float(c)))
            except Exception:
                # ignore any malformed row
                continue
    return bars
