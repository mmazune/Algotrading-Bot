# AXFL Discord Alerts - Quick Reference

## Overview
Comprehensive Discord webhook notification system for all AXFL trading events using stdlib-only (urllib) implementation.

## Setup

### 1. Environment Variable
```bash
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN"
```

### 2. Test Alerts
```bash
PYTHONPATH=. python -c "from axfl.notify.discord import send_discord; send_discord('AXFL Test Alert')"
```

## Alert Events

### **SCHEDULER_START** (Gear ⚙️)
- **When**: Scheduler starts
- **Function**: `alert_scheduler_start(interval_sec)`
- **Example**: "⚙️ AXFL Scheduler STARTED (interval: 300s)"

### **SCHEDULER_STOP** (Stop 🛑)
- **When**: STOP file detected or manual shutdown
- **Function**: `alert_scheduler_stop(reason)`
- **Example**: "🛑 AXFL Scheduler STOPPED (reason: STOP_file)"

### **TRADE_OPEN** (Blue Embed 🔵)
- **When**: Trade placed (LIVE or DRYRUN)
- **Function**: `alert_trade_open(mode, is_live, strategy, side, units, entry, sl, tp, adr14)`
- **Fields**: Strategy, Side, Units, Entry, SL, TP, ADR14, Mode
- **Example**: "TRADE OPEN | LSG | LONG | 2000 units @ 1.08450"

### **TRADE_CLOSE** (Green/Red Embed)
- **When**: Trade closed (manage_open.py)
- **Function**: `alert_trade_close(mode, is_live, strategy, side, reason, mfeR, lastR)`
- **Color**: Green if lastR ≥ 0, Red if negative
- **Fields**: Strategy, Side, Reason, MFE, Final P/L
- **Example**: "TRADE CLOSED | ORB | LONG | Breakeven | MFE: +1.2R | Final: +0.0R"

### **KILL_SWITCH_HIT** (Red Embed 🔴)
- **When**: Daily limits reached (4.0R or 6 trades)
- **Function**: `alert_kill_switch(day_r, trades, daily_stop_r, max_trades)`
- **Debounced**: Once per day via `sent_kill` state flag
- **Example**: "🔴 KILL SWITCH ENGAGED | Day Risk: 4.0R/4.0R | Trades: 6/6"

### **ADR_GUARD** (Orange/Green)
- **When**: ADR14 drops below 40 pips (lock) or recovers above (unlock)
- **Function**: `alert_adr_guard(is_active, adr14, adr_min)`
- **Debounced**: Tracks state transitions via `adr_was_low` flag
- **Lock**: "🔒 ADR Guard ENGAGED | ADR14: 35.2 pips (min: 40.0)"
- **Unlock**: "✅ ADR Guard CLEARED | ADR14: 42.8 pips (min: 40.0)"

### **SESSION_END** (Teal Embed 🏁)
- **When**: Session flips from active→inactive (called by scheduler)
- **Function**: `alert_session_end(trades, pf, win_pct, total_r)`
- **Fields**: Trades, Profit Factor, Win%, Total R
- **Example**: "SESSION SUMMARY | Trades: 4 | PF: 1.82 | Win%: 50.0% | Total R: +2.4"

### **ERROR** (Red X ❌)
- **When**: Exception caught in critical paths
- **Function**: `alert_error(component, error_msg)`
- **Example**: "❌ ERROR in live_trade_oanda: KeyError 'candles'"

## File Modifications

### **scripts/live_trade_oanda.py**
```python
# Imports (with fallback)
try:
    from axfl.notify.discord import alert_trade_open, alert_kill_switch, alert_adr_guard
except Exception:
    def alert_trade_open(*a, **k): return 0
    def alert_kill_switch(*a, **k): return 0
    def alert_adr_guard(*a, **k): return 0

# State flags for debouncing
state = {
    "sent_kill": "",      # Last date kill switch alert sent
    "sent_adr": "",       # Last date ADR guard alert sent
    "adr_was_low": False  # ADR state tracking
}

# ADR guard transitions
if not adr_ok and not adr_was_low:
    if state.get("sent_adr") != dt_iso:
        alert_adr_guard(True, adr14, adr_min)  # Lock
        state["sent_adr"] = dt_iso
    state["adr_was_low"] = True
elif adr_ok and adr_was_low:
    alert_adr_guard(False, adr14, adr_min)  # Unlock
    state["adr_was_low"] = False

# Kill switch (daily debounce)
if ks_hit and state.get("sent_kill") != dt_iso:
    alert_kill_switch(day_r, trades, daily_stop_r, max_trades)
    state["sent_kill"] = dt_iso

# Trade placement
alert_trade_open(mode, live_flag and mode=="OANDA", strat, side, units, entry, sl, tp, adr14)
```

