# Performance Alerts & Trade Notifications Implementation

**Branch:** `feature/perf-alerts`  
**Status:** ✅ COMMITTED & PUSHED  
**Date:** November 5, 2025

## 🎯 Goals Achieved

All requirements have been implemented with zero new dependencies (stdlib only):

1. ✅ **Intel-rich Discord notifications for every automatic trade**
   - OPEN alerts include: instrument, side, units, entry, SL/TP, spread, strategy, reason, account, order ID, trade ID
   - CLOSE alerts include: entry→exit, pips, money PnL (quote ccy), strategy, opened-at (UTC ISO), account, reason

2. ✅ **SQLite trade persistence**
   - Path from env `AXFL_DB` (default: `/opt/axfl/app/data/axfl.db`)
   - Automatic table creation with indexes
   - Records all trades with full lifecycle data

3. ✅ **Scheduled performance alerts**
   - Daily (23:59 UTC), Weekly (Sunday 23:59 UTC), Monthly (last day 23:59 UTC)
   - Totals: PnL (pips & money), #trades, win%, best, worst, avg/trade
   - Per-strategy ranking: trades, win%, pips, money, avg/trade (sorted by money desc, then pips)

4. ✅ **Production-safe implementation**
   - Zero new pip dependencies (stdlib only)
   - Idempotent operations
   - Error handling in all hooks
   - Respects OANDA_ENV and AXFL_LOG_LEVEL

---

## 📁 Files Created/Modified

### New Files

1. **`axfl/notify/trades.py`** (NEW)
   - Discord webhook notifications with rich embeds
   - `open_alert()`: Trade open notifications
   - `close_alert()`: Trade close notifications with PnL
   - `perf_alert()`: Scheduled performance reports
   - Uses `DISCORD_WEBHOOK_URL_FILE` env var

2. **`axfl/metrics/perf.py`** (NEW)
   - SQLite trade logging and performance computation
   - `record_open()`: Log trade opening
   - `record_close()`: Update trade with exit & PnL
   - `compute()`: Calculate daily/weekly/monthly performance
   - Automatic DB setup with indexes

3. **`axfl/metrics/__init__.py`** (NEW)
   - Package initialization

4. **`axfl/hooks.py`** (NEW)
   - Unified trade lifecycle hooks
   - `on_trade_opened()`: Persist to DB + send Discord alert
   - `on_trade_closed()`: Update DB + send Discord alert with PnL
   - Returns `opened_at_iso` for later use in close

### Modified Files

5. **`axfl/portfolio/scheduler.py`** (MODIFIED)
   - Added imports: `os, json, datetime as dt`, `perf`, `perf_alert`
   - Added `_PERF_STATE` path for tracking sent alerts
   - Added `_should_send()`: Check if it's time to send alerts (5-min window)
   - Added `_mark_sent()`: Mark alert as sent to prevent duplicates
   - Added `check_send_performance_alerts()`: Main entry point called from engine loops

6. **`axfl/portfolio/engine.py`** (MODIFIED)
   - Added imports: `check_send_performance_alerts`, `on_trade_opened`, `on_trade_closed`
   - Modified trade open flow:
     - Stores `units` in position dict
     - Calls `on_trade_opened()` after successful broker mirror
     - Stores `opened_at_iso` in position for later use
   - Modified trade close flow:
     - Stores position data before closing
     - Calls `on_trade_closed()` after successful broker close
   - Added `check_send_performance_alerts()` calls in both replay and WebSocket loops
   - Calls happen during status updates (every `status_every_s` interval)

---

## 🔧 Environment Variables

Required:
- **`DISCORD_WEBHOOK_URL_FILE`**: Path to file containing Discord webhook URL
- **`OANDA_ENV`**: Environment label (e.g., "practice", "live") for Discord embeds

Optional:
- **`AXFL_DB`**: SQLite database path (default: `/opt/axfl/app/data/axfl.db`)
- **`AXFL_LOG_LEVEL`**: Logging verbosity (honored by existing code)

---

## 🗄️ Database Schema

Table: `trades`

