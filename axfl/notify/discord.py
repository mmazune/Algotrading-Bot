"""
AXFL Discord Notify - Lightweight stdlib-only Discord webhook client
Reuses existing alerts.py infrastructure but provides stdlib fallback
"""
from __future__ import annotations
import os, json, time, urllib.request, urllib.error, pathlib
from typing import List, Dict, Any, Optional

# Colors
GREEN=0x16A34A; RED=0xDC2626; YELLOW=0xF59E0B; BLUE=0x3B82F6; GRAY=0x6B7280

def _resolve_webhook() -> str:
    """Order: DISCORD_WEBHOOK_URL env -> DISCORD_WEBHOOK_URL_FILE env -> reports/.discord_webhook file"""
    env = (os.environ.get("DISCORD_WEBHOOK_URL") or "").strip()
    if env:
        return env
    fp = (os.environ.get("DISCORD_WEBHOOK_URL_FILE") or "").strip()
    cand = [fp] if fp else []
    cand.append("reports/.discord_webhook")
    for p in cand:
        if not p: continue
        try:
            txt = pathlib.Path(p).read_text().strip()
            if txt: return txt
        except Exception:
            pass
    return ""

def _mask(u: str) -> str:
    if not u: return "EMPTY"
    if len(u) <= 16: return "***"
    return u[:8] + "…MASK…" + u[-6:]

def _debug_log(msg:str, code:int|None=None):
    if os.environ.get("ALERTS_DEBUG","0")!="1": return
    try:
        os.makedirs("reports", exist_ok=True)
        with open("reports/alerts_debug.log","a") as f:
            ts=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            f.write(f"{ts} | {msg} | code={code}\n")
    except Exception:
        pass