### **scripts/manage_open.py**
```python
try:
    from axfl.notify.discord import alert_trade_close
except Exception:
    def alert_trade_close(*a, **k): return 0

# On LIVE close
if code in (200,201):
    alert_trade_close(mode, True, rec["strategy"], rec["side"], reason, mfeR, lastR)
```

### **scripts/session_scheduler.py**
```python
try:
    from axfl.notify.discord import alert_scheduler_start, alert_scheduler_stop
except Exception:
    def alert_scheduler_start(*a, **k): return 0
    def alert_scheduler_stop(*a, **k): return 0

# On startup
alert_scheduler_start(interval * 60)

# On shutdown
if os.path.exists("reports/STOP"):
    alert_scheduler_stop("STOP_file")
```

### **scripts/alerts_summary.py** (NEW)
- Called by scheduler on session end
- Reads `reports/m10_ledger.json`
- Filters today's closed trades
- Calculates: PF, Win%, Total R
- Calls: `alert_session_end(...)`

## Discord Embed Colors

| Event | Color | Hex |
|-------|-------|-----|
| TRADE_OPEN | Blue | `0x3498db` |
| TRADE_CLOSE (Win) | Green | `0x2ecc71` |
| TRADE_CLOSE (Loss) | Red | `0xe74c3c` |
| KILL_SWITCH | Red | `0xe74c3c` |
| ADR_GUARD (Lock) | Orange | `0xe67e22` |
| ADR_GUARD (Unlock) | Green | `0x2ecc71` |
| SESSION_END | Teal | `0x1abc9c` |

## Testing

### Manual Test (No Scheduler)
```bash
# 1. Set webhook URL
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."

# 2. Test scheduler start
PYTHONPATH=. python scripts/session_scheduler.py --oneshot

# 3. Test live trade (DRYRUN)
PYTHONPATH=. python scripts/live_trade_oanda.py

# 4. Test manage open
PYTHONPATH=. python scripts/manage_open.py

# 5. Test session summary
PYTHONPATH=. python scripts/alerts_summary.py
```

### Full Integration Test
```bash
# Daemon mode (with alerts)
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
PYTHONPATH=. python scripts/session_scheduler.py --daemon --interval-min 5
```

## Debouncing Logic

### Daily Debounce
- **Kill Switch**: `sent_kill` = last date string (YYYY-MM-DD)
- **ADR Guard**: `sent_adr` = last date string (YYYY-MM-DD)
- Prevents duplicate alerts on same day

### State Transitions
- **ADR Guard**: Uses `adr_was_low` boolean to track transitions
  - Only alerts when ADR crosses threshold (not every tick)
  - Sends "lock" when ADR drops below min
  - Sends "unlock" when ADR recovers above min

## Architecture

### Module: `axfl/notify/discord.py`
- **163 lines** stdlib-only (urllib.request, urllib.parse, json)
- **9 functions**: 1 base sender + 8 event-specific alerts
- **No dependencies**: Zero external packages (no requests)
- **Fallback pattern**: All imports wrapped in try/except with no-op fallbacks

### Integration Points
1. **live_trade_oanda.py**: Trade placement, kill switch, ADR guard
2. **manage_open.py**: Trade exits
3. **session_scheduler.py**: Scheduler lifecycle
4. **alerts_summary.py**: Session end summary

## Success Markers
```
ALERTS_READY transport=webhook reuse=NO module=axfl/notify/discord.py
ALERT_EVENTS wired=[SCHEDULER_START,SCHEDULER_STOP,TRADE_OPEN,TRADE_CLOSE,KILL_SWITCH_HIT,ADR_GUARD,SESSION_END,ERROR]
ALERT_FILES created=[axfl/notify/discord.py,axfl/notify/__init__.py,scripts/alerts_summary.py] modified=[scripts/live_trade_oanda.py,scripts/manage_open.py,scripts/session_scheduler.py]
DEBOUNCE_FLAGS state=[sent_kill,sent_adr,adr_was_low] scope=per_day
AXFL_ALERTS_OK
```

## Notes
- All alerts are **non-blocking** (best-effort, fail silently)
- Webhook URL is **optional** (no-op if not set)
- Alerts fire in **both LIVE and DRYRUN** modes (differentiated by `mode` field)
- Session summary only fires when trades closed **today**
- ADR guard state persists across scheduler restarts (in m5_state.json)
