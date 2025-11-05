"""Intel-rich Discord notifications for automatic trades."""
import os, json, urllib.request, datetime

def _read_webhook() -> str:
    path = os.environ["DISCORD_WEBHOOK_URL_FILE"]
    with open(path, "r") as f:
        return f.read().strip()

def _post_embed(title: str, fields: list[dict], color: int) -> None:
    hook = _read_webhook()
    body = {
        "content": f"**{title}**",
        "embeds": [{
            "title": title,
            "color": color,
            "timestamp": datetime.datetime.utcnow().isoformat(timespec="seconds")+"Z",
            "fields": fields
        }]
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(hook, data=data, headers={
        "Content-Type":"application/json","User-Agent":"axfl"
    })
    with urllib.request.urlopen(req, timeout=10) as r:
        r.read()

def _pip_size(instr: str) -> float:
    return 0.01 if instr.endswith("JPY") else 0.0001

def open_alert(*, order_id, trade_id, instrument, side, units, entry, strategy,
               sl=None, tp=None, spread_pips=None, reason:str="signal") -> None:
    account = os.getenv("OANDA_ENV", "practice")
    fields = [
        {"name":"Instrument","value":instrument,"inline":True},
        {"name":"Side","value":str(side).upper(),"inline":True},
        {"name":"Units","value":f"{abs(int(units)):,}","inline":True},
        {"name":"Entry","value":f"{float(entry):.5f}","inline":True},
        {"name":"Strategy","value":strategy,"inline":True},
        {"name":"Reason","value":reason,"inline":True},
        {"name":"Order","value":f"#{order_id}" if order_id else "n/a","inline":True},
        {"name":"TradeID","value":str(trade_id) if trade_id else "n/a","inline":True},
        {"name":"Account","value":account,"inline":True},
    ]
    if sl is not None and tp is not None:
        fields.insert(4, {"name":"SL / TP","value":f"{float(sl):.5f} / {float(tp):.5f}","inline":True})
    if spread_pips is not None:
        fields.append({"name":"Spread","value":f"{float(spread_pips):.1f} pips","inline":True})
    _post_embed("OPEN", fields, 0x2ECC71)

def close_alert(*, order_id, trade_id, instrument, side, units, entry, exit_price,
                strategy, opened_at_iso, reason:str="close") -> None:
    pip = _pip_size(instrument)
    raw = (float(exit_price) - float(entry)) / pip
    pips = raw if str(side).lower() in ("buy","long") else -raw
    money = (float(exit_price) - float(entry)) * (int(units) if str(side).lower() in ("buy","long") else -int(units))
    account = os.getenv("OANDA_ENV", "practice")
    fields = [
        {"name":"Instrument","value":instrument,"inline":True},
        {"name":"Strategy","value":strategy,"inline":True},
        {"name":"Units","value":f"{abs(int(units)):,}","inline":True},
        {"name":"Entry → Exit","value":f"{float(entry):.5f} → {float(exit_price):.5f}","inline":False},
        {"name":"PnL","value":f"{pips:.1f} pips • {money:.2f} {instrument.split('_')[1]}","inline":False},
        {"name":"Opened At (UTC)","value":opened_at_iso,"inline":True},
        {"name":"Reason","value":reason,"inline":True},
        {"name":"Order","value":f"#{order_id}" if order_id else "n/a","inline":True},
        {"name":"TradeID","value":str(trade_id) if trade_id else "n/a","inline":True},
        {"name":"Account","value":account,"inline":True},
    ]
    _post_embed("CLOSE", fields, 0xE74C3C if money < 0 else 0x2ECC71)

def perf_alert(title: str, *, totals: dict, strat_rows: list[dict]) -> None:
    fields: list[dict] = []
    for k in ("period","trades","win_rate","pips","money","best","worst","avg"):
        if k in totals:
            fields.append({"name":k.replace("_"," ").title(),"value":str(totals[k]),"inline":True})
    for row in strat_rows:
        fields.append({
            "name": f"#{row['rank']} {row['strategy']}",
            "value": (f"Trades {row['trades']} • Win {row['win_rate']}% • "
                      f"PnL {row['money']:.2f} • Pips {row['pips']:.1f} • Avg {row['avg']:.2f}"),
            "inline": False
        })
    _post_embed(title, fields, 0x3498DB)
