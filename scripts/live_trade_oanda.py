# Unified live runner: DRYRUN by default; LIVE if LIVE_TRADING=1.
import os, json
import pandas as pd
from axfl.brokers.oanda_api import oanda_detect, OandaClient, fetch_oanda_candles
from axfl.strategies.registry import REGISTRY
from axfl.strategies.utils import position_units_from_risk

PIP = 0.0001

def _synth_eurusd(n=600, seed=11):
    import numpy as np
    rng = np.random.default_rng(seed)
    dt = pd.date_range("2024-01-05", periods=n, freq="5min", tz="UTC")
    close = 1.085 + rng.normal(0, 0.00024, size=n).cumsum()
    high = close + rng.uniform(0, 0.0006, size=n)
    low  = close - rng.uniform(0, 0.0006, size=n)
    open_ = pd.Series(close).shift(1).fillna(close[0]).values
    return pd.DataFrame({"open":open_, "high":high, "low":low, "close":close}, index=dt)

def in_session(now_utc: pd.Timestamp) -> bool:
    # Simple UTC windows: London+NY overlap-ish. M-F only.
    if now_utc.weekday() > 4:  # 0=Mon
        return False
    hhmm = now_utc.hour*100 + now_utc.minute
    windows = [(700,1200), (1300,1700)]  # 07:00-12:00 & 13:00-17:00 UTC
    return any(a <= hhmm <= b for (a,b) in windows)

def load_state():
    os.makedirs("reports", exist_ok=True)
    p = "reports/m5_state.json"
    if not os.path.exists(p):
        return {"date": None, "trades_today": 0, "day_risk_R": 0.0}
    try:
        with open(p,"r") as f: return json.load(f)
    except Exception:
        return {"date": None, "trades_today": 0, "day_risk_R": 0.0}

def save_state(st):
    with open("reports/m5_state.json","w") as f: json.dump(st,f)

def pick_signal(df: pd.DataFrame):
    names = ["ema_trend","bollinger_mean_rev","price_action_breakout"]
    for name in names:
        sig = REGISTRY[name]().generate(df).reindex(df.index).iloc[-1]
        if sig["signal"] != 0 and not pd.isna(sig["sl"]) and not pd.isna(sig["tp"]):
            side = int(sig["signal"])
            return name, side, float(df["close"].iloc[-1]), float(sig["sl"]), float(sig["tp"])
    return None, 0, float(df["close"].iloc[-1]), float("nan"), float("nan")

def main():
    # Config
    balance = float(os.environ.get("AXFL_BALANCE","200"))
    risk_pct = float(os.environ.get("AXFL_RISK_PCT","0.01"))
    daily_stop_R = float(os.environ.get("AXFL_DAILY_STOP_R","4.0"))
    max_trades_day = int(os.environ.get("AXFL_MAX_TRADES_DAY","6"))
    instr = os.environ.get("OANDA_INSTR","EUR_USD")

    # Env detect + data
    key, acct, env = oanda_detect()
    live_flag = os.environ.get("LIVE_TRADING") == "1"
    mode = "OANDA" if key and acct else "SIM"

    if mode=="OANDA":
        cli = OandaClient(key, acct, env)
        code, df = fetch_oanda_candles(cli, instrument=instr, granularity="M5", count=300)
        if code != 200 or df.empty:
            mode="SIM"; df = _synth_eurusd()
    else:
        df = _synth_eurusd()

    now_utc = pd.Timestamp.utcnow()
    if now_utc.tz is None:
        now_utc = now_utc.tz_localize("UTC")
    state = load_state()
    if state.get("date") != now_utc.date().isoformat():
        state = {"date": now_utc.date().isoformat(), "trades_today": 0, "day_risk_R": 0.0}

    # Session window + kill-switch checks
    allowed = in_session(now_utc)
    ks_hit = (abs(state["day_risk_R"]) >= daily_stop_R) or (state["trades_today"] >= max_trades_day)

    # Pick a signal
    strat, side, entry, sl, tp = pick_signal(df)
    decision = "NONE"
    reason = ""
    units = 0
    if strat and allowed and not ks_hit:
        units = position_units_from_risk(balance, risk_pct, entry, sl, pip_value_per_unit=0.0001)
        if units > 0:
            # OANDA requires positive units for BUY (long), negative for SELL (short)
            oanda_units = units if side==1 else -units
            decision = "PLACE"
        else:
            decision = "SKIP"; reason = "sizing_zero"
    else:
        decision = "SKIP"
        reason = "no_session" if not allowed else ("kill_switch" if ks_hit else "no_signal")

    # Act
    action = "SKIPPED"
    order_id = "NA"
    if decision=="PLACE":
        if live_flag and mode=="OANDA":
            code, resp = cli.place_market_order(instr, oanda_units, sl=sl, tp=tp, tag=strat)
            if code==201 and "orderFillTransaction" in resp:
                action="PLACED"
                order_id = str(resp["orderFillTransaction"].get("id","?"))
                # consume 1R risk budget when placing
                state["day_risk_R"] += 1.0
                state["trades_today"] += 1
            else:
                action="ERROR"
                reason=f"http_{code}"
        else:
            action="DRYRUN"
            # simulate consuming 1R risk budget on planned order
            state["day_risk_R"] += 1.0
            state["trades_today"] += 1

    save_state(state)

    # SUCCESS MARKERS (ONLY)
    print(f"OANDA_EXEC_READY mode={mode} trading={'LIVE' if live_flag and mode=='OANDA' else 'DRYRUN'} account={(acct or 'NA')} env={(env or 'NA')} instrument={instr}")
    if strat:
        print(f"SIGNAL_DECISION strategy={strat} side={side} entry={entry:.5f} sl={sl:.5f} tp={tp:.5f} units={units}")
    else:
        print("SIGNAL_DECISION strategy=NONE side=0 entry=NA sl=NA tp=NA units=0")
    print(f"ORDER_ACTION action={action} orderID={order_id} reason={reason}")
    print(f"KILL_SWITCH day_total_R={state['day_risk_R']:.2f} trades_today={state['trades_today']} daily_stop_R={daily_stop_R} max_trades_day={max_trades_day}")
    print("AXFL_M5_OK")

    # Append event to JSONL
    os.makedirs("reports", exist_ok=True)
    try:
        _rec = {
            "ts": pd.Timestamp.utcnow().isoformat(timespec="seconds")+"Z",
            "mode": mode, "trading": ("LIVE" if (live_flag and mode=="OANDA") else "DRYRUN"),
            "strategy": (strat or "NONE"), "side": int(side) if strat else 0,
            "entry": (float(entry) if strat else None), "sl": (float(sl) if strat else None), "tp": (float(tp) if strat else None),
            "units": int(units) if strat else 0, "action": action, "reason": reason,
            "day_total_R": float(state["day_risk_R"]), "trades_today": int(state["trades_today"])
        }
        with open("reports/live_events.jsonl","a") as _f:
            _f.write(json.dumps(_rec)+"\n")
    except Exception:
        pass

if __name__ == "__main__":
    main()
