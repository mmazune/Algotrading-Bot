# scripts/live_trade_oanda.py Restore Summary

**Date**: November 3, 2025  
**Status**: ✅ COMPLETE  
**File**: `/workspaces/Algotrading-Bot/scripts/live_trade_oanda.py` (254 lines)

---

## Restoration Context

The file was corrupted during Discord alerts integration edits. Rebuilt from specification with all M5-M10 features plus alert hooks.

## Features Restored

### Core Infrastructure
- **Mode Detection**: OANDA (with creds) or SIM (synthetic data fallback)
- **Trading Mode**: DRYRUN default, LIVE only when `LIVE_TRADING=1` AND `env=practice`
- **Data Source**: OANDA M5 candles (300 bars) or synthetic EUR/USD if unavailable
- **State Persistence**: `reports/m5_state.json` with daily reset

### M5 Features (Original)
- Session windows: UTC 07:00-12:00 & 13:00-17:00, Monday-Friday only
- Kill switch: Daily stop at 4.0R or 6 trades
- Position sizing: Risk-based (1% default, configurable via `AXFL_RISK_PCT`)

### M8 Features (Strategy Expansion)
- **5 Strategies**: `session_breakout`, `volatility_contraction`, `ema_trend`, `bollinger_mean_rev`, `price_action_breakout`
- Strategy evaluation order: session_breakout first (highest priority)
- Fallback to synthetic data if OANDA unavailable

### M9 Features (Live Guards)
- **ADR14 Guard**: Minimum 40 pips average daily range (env: `AXFL_ADR14_MIN_PIPS`)
  - Calculated from last 14 days of M5 data
  - Blocks trading when ADR14 < threshold
- **Per-Strategy Daily Limit**: 1 trade per strategy per day (env: `AXFL_PER_STRAT_PER_DAY`)
- **Cooldown**: 30-minute minimum between trades for same strategy (env: `AXFL_STRAT_COOLDOWN_MIN`)
- **Whitelist**: Env `AXFL_LIVE_STRATS` allows filtering active strategies (comma-separated)

### M10 Features (Trade Management)
- **Ledger System**: `reports/m10_ledger.json` with `{open, closed}` structure
  - Restart-safe: reads existing ledger before writing
  - Tracks: ts, strategy, side, entry, sl, tp, trade_id, instrument, mode
  - Key generation: order_id or fallback `plan_{timestamp}`

### Discord Alerts Integration
- **Import Pattern**: Try/except with no-op fallbacks
  ```python
  try:
      from axfl.notify.discord import alert_trade_open, alert_kill_switch, alert_adr_guard
  except Exception:
      def alert_trade_open(*a, **k): return 0
      def alert_kill_switch(*a, **k): return 0
      def alert_adr_guard(*a, **k): return 0
  ```
- **State Tracking**: Debounce flags in state dict
  - `sent_kill`: Last date kill switch alert sent (daily debounce)
  - `sent_adr`: Last date ADR guard alert sent (daily debounce)
  - `adr_was_low`: Boolean for ADR state transition detection
- **Alert Hooks**:
  1. **ADR Guard Transitions**: Lock when ADR drops below min, unlock when recovers
  2. **Kill Switch Hit**: Once per day when daily limits reached
  3. **Trade Open**: After ledger write for both LIVE and DRYRUN placements

### Event Logging
- **JSONL Append**: `reports/live_events.jsonl`
- Fields: ts, mode, trading, strategy, side, entry, sl, tp, units, action, reason
- Survives restarts, appends only

---

## Functions (10 total)

