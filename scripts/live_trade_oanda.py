from __future__ import annotations
import os, json, math
import pandas as pd
import numpy as np
import datetime as _dt

from axfl.brokers.oanda_api import oanda_detect, OandaClient, fetch_oanda_candles
from axfl.strategies.registry import REGISTRY
from axfl.strategies.utils import position_units_from_risk

# Discord alert fallbacks
try:
    from axfl.notify.discord import alert_trade_open, alert_kill_switch, alert_adr_guard
except Exception:
    def alert_trade_open(*a, **k): return 0
    def alert_kill_switch(*a, **k): return 0
    def alert_adr_guard(*a, **k): return 0

PIP = 0.0001

def _synth_eurusd(n=600, seed=11):
    rng = np.random.default_rng(seed)
    dt = pd.date_range("2024-01-05", periods=n, freq="5min", tz="UTC")
    close = 1.085 + rng.normal(0, 0.00024, size=n).cumsum()
    high = close + rng.uniform(0, 0.0006, size=n)
    low  = close - rng.uniform(0, 0.0006, size=n)
    open_ = pd.Series(close).shift(1).fillna(close[0]).values
    return pd.DataFrame({"open":open_, "high":high, "low":low, "close":close}, index=dt)

def in_session(now_utc: pd.Timestamp) -> bool:
    if now_utc.weekday() > 4:
        return False
    hhmm = now_utc.hour*100 + now_utc.minute
    windows = [(700,1200), (1300,1700)]
    return any(a <= hhmm <= b for (a,b) in windows)

def load_state():
    os.makedirs("reports", exist_ok=True)
    p = "reports/m5_state.json"
    base = {"date": None, "trades_today": 0, "day_risk_R": 0.0,
            "last_exec": {}, "done_today": {},
            "sent_kill": "", "sent_adr": "", "adr_was_low": False}
    if not os.path.exists(p):
        return base
    try:
        with open(p,"r") as f:
            st = json.load(f)
        for k,v in base.items():
            st.setdefault(k, v)
        return st
    except Exception:
        return base

def save_state(st):
    with open("reports/m5_state.json","w") as f:
        json.dump(st,f)

def _adr14_pips(df_m5: pd.DataFrame) -> float:
    d = df_m5.copy()
    d["date"] = d.index.tz_convert("UTC").date
    grp = d.groupby("date")
    daily_rng = (grp["high"].max() - grp["low"].min()) / PIP
    vals = daily_rng.tail(14).values
    if len(vals)==0: return 0.0
    return float(np.mean(vals))