| Column      | Type    | Description                    |
|-------------|---------|--------------------------------|
| id          | INTEGER | Primary key (auto-increment)   |
| trade_id    | TEXT    | Trade identifier               |
| order_id    | TEXT    | Order identifier               |
| instrument  | TEXT    | Trading pair (e.g., EUR_USD)   |
| strategy    | TEXT    | Strategy name                  |
| side        | TEXT    | buy/sell/long/short            |
| units       | INTEGER | Position size                  |
| entry       | REAL    | Entry price                    |
| exit        | REAL    | Exit price (NULL until closed) |
| pips        | REAL    | PnL in pips (NULL until closed)|
| money       | REAL    | PnL in money (NULL until closed)|
| opened_at   | TEXT    | ISO 8601 timestamp             |
| closed_at   | TEXT    | ISO 8601 timestamp (NULL until closed)|

Indexes:
- `idx_trades_time` on `(opened_at, closed_at)`
- `idx_trades_strategy` on `(strategy)`

---

## 📊 Discord Embed Format

### Trade OPEN
```
**OPEN**
┌─────────────────────────────────────
│ Instrument: EUR_USD
│ Side: BUY
│ Units: 10,000
│ Entry: 1.10000
│ SL / TP: 1.09800 / 1.10200
│ Strategy: lsg
│ Reason: signal
│ Order: #12345
│ TradeID: T-67890
│ Account: practice
│ Spread: 0.6 pips
└─────────────────────────────────────
Color: Green (0x2ECC71)
```

### Trade CLOSE
```
**CLOSE**
┌─────────────────────────────────────
│ Instrument: EUR_USD
│ Strategy: lsg
│ Units: 10,000
│ Entry → Exit: 1.10000 → 1.10050
│ PnL: 5.0 pips • 50.00 USD
│ Opened At (UTC): 2025-11-05T10:30:00Z
│ Reason: tp
│ Order: #12345
│ TradeID: T-67890
│ Account: practice
└─────────────────────────────────────
Color: Green (profit) or Red (loss)
```

### Performance DAILY/WEEKLY/MONTHLY
```
**DAILY PERFORMANCE**
┌─────────────────────────────────────
│ Period: daily
│ Trades: 15
│ Win Rate: 60.0%
│ Pips: 45.3
│ Money: 453.00
│ Best: 120.50
│ Worst: -85.20
│ Avg: 30.20
│
│ #1 lsg
│ Trades 8 • Win 62.5% • PnL 280.00 • Pips 28.0 • Avg 35.00
│
│ #2 breaker
│ Trades 5 • Win 60.0% • PnL 150.00 • Pips 15.0 • Avg 30.00
│
│ #3 orb
│ Trades 2 • Win 50.0% • PnL 23.00 • Pips 2.3 • Avg 11.50
└─────────────────────────────────────
Color: Blue (0x3498DB)
```

---

## ⏰ Alert Schedule

| Period   | Trigger Time   | Window  | State Key Example      |
|----------|----------------|---------|------------------------|
| Daily    | 23:59 UTC      | 5 min   | `daily_20251105`       |
| Weekly   | Sun 23:59 UTC  | 5 min   | `weekly_20251110`      |
| Monthly  | Last day 23:59 | 5 min   | `monthly_202511`       |

State file: `/opt/axfl/app/reports/.perf_state.json`

The scheduler checks every `status_every_s` interval (default: 180s) and sends alerts once per period if within the trigger window.

---

## 🔄 Integration Points

### Trade Open Flow
```python
# In axfl/portfolio/engine.py, after broker.place_market():
if result['success']:
    pos['broker_order_id'] = result['order_id']
    pos['units'] = units  # Store for close hook
    
    # Call hook
    opened_at_iso = on_trade_opened(
        trade_id=result.get('trade_id') or result['order_id'],
        order_id=result['order_id'],
        instrument=symbol,
        strategy=strategy_name,
        side=side,
        units=units,
        entry=entry,
        sl=sl,
        tp=pos.get('tp'),
        spread_pips=spread_pips,
        reason="signal"
    )
    pos['opened_at_iso'] = opened_at_iso  # Store for close hook
```

