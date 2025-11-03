#!/usr/bin/env python3
"""
Alert Session End Summary
Reads today's closed trades from ledger and sends Discord summary.
"""
import os, json
from datetime import datetime, timezone

try:
    from axfl.notify.discord import alert_session_end
except Exception:
    def alert_session_end(*a, **k): return 0

def main():
    led_path = "reports/m10_ledger.json"
    if not os.path.exists(led_path):
        return
    
    with open(led_path, "r") as f:
        ledger = json.load(f)
    
    # Filter today's closed trades
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    closed_today = []
    for rec in ledger.get("closed", []):
        ts = rec.get("exit_ts", "")
        if ts.startswith(today):
            closed_today.append(rec)
    
    if not closed_today:
        return
    
    # Calculate stats
    trades = len(closed_today)
    winners = sum(1 for r in closed_today if r.get("lastR", 0) > 0)
    win_pct = (winners / trades * 100) if trades > 0 else 0
    total_r = sum(r.get("lastR", 0) for r in closed_today)
    
    # Profit factor: sum(winners) / abs(sum(losers))
    win_r = sum(r.get("lastR", 0) for r in closed_today if r.get("lastR", 0) > 0)
    loss_r = abs(sum(r.get("lastR", 0) for r in closed_today if r.get("lastR", 0) < 0))
    pf = (win_r / loss_r) if loss_r > 0 else (999 if win_r > 0 else 0)
    
    alert_session_end(trades, pf, win_pct, total_r)
    print(f"SESSION_END_SUMMARY trades={trades} pf={pf:.2f} win_pct={win_pct:.1f} total_r={total_r:.2f}")

if __name__ == "__main__":
    main()