def pick_signal(df: pd.DataFrame, names=None):
    if names is None:
        names = ["session_breakout","volatility_contraction","ema_trend","bollinger_mean_rev","price_action_breakout"]
    for name in names:
        if name not in REGISTRY: 
            continue
        sig = REGISTRY[name]().generate(df).reindex(df.index).iloc[-1]
        if int(sig.get("signal",0)) != 0 and not pd.isna(sig.get("sl")) and not pd.isna(sig.get("tp")):
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

    # Env detect + mode
    key, acct, env = oanda_detect()
    live_flag = os.environ.get("LIVE_TRADING") == "1"
    mode = "OANDA" if (key and acct) else "SIM"
    # enforce practice-only live
    if live_flag and env != "practice":
        live_flag = False

    # Data
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
        state = {"date": now_utc.date().isoformat(), "trades_today": 0, "day_risk_R": 0.0,
                 "last_exec": {}, "done_today": {}, "sent_kill":"", "sent_adr":"", "adr_was_low": False}

    allowed = in_session(now_utc)
    adr_min = float(os.environ.get("AXFL_ADR14_MIN_PIPS","40"))
    adr14 = _adr14_pips(df)
    adr_ok = adr14 >= adr_min

    # Guards + whitelist
    per_day = int(os.environ.get("AXFL_PER_STRAT_PER_DAY","1"))
    cooldown_min = int(os.environ.get("AXFL_STRAT_COOLDOWN_MIN","30"))
    wl = os.environ.get("AXFL_LIVE_STRATS","").strip()
    default_names = ["session_breakout","volatility_contraction","ema_trend","bollinger_mean_rev","price_action_breakout"]
    names = [n for n in default_names if (n in [x.strip() for x in wl.split(",")] if wl else True)]

    # ADR guard alert logic
    dt_iso = now_utc.date().isoformat()
    adr_was_low = state.get("adr_was_low", False)
    if not adr_ok and not adr_was_low:
        if state.get("sent_adr") != dt_iso:
            alert_adr_guard(True, adr14, adr_min)
            state["sent_adr"] = dt_iso
        state["adr_was_low"] = True
    elif adr_ok and adr_was_low:
        alert_adr_guard(False, adr14, adr_min)
        state["adr_was_low"] = False

    # Determine signal
    ks_hit = (abs(state["day_risk_R"]) >= daily_stop_R) or (state["trades_today"] >= max_trades_day)
    strat, side, entry, sl, tp = pick_signal(df, names)
    decision = "NONE"; reason=""; units=0

    # Kill switch alert (debounced daily)
    if ks_hit and state.get("sent_kill") != dt_iso:
        alert_kill_switch(state["day_risk_R"], state["trades_today"], daily_stop_R, max_trades_day)
        state["sent_kill"] = dt_iso

    if not adr_ok:
        decision="SKIP"; reason="adr_guard"
    elif not allowed:
        decision="SKIP"; reason="no_session"
    elif ks_hit:
        decision="SKIP"; reason="kill_switch"
    elif not strat:
        decision="SKIP"; reason="no_signal"
    else:
        # per-strategy limits
        last = state["last_exec"].get(strat)
        done_day = state["done_today"].get(strat)
        if done_day == dt_iso and per_day <= 1:
            decision="SKIP"; reason="daily_limit"
        else:
            if last:
                try:
                    last_dt = pd.to_datetime(last, utc=True)
                    mins = (now_utc - last_dt).total_seconds()/60.0
                    if mins < cooldown_min:
                        decision="SKIP"; reason=f"cooldown_{int(mins)}m"
                except Exception:
                    pass
        if decision=="NONE":
            units = position_units_from_risk(balance, risk_pct, entry, sl, pip_value_per_unit=0.0001)
            decision = "PLACE" if units>0 else "SKIP"
            if decision=="SKIP" and not reason:
                reason="sizing_zero"

    # Act
    action = "SKIPPED"; order_id = "NA"
    if decision=="PLACE":
        oanda_units = units if side==1 else -units
        if live_flag and mode=="OANDA":
            code, resp = cli.place_market_order(instr, oanda_units, sl=sl, tp=tp, tag=strat)
            if code==201 and "orderFillTransaction" in resp:
                action="PLACED"
                order_id = str(resp["orderFillTransaction"].get("id","?"))
                state["day_risk_R"] += 1.0
                state["trades_today"] += 1
                state["last_exec"][strat] = now_utc.isoformat()
                state["done_today"][strat] = dt_iso
            else:
                action="ERROR"; reason=f"http_{code}"
        else:
            action="DRYRUN"
            state["day_risk_R"] += 1.0
            state["trades_today"] += 1
            state["last_exec"][strat] = now_utc.isoformat()
            state["done_today"][strat] = dt_iso

        # Ledger append (restart-safe)
        try:
            os.makedirs("reports", exist_ok=True)
            led_p = "reports/m10_ledger.json"
            try:
                with open(led_p,"r") as __f: ledger = json.load(__f)
            except Exception:
                ledger = {"open":{}, "closed":[]}
            rec = {
                "ts": now_utc.isoformat(),
                "strategy": strat, "side": int(side),
                "entry": float(entry), "sl": float(sl), "tp": float(tp) if not math.isnan(tp) else None,
                "trade_id": order_id, "instrument": instr,
                "mode": ("LIVE" if (live_flag and mode=='OANDA') else "DRYRUN")
            }
            key_k = order_id if order_id not in (None,"NA","?") else f"plan_{int(now_utc.timestamp())}"
            ledger["open"][key_k] = rec
            with open(led_p,"w") as __f: json.dump(ledger,__f)
        except Exception:
            pass

        # Alerts: trade open
        try:
            alert_trade_open(mode, (live_flag and mode=="OANDA"), strat, side, units, entry, sl, tp, adr14)
        except Exception:
            pass

    save_state(state)

    # SUCCESS MARKERS
    print(f"OANDA_EXEC_READY mode={mode} trading={'LIVE' if (live_flag and mode=='OANDA') else 'DRYRUN'} account={(acct or 'NA')} env={(env or 'NA')} instrument={instr}")
    if strat:
        print(f"SIGNAL_DECISION strategy={strat} side={side} entry={entry:.5f} sl={sl:.5f} tp={tp:.5f} units={units}")
    else:
        print("SIGNAL_DECISION strategy=NONE side=0 entry=NA sl=NA tp=NA units=0")
    print(f"ORDER_ACTION action={action} orderID={order_id} reason={reason}")
    print(f"KILL_SWITCH day_total_R={state['day_risk_R']:.2f} trades_today={state['trades_today']} daily_stop_R={daily_stop_R} max_trades_day={max_trades_day} adr14={adr14:.1f} adr_min={adr_min:.1f}")
    wired = "YES" if os.environ.get("DISCORD_WEBHOOK_URL") else "NO"
    print(f"ALERTS_HOOKS wired={wired}")
    print("AXFL_LTO_RESTORE_OK")

    # JSONL event append
    try:
        os.makedirs("reports", exist_ok=True)
        rec = {
            "ts": pd.Timestamp.utcnow().isoformat(timespec="seconds")+"Z",
            "mode": mode, "trading": ("LIVE" if (live_flag and mode=='OANDA') else "DRYRUN"),
            "strategy": (strat or "NONE"), "side": int(side) if strat else 0,
            "entry": (float(entry) if strat else None), "sl": (float(sl) if strat else None), "tp": (float(tp) if strat else None),
            "units": int(units) if strat else 0, "action": action, "reason": reason,
        }
        with open("reports/live_events.jsonl","a") as f:
            f.write(json.dumps(rec)+"\n")
    except Exception:
        pass

if __name__ == "__main__":
    main()