### Trade Close Flow
```python
# In axfl/portfolio/engine.py, after broker.close_all():
if result['success']:
    # Call hook
    on_trade_closed(
        trade_id=result.get('trade_id') or broker_order_id,
        order_id=broker_order_id,
        instrument=symbol,
        strategy=strategy_name,
        side=side,
        units=units,
        entry=entry,
        exit_price=exit_price,
        opened_at_iso=opened_at_iso,
        reason=reason
    )
```

### Performance Alerts
```python
# In axfl/portfolio/engine.py, in status update loops:
if time.time() - last_status_time >= self.status_every_s:
    self._print_status()
    check_send_performance_alerts()  # Check if it's time to send reports
    last_status_time = time.time()
```

---

## ✅ Testing

### Unit Test
```bash
cd /workspaces/Algotrading-Bot
PYTHONPATH=/workspaces/Algotrading-Bot:$PYTHONPATH python /tmp/test_hooks.py
```

Output:
```
✓ All imports successful
✓ Database created
✓ Trade recorded to DB
✓ Trade closed in DB
✓ Performance computed: 0 trades
✓✓✓ All tests passed! ✓✓✓
```

### Import Test
```bash
python -c "import axfl.notify.trades, axfl.metrics.perf, axfl.hooks; print('✓ Success')"
python -c "from axfl.portfolio.scheduler import check_send_performance_alerts; print('✓ Success')"
python -c "from axfl.portfolio.engine import PortfolioEngine; print('✓ Success')"
```

All tests passed ✅

---

## 🚀 Deployment Notes

1. **Environment Setup**
   ```bash
   # Create webhook file
   echo "https://discord.com/api/webhooks/YOUR/WEBHOOK" > /opt/axfl/secrets/discord_webhook.txt
   
   # Set env vars in systemd service or shell
   export DISCORD_WEBHOOK_URL_FILE=/opt/axfl/secrets/discord_webhook.txt
   export OANDA_ENV=practice  # or "live"
   export AXFL_DB=/opt/axfl/app/data/axfl.db  # optional, this is default
   ```

2. **Directory Creation**
   ```bash
   mkdir -p /opt/axfl/app/data
   mkdir -p /opt/axfl/app/reports
   mkdir -p /opt/axfl/secrets
   chmod 700 /opt/axfl/secrets
   ```

3. **First Run**
   - Database will auto-create on first trade
   - State file will auto-create on first alert check
   - No manual intervention needed

4. **Monitoring**
   - Check SQLite DB: `sqlite3 /opt/axfl/app/data/axfl.db "SELECT * FROM trades LIMIT 10;"`
   - Check state file: `cat /opt/axfl/app/reports/.perf_state.json`
   - Logs show hook errors if Discord webhook fails

---

## 🎓 Key Design Decisions

1. **Stdlib Only**: No new dependencies ensures compatibility and reduces attack surface
2. **Idempotent**: DB operations safe to retry, state file prevents duplicate alerts
3. **Defensive**: Error handling in hooks doesn't crash main engine
4. **Minimal Changes**: Hooks integrated only at broker mirror points (production-safe)
5. **Performance**: Indexes on DB for fast queries, state file prevents unnecessary computation
6. **Flexibility**: Env vars for all paths/settings, works with practice and live accounts

---

## 📝 Future Enhancements (Out of Scope)

- [ ] Add weekly/monthly email digests
- [ ] Dashboard for trade history visualization
- [ ] Real-time trade streaming via WebSocket
- [ ] Multi-account aggregation
- [ ] Trade replay for backtesting validation
- [ ] Export to CSV/JSON for external analysis

---

## 🔗 Related Files

- Discord webhook setup: See existing `DISCORD_ALERTS_*.md` docs
- Systemd service: `deploy/axfl-daily-runner.service`
- Environment template: `deploy/axfl.env.sample`

---

**Implementation Complete ✅**  
Branch: `feature/perf-alerts`  
Commit: `deec8a0`  
Ready for merge to main.