def _post_json(url: str, payload: dict) -> int:
    """Post JSON to URL, return status code."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type":"application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            code=r.getcode(); _debug_log("POST webhook", code); return code
    except urllib.error.HTTPError as e:
        _debug_log("HTTPError", e.code); return e.code
    except Exception:
        _debug_log("Exception sending", 0); return 0

def send_discord(text: str, *, embeds: Optional[List[Dict[str,Any]]]=None, color:int|None=None) -> int:
    if os.environ.get("ALERTS_ENABLED","1")!="1": return 0
    url = _resolve_webhook()
    _debug_log(f"webhook_source={('env' if os.environ.get('DISCORD_WEBHOOK_URL') else 'file')} value={_mask(url)}")
    if not url: return 0
    payload={"content": text[:1500]}
    if embeds:
        if color is not None:
            for e in embeds: e.setdefault("color", color)
        payload["embeds"]=embeds
    code=_post_json(url, payload)
    return code

def _fmt_money(x: float|None) -> str:
    if x is None: return "NA"
    sign="+" if x>=0 else "−"
    return f"{sign}${abs(x):.2f}"

def _fmt_r(x: float|None) -> str:
    if x is None: return "NA"
    sign="+" if x>=0 else "−"
    return f"{sign}{abs(x):.2f}R"

# Convenience wrappers for common alert types
def alert_trade_open(mode:str, is_live:bool, strat:str, side:int, units:int, entry:float, sl:float, tp:float, adr14:float|None, risk_usd:float|None=None):
    stop_pips = abs(entry-sl)/0.0001 if (entry and sl) else None
    approx_risk = risk_usd
    if approx_risk is None:
        # try ENV base
        try:
            bal=float(os.environ.get("AXFL_BALANCE","200"))
            rp=float(os.environ.get("AXFL_RISK_PCT","0.01"))
            approx_risk = round(bal*rp,2)
        except Exception:
            approx_risk = None
    side_txt="LONG" if side==1 else "SHORT"
    title="TRADE OPEN"
    desc=f"{mode}/{'LIVE' if is_live else 'DRYRUN'} • {strat} • {side_txt}"
    fields=[
        {"name":"Units","value":str(units),"inline":True},
        {"name":"Entry","value":f"{entry:.5f}","inline":True},
        {"name":"SL / TP","value":f"{sl:.5f} / {tp:.5f}","inline":True},
    ]
    if stop_pips is not None:
        fields.append({"name":"Stop (pips)","value":f"{stop_pips:.1f}","inline":True})
    if approx_risk is not None:
        fields.append({"name":"Risk (≈$)","value":f"${approx_risk:.2f}","inline":True})
    if adr14 is not None:
        fields.append({"name":"ADR14","value":f"{adr14:.1f} pips","inline":True})
    code=send_discord(f"**{title}**", embeds=[{"title":title,"description":desc,"fields":fields}], color=BLUE)
    _debug_log("alert_trade_open", code); return code

def alert_trade_close(mode:str, is_live:bool, strat:str, side:int, units:int, entry:float, sl:float, tp:float|None, exit_px:float|None, reason:str, lastR:float|None=None, mfeR:float|None=None, pnl_usd:float|None=None):
    # If lastR not given, compute from entry/sl/exit
    if lastR is None and (entry and sl and exit_px):
        denom=(entry-sl) if side==1 else (sl-entry)
        if denom and denom>0:
            num=(exit_px-entry) if side==1 else (entry-exit_px)
            lastR=num/denom
    color = GREEN if (lastR is not None and lastR>0) else (RED if (lastR is not None and lastR<0) else YELLOW)
    side_txt="LONG" if side==1 else "SHORT"
    title="TRADE CLOSE"
    desc=f"{mode}/{'LIVE' if is_live else 'DRYRUN'} • {strat} • {side_txt} • {reason or '—'}"
    fields=[
        {"name":"Entry → Exit","value":f"{entry:.5f} → {('%.5f'%exit_px) if exit_px else 'NA'}"},
        {"name":"R Multiple","value":_fmt_r(lastR),"inline":True},
        {"name":"PnL (≈)","value":_fmt_money(pnl_usd) if pnl_usd is not None else "NA","inline":True},
    ]
    if mfeR is not None:
        fields.append({"name":"Max Favorable","value":_fmt_r(mfeR),"inline":True})
    code=send_discord(f"**{title}** {_fmt_r(lastR)} {_fmt_money(pnl_usd) if pnl_usd is not None else ''}".strip(), embeds=[{"title":title,"description":desc,"fields":fields}], color=color)
    _debug_log("alert_trade_close", code); return code

def alert_session_begin() -> int:
    """Alert for session beginning."""
    return send_discord("🟢 SESSION_BEGIN - Trading window opened")

def alert_session_end(trades: int, pf: float, win_pct: float, total_r: float) -> int:
    """Alert for session ending with summary."""
    return send_discord(
        f"🔴 SESSION_END - Daily Summary",
        embeds=[{
            "title": "Session Summary",
            "color": 1752220,  # teal
            "fields": [
                {"name": "Trades", "value": str(trades), "inline": True},
                {"name": "PF", "value": f"{pf:.2f}", "inline": True},
                {"name": "Win%", "value": f"{win_pct:.1f}%", "inline": True},
                {"name": "Total R", "value": f"{total_r:.2f}R", "inline": True}
            ]
        }]
    )

def alert_kill_switch(dayR:float, n:int, capR:float, maxN:int):
    text=f"**KILL SWITCH HIT** dayR={dayR:.2f} / cap={capR:.1f}, trades={n}/{maxN}"
    return send_discord(text, embeds=[{"title":"Kill Switch","description":text}], color=RED)

def alert_adr_guard(active:bool, adr14:float, min_pips:float):
    if active:
        text=f"**ADR GUARD ACTIVE** adr14={adr14:.1f} < min={min_pips:.1f}"
        return send_discord(text, embeds=[{"title":"ADR Guard","description":text}], color=YELLOW)
    else:
        text=f"**ADR GUARD CLEARED** adr14={adr14:.1f} ≥ min={min_pips:.1f}"
        return send_discord(text, embeds=[{"title":"ADR Guard","description":text}], color=GREEN)

def alert_adr_guard(active: bool, adr14: float, adr_min: float) -> int:
    """Alert for ADR guard state change."""
    if active:
        return send_discord(
            f"🔒 ADR_GUARD active - Low volatility lock",
            embeds=[{
                "title": "ADR Guard Engaged",
                "color": 15105570,  # orange
                "fields": [
                    {"name": "ADR14", "value": f"{adr14:.1f} pips", "inline": True},
                    {"name": "Minimum", "value": f"{adr_min:.1f} pips", "inline": True}
                ]
            }]
        )
    else:
        return send_discord(
            f"🔓 ADR_GUARD cleared - Volatility restored",
            embeds=[{
                "title": "ADR Guard Cleared",
                "color": 3066993,  # green
                "fields": [
                    {"name": "ADR14", "value": f"{adr14:.1f} pips", "inline": True},
                    {"name": "Minimum", "value": f"{adr_min:.1f} pips", "inline": True}
                ]
            }]
        )

def alert_scheduler_start(interval: int) -> int:
    """Alert for scheduler startup."""
    return send_discord(f"⚙️ SCHEDULER_START - Running every {interval}m")

def alert_scheduler_stop(reason: str = "STOP_file") -> int:
    """Alert for scheduler shutdown."""
    return send_discord(f"⏹️ SCHEDULER_STOPPED - Reason: {reason}")

def alert_error(component: str, error: str) -> int:
    """Red X emoji on exceptions."""
    return send_discord(f"❌ ERROR in {component}: {error}")

# Marker to confirm embeds/colors enabled
def alerts_capabilities() -> str:
    return "embeds=1 colors=1"
