import os, sys, time, json, math, argparse, subprocess, datetime as dt

def utc_now():
    return dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc)

def next_tick(now=None, interval_min=5):
    now = now or utc_now()
    # Round up to next interval boundary
    total_min = now.minute + now.hour*60
    step = interval_min
    next_total = ((total_min // step) + 1) * step
    delta_min = next_total - total_min
    next_dt = (now + dt.timedelta(minutes=delta_min)).replace(second=0, microsecond=0)
    return next_dt

def run_once():
    os.makedirs("reports", exist_ok=True)
    # 1) Run live decision (DRYRUN or LIVE based on ENV)
    cmd = [sys.executable, "scripts/live_trade_oanda.py"]
    p = subprocess.run(cmd, capture_output=True, text=True)
    out = (p.stdout or "") + (p.stderr or "")
    with open("reports/live_roll.log","a") as f:
        f.write(out + "\n")
    # 2) Regenerate dashboard
    p2 = subprocess.run([sys.executable, "scripts/generate_dashboard.py"], capture_output=True, text=True)
    dash_line = ""
    for ln in (p2.stdout or "").splitlines():
        if ln.startswith("DASHBOARD_READY "): dash_line = ln; break
    return out, dash_line

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--daemon", action="store_true", help="run forever")
    ap.add_argument("--oneshot", action="store_true", help="run one cycle and exit")
    ap.add_argument("--interval-min", type=int, default=int(os.environ.get("AXFL_SCHED_INTERVAL_MIN","5")))
    args = ap.parse_args()
    interval = max(1, args.interval_min)

    if os.path.exists("reports/STOP"):
        print("SCHEDULER_STOPPED reason=STOP_file")
        return

    nxt = next_tick(interval_min=interval)
    print(f"SCHEDULER_READY interval={interval}m next_tick={nxt.isoformat().replace('+00:00','Z')}")
    if args.daemon:
        while True:
            if os.path.exists("reports/STOP"):
                print("SCHEDULER_STOPPED reason=STOP_file"); return
            now = utc_now()
            if now >= nxt:
                run_once()
                nxt = next_tick(now=now, interval_min=interval)
            time.sleep(5)
    else:
        # oneshot run immediately
        out, dash_line = run_once()
        # also echo spread/slippage config for visibility
        spread = float(os.environ.get("AXFL_SPREAD_PIPS","0.2"))
        slip = float(os.environ.get("AXFL_SLIPPAGE_PIPS","0.1"))
        print(f"SPREAD_MODEL spread_pips={spread} slippage_pips={slip}")
        if dash_line: print(dash_line)

if __name__=="__main__":
    main()
