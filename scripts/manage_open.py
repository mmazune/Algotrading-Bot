import os, json, pandas as pd, numpy as np
from axfl.brokers.oanda_api import oanda_detect, OandaClient
from axfl.engine.trade_rules import TradeSnapshot, should_close

try:
    from axfl.notify.discord import alert_trade_close
except Exception:
    def alert_trade_close(*a, **k): return 0

PIP = 0.0001

def load_ledger(path="reports/m10_ledger.json"):
    if not os.path.exists(path):
        return {"open":{}, "closed":[]}
    try:
        with open(path,"r") as f: return json.load(f)
    except Exception:
        return {"open":{}, "closed":[]}

def save_ledger(ledger, path="reports/m10_ledger.json"):
    with open(path,"w") as f: json.dump(ledger,f)

def main():
    os.makedirs("reports", exist_ok=True)
    ledger = load_ledger()

    key, acct, env = oanda_detect()
    mode = "OANDA" if (key and acct) else "SIM"
    instr = os.environ.get("OANDA_INSTR","EUR_USD")
    live_flag = os.environ.get("LIVE_TRADING") == "1"

    # get latest M5 to compute MFE/lastR
    last_close = None; bar_hi = None; bar_lo = None
    if mode=="OANDA":
        cli = OandaClient(key, acct, env)
        code, payload = cli.latest_m5(instr)
        if code==200 and payload.get("candles"):
            bars = payload["candles"]
            # use the last fully completed bar if available, else last
            b = bars[-1]
            mid = b.get("mid",{})
            last_close = float(mid.get("c","nan"))
            bar_hi = float(mid.get("h","nan"))
            bar_lo = float(mid.get("l","nan"))
    if last_close is None or np.isnan(last_close):
        print("M10_MANAGE mode=SIM actions=0 would_close=0 reason=no_market_data")
        return

    actions = 0; would = 0
    # OANDA open trades dictionary (for live close)
    live_trades = {}
    if mode=="OANDA":
        code, ot = cli.open_trades()
        if code==200:
            for t in ot.get("trades", []):
                live_trades[str(t.get("id"))] = t

    # iterate ledger open items
    to_close = []
    for k, rec in list(ledger["open"].items()):
        snap = TradeSnapshot(side=int(rec["side"]), entry=float(rec["entry"]), sl=float(rec["sl"]), tp=(float(rec["tp"]) if rec.get("tp") is not None else None))
        close_now, reason, mfeR, lastR = should_close(snap.entry, last_close, bar_hi, bar_lo, snap)

        if not close_now:
            continue

        trade_id = rec.get("trade_id")
        if live_flag and mode=="OANDA" and trade_id and trade_id in live_trades:
            # live close at market
            try:
                code, resp = cli.close_trade_units(trade_id, "ALL")
                if code in (200,201):
                    actions += 1
                    rec["exit_reason"] = reason
                    rec["exit_price"]  = last_close
                    rec["mfeR"] = round(mfeR,3); rec["lastR"] = round(lastR,3)
                    to_close.append(k)
                    # Send trade close alert with PnL
                    risk_pct = float(os.environ.get("AXFL_RISK_PCT","0.01"))
                    approx_bal = None
                    if mode=="OANDA":
                        try:
                            code_b, summ = cli._req("GET", f"/v3/accounts/{acct}/summary")
                            if code_b==200: approx_bal = float(summ["account"]["balance"])
                        except Exception:
                            approx_bal = None
                    if approx_bal is None:
                        approx_bal = float(os.environ.get("AXFL_BALANCE","200"))
                    pnl_usd = round(float(rec.get("lastR",0.0)) * approx_bal * risk_pct, 2)
                    try:
                        alert_trade_close(mode, True, rec["strategy"], int(rec["side"]), int(rec.get("units",0) or 0),
                                          float(rec["entry"]), float(rec["sl"]), (float(rec["tp"]) if rec.get("tp") is not None else None),
                                          float(rec.get("exit_price") or 0.0), rec.get("exit_reason",""),
                                          lastR=float(rec.get("lastR",0.0)), mfeR=float(rec.get("mfeR",0.0)), pnl_usd=pnl_usd)
                    except Exception:
                        pass
                else:
                    # failed to close, mark as would_close
                    would += 1
            except Exception:
                would += 1
        else:
            # DRYRUN or not found -> would_close
            would += 1
    # move closed records
    for k in to_close:
        ledger["closed"].append(ledger["open"].pop(k))

    save_ledger(ledger)
    print(f"M10_MANAGE mode={mode} actions={actions} would_close={would} open={len(ledger['open'])} closed={len(ledger['closed'])}")

if __name__ == "__main__":
    main()
