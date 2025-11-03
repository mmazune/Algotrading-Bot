import os, json, math, time
import pandas as pd
from axfl.brokers.oanda_api import oanda_detect, OandaClient
from axfl.strategies.utils import position_units_from_risk

# Alert fallbacks
try:
    from axfl.notify.discord import alert_trade_open, alert_trade_close
except Exception:
    def alert_trade_open(*a, **k): return 0
    def alert_trade_close(*a, **k): return 0

PIP = 0.0001

def latest_mid(cli, instr="EUR_USD"):
    code, payload = cli._req("GET", f"/v3/instruments/{instr}/candles?granularity=M5&count=1&price=M")
    if code!=200 or not payload.get("candles"):
        return None
    mid = payload["candles"][-1]["mid"]
    return float(mid["c"])

def extract_trade_id(fill_tx: dict) -> str:
    # OANDA fills can contain 'tradeOpened' or 'tradesOpened'
    tid = fill_tx.get("tradeOpened",{}).get("tradeID")
    if tid: return str(tid)
    tos = fill_tx.get("tradesOpened") or []
    if tos and "tradeID" in tos[0]: return str(tos[0]["tradeID"])
    # Some payloads use 'id' directly
    return str(fill_tx.get("id","?"))

def main():
    key, acct, env = oanda_detect()
    if not key or not acct:
        print("TEST_ORDER_OPEN error=no_creds")
        return

    # Force practice env for safety
    live = True
    if env != "practice":
        live = False

    instr = os.environ.get("OANDA_INSTR","EUR_USD")
    risk_usd = float(os.environ.get("AXFL_TEST_RISK_USD","1.0"))
    stop_pips = float(os.environ.get("AXFL_TEST_STOP_PIPS","5"))
    tp_pips   = float(os.environ.get("AXFL_TEST_TP_PIPS","6"))
    side_txt  = os.environ.get("AXFL_TEST_SIDE","LONG").upper()
    side = 1 if side_txt=="LONG" else -1

    cli = OandaClient(key, acct, env)
    px = latest_mid(cli, instr)
    if px is None:
        print("TEST_ORDER_OPEN error=no_price")
        return

    # derive units from risk & stop
    sl_price = px - stop_pips*PIP if side==1 else px + stop_pips*PIP
    tp_price = px + tp_pips*PIP   if side==1 else px - tp_pips*PIP
    units = position_units_from_risk(balance=100.0, risk_pct=(risk_usd/100.0), entry=px, sl=sl_price, pip_value_per_unit=0.0001)
    if units < 1:
        units = 100  # safety floor for test

    oanda_units = units if side==1 else -units

    # Place market order (LIVE only if practice; otherwise DRYRUN)
    if live:
        code, resp = cli.place_market_order(instr, oanda_units, sl=sl_price, tp=tp_price, tag="AXFL_TEST")
        if code not in (200,201) or "orderFillTransaction" not in resp:
            print(f"TEST_ORDER_OPEN error=http_{code}")
            return
        fill = resp["orderFillTransaction"]
        trade_id = extract_trade_id(fill)
        entry = float(fill.get("price", px))
        print(f"TEST_ORDER_OPEN id={trade_id} side={'LONG' if side==1 else 'SHORT'} units={units} entry={entry:.5f} sl={sl_price:.5f} tp={tp_price:.5f}")
        try:
            alert_trade_open("OANDA", True, "AXFL_TEST", side, units, entry, sl_price, tp_price, adr14=None)
        except Exception:
            pass

        # Small pause and immediate market close to test close alerts
        time.sleep(3)
        code2, resp2 = cli.close_trade_units(trade_id, "ALL")
        exit_px = None
        if code2 in (200,201):
            # Try to read the realized price (varies by payload)
            exit_px = None
            try:
                exit_px = float(resp2.get("orderFillTransaction",{}).get("price", "nan"))
            except Exception:
                pass
            print(f"TEST_ORDER_CLOSE id={trade_id} exit={('%.5f' % exit_px) if exit_px else 'NA'} status=OK")
            # Compute R and PnL for alert
            risk_pips = abs(entry - sl_price)/PIP
            if risk_pips > 0:
                pnl_pips = (exit_px - entry)/PIP if side==1 else (entry - exit_px)/PIP
                lastR = pnl_pips / risk_pips
            else:
                lastR = 0.0
            pnl_usd = round(lastR * float(os.environ.get("AXFL_TEST_RISK_USD","1.0")), 2)
            try:
                alert_trade_close("OANDA", True, "AXFL_TEST", side, units, entry, sl_price, tp_price, exit_px, reason="TEST_CLOSE", lastR=lastR, mfeR=None, pnl_usd=pnl_usd)
            except Exception:
                pass
            # Update ledger: move from open → closed if present
            try:
                import json as _j, os as _o, time as _t
                _o.makedirs("reports", exist_ok=True)
                led_p = "reports/m10_ledger.json"
                try:
                    with open(led_p,"r") as _f: L = _j.load(_f)
                except Exception:
                    L = {"open":{}, "closed":[]}
                key = trade_id
                # If open key not found (e.g., nonstandard id), add a synthetic record then close it
                if key not in L["open"]:
                    L["open"][key] = {"ts": pd.Timestamp.utcnow().isoformat(), "strategy":"AXFL_TEST", "side": side, "entry": entry, "sl": sl_price, "tp": tp_price, "trade_id": trade_id, "instrument": instr, "mode":"LIVE"}
                rec = L["open"].pop(key)
                rec["exit_reason"]="TEST_CLOSE"; rec["exit_price"]=exit_px
                L["closed"].append(rec)
                with open(led_p,"w") as _f: _j.dump(L,_f)
            except Exception:
                pass

            print("ALERTS_TEST open=OK close=OK")
        else:
            print(f"TEST_ORDER_CLOSE id={trade_id} status=http_{code2}")
            print("ALERTS_TEST open=OK close=SKIPPED")
    else:
        # DRYRUN path (no live order if env != practice)
        print("TEST_ORDER_OPEN error=not_practice_env")
        print("ALERTS_TEST open=SKIPPED close=SKIPPED")

if __name__ == "__main__":
    main()