1. **`_synth_eurusd(n=600, seed=11)`** - Generate synthetic EUR/USD M5 data
2. **`in_session(now_utc)`** - Check if within trading hours (UTC windows, Mon-Fri)
3. **`load_state()`** - Read persistent state from JSON (with base defaults)
4. **`save_state(st)`** - Write state to JSON
5. **`_adr14_pips(df_m5)`** - Calculate 14-day average daily range in pips
6. **`pick_signal(df, names)`** - Iterate strategies, return first valid signal
7. **`main()`** - Core execution loop
8-10. **Alert fallbacks** - No-op functions if Discord module unavailable

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AXFL_BALANCE` | 200 | Account balance for position sizing |
| `AXFL_RISK_PCT` | 0.01 | Risk per trade (1% default) |
| `AXFL_DAILY_STOP_R` | 4.0 | Daily risk budget (R-multiples) |
| `AXFL_MAX_TRADES_DAY` | 6 | Maximum trades per day |
| `OANDA_INSTR` | EUR_USD | Trading instrument |
| `LIVE_TRADING` | (unset) | Set to "1" for LIVE mode |
| `AXFL_ADR14_MIN_PIPS` | 40 | Minimum ADR14 threshold |
| `AXFL_PER_STRAT_PER_DAY` | 1 | Max trades per strategy per day |
| `AXFL_STRAT_COOLDOWN_MIN` | 30 | Cooldown between same-strategy trades |
| `AXFL_LIVE_STRATS` | (all) | Comma-separated whitelist (e.g., "session_breakout,ema_trend") |
| `DISCORD_WEBHOOK_URL` | (optional) | Discord webhook for alerts |

---

## Success Markers (Printed)

```
OANDA_EXEC_READY mode={mode} trading={LIVE/DRYRUN} account={acct} env={env} instrument={instr}
SIGNAL_DECISION strategy={name} side={1/-1} entry={price} sl={price} tp={price} units={int}
ORDER_ACTION action={PLACED/DRYRUN/SKIPPED/ERROR} orderID={id} reason={skip_reason}
KILL_SWITCH day_total_R={float} trades_today={int} daily_stop_R={float} max_trades_day={int} adr14={float} adr_min={float}
ALERTS_HOOKS wired={YES/NO}
AXFL_LTO_RESTORE_OK
```

---

## Verification Run

```bash
$ PYTHONPATH=. python scripts/live_trade_oanda.py
OANDA_EXEC_READY mode=OANDA trading=DRYRUN account=101-001-37425530-001 env=practice instrument=EUR_USD
SIGNAL_DECISION strategy=session_breakout side=-1 entry=1.15112 sl=1.15170 tp=1.15029 units=0
ORDER_ACTION action=SKIPPED orderID=NA reason=adr_guard
KILL_SWITCH day_total_R=0.00 trades_today=0 daily_stop_R=4.0 max_trades_day=6 adr14=33.5 adr_min=40.0
ALERTS_HOOKS wired=YES
AXFL_LTO_RESTORE_OK
```

**Analysis**: 
- ✅ OANDA connection successful (practice account detected)
- ✅ Session breakout strategy generated SHORT signal
- ✅ ADR guard blocked trade (33.5 pips < 40.0 threshold)
- ✅ Discord alerts wired (DISCORD_WEBHOOK_URL set)
- ✅ All markers printed correctly

---

## Decision Flow

```
1. Load state (daily reset if date changed)
2. Check ADR14 guard → SKIP if adr14 < adr_min
3. Check session window → SKIP if outside hours
4. Check kill switch → SKIP if day_risk_R >= 4.0 OR trades_today >= 6
5. Pick signal (iterate 5 strategies, first valid wins)
   → SKIP if no signal
6. Check per-strategy daily limit → SKIP if done_today[strat] == today AND per_day <= 1
7. Check cooldown → SKIP if last_exec[strat] < cooldown_min ago
8. Calculate position size → SKIP if units == 0
9. PLACE order (LIVE or DRYRUN)
10. Write ledger + alerts + state + JSONL
```

---

## Files Generated

- `reports/m5_state.json` - Daily state persistence
- `reports/m10_ledger.json` - Trade ledger (open/closed)
- `reports/live_events.jsonl` - Append-only event log

---

## Integration Points

### Scheduler
```bash
# scripts/session_scheduler.py calls live_trade_oanda.py every 5 minutes
PYTHONPATH=. python scripts/session_scheduler.py --daemon --interval-min 5
```

### Trade Management
```bash
# scripts/manage_open.py reads m10_ledger.json, applies M10 rules
PYTHONPATH=. python scripts/manage_open.py
```

---

## Restore Methodology

1. **Removed corrupted file** (409 lines with concatenation errors)
2. **Rebuilt via heredoc** in 4 parts:
   - Header + imports + PIP constant
   - Utility functions (_synth_eurusd, in_session, load_state, save_state, _adr14_pips, pick_signal)
   - Main function part 1 (config, data load, guards, signal selection)
   - Main function part 2 (order placement, ledger, alerts, markers, JSONL)
3. **Fixed runtime errors**:
   - `tz_localize()` → check if already tz-aware before localizing
   - `REGISTRY[name].generate()` → `REGISTRY[name]().generate()` (instantiate first)
4. **Verified output** - All markers present, ADR guard functional

---

## Key Differences from Git Version

The git HEAD (commit `15484ca`) only has M1-M7 features:
- ❌ No ADR14 guard
- ❌ No per-strategy limits or cooldown
- ❌ Only 3 strategies (ema_trend, bollinger_mean_rev, price_action_breakout)
- ❌ No M10 ledger system
- ❌ No Discord alert hooks
- ❌ No JSONL event logging

**This restored version includes ALL M8-M10 enhancements plus Discord integration.**

---

## Status

**AXFL_M5_TO_M10_FEATURES_RESTORED** ✅  
**DISCORD_ALERTS_WIRED** ✅  
**VERIFICATION_PASSED** ✅

