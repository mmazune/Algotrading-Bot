# Go-Live v2: OANDA Mirroring with Reconciliation & Recovery

**Version**: 2.0  
**Status**: Production Ready ✅  
**Date**: October 20, 2025

---

## Overview

Go-Live v2 adds production-grade OANDA broker mirroring with:

1. **Strong Guarantees**: Idempotent orders, client tagging, retry-safe operations
2. **Reconciliation & Recovery**: Startup sync, conflict detection, safe flattening
3. **Journal Persistence**: SQLite-backed order/trade tracking
4. **Intraday Digest**: On-demand P&L reports with Discord integration

---

## Architecture

```
AXFL Paper Trading (Source of Truth)
         ↓
    [Journal]  ← SQLite persistence
         ↓
   [Reconcile] ← Startup sync
         ↓
  [OANDA Broker] ← Idempotent mirroring
```

**Key Principle**: AXFL remains the source of truth. Broker failures are logged but do not affect AXFL P&L tracking.

---

## Journal Schema

### SQLite Database: `data/journal.db`

#### Table: `broker_orders`
Broker-side orders with client tags for idempotency.

| Column | Type | Description |
|--------|------|-------------|
| `order_id` | TEXT PRIMARY KEY | Broker order ID |
| `client_tag` | TEXT UNIQUE | AXFL::strategy::symbol::ts::uuid |
| `symbol` | TEXT | Trading symbol |
| `side` | TEXT | 'long' or 'short' |
| `units` | INTEGER | Position size |
| `entry` | REAL | Entry price |
| `sl` | REAL | Stop loss |
| `tp` | REAL | Take profit |
| `status` | TEXT | 'open' or 'closed' |
| `opened_at` | TEXT | ISO timestamp |
| `closed_at` | TEXT | ISO timestamp |
| `extra` | TEXT | JSON metadata |

#### Table: `axfl_trades`
AXFL portfolio trades.

| Column | Type | Description |
|--------|------|-------------|
| `axfl_id` | TEXT PRIMARY KEY | Unique AXFL trade ID |
| `symbol` | TEXT | Trading symbol |
| `strategy` | TEXT | Strategy name |
| `side` | TEXT | 'long' or 'short' |
| `entry` | REAL | Entry price |
| `sl` | REAL | Stop loss |
| `tp` | REAL | Take profit |
| `r` | REAL | Risk multiple (R) |
| `pnl` | REAL | Profit/loss in USD |
| `opened_at` | TEXT | ISO timestamp |
| `closed_at` | TEXT | ISO timestamp |
| `extra` | TEXT | JSON metadata |

#### Table: `map`
Links AXFL trades to broker orders.

| Column | Type | Description |
|--------|------|-------------|
| `axfl_id` | TEXT | AXFL trade ID |
| `order_id` | TEXT | Broker order ID |

PRIMARY KEY: `(axfl_id, order_id)`

#### Table: `events`
Diagnostic events (reconciliation, conflicts, etc.).

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PRIMARY KEY | Auto-increment |
| `ts` | TEXT | ISO timestamp |
| `level` | TEXT | 'INFO', 'WARN', 'ERROR' |
| `kind` | TEXT | Event type |
| `payload` | TEXT | JSON data |

---

## Idempotent Order Tagging

### Client Tag Format
```
AXFL::{strategy}::{symbol}::{yyyymmddHHMMss}::{uuid8}
```

**Example**:
```
AXFL::lsg::EURUSD::20251020143022::a7b3f9e1
```

### Idempotency Guarantee
- Before placing order, check if an order with the same client tag exists (last 24h)
- If found, return existing order ID (no duplicate)
- Handles network retries, crashes, and duplicate submissions

### Implementation (axfl/brokers/oanda.py)
```python
def place_market(..., client_tag):
    # Check for existing order
    existing = self._find_order_by_client_tag(client_tag)
    if existing:
        return {'success': True, 'order_id': existing['order_id'], 'idempotent': True}
    
    # Place new order
    # ...
```

---

## Reconciliation Policy

### Startup Reconciliation (`on_start()`)

**Objective**: Ensure broker positions match journal at system start.

**Flow**:
1. Fetch broker open positions
2. Fetch journal open positions
3. Compare: find orphaned broker positions (not in journal)
4. If `flatten_on_conflict=True`: close orphaned positions
5. Log all actions to `events` table

**Safety Config**:
```python
safety = {
    'flatten_on_conflict': True,  # Auto-close orphans
    'max_retries': 3               # Retry on transient errors
}
```

### Pending Mappings (`link_pending()`)

**Objective**: Link unmapped AXFL trades to broker orders.

**Strategies**:
1. **Client Tag Match**: Exact match on `client_tag`
2. **Time/Price Proximity**: Within 5 minutes + same instrument

**Example**:
```python
reconcile_engine.link_pending()
# Returns: number of trades successfully linked
```

---

## Crash Recovery

### Scenario 1: AXFL Crash After Trade Open

**State**:
- AXFL trade recorded in journal
- Broker order placed
- System crashes before mapping recorded

**Recovery**:
1. Restart → `on_start()` runs
2. `link_pending()` finds unmapped AXFL trade
3. Searches broker for order by `client_tag`
4. Links trade to order in `map` table

### Scenario 2: Broker Failure During Open

**State**:
- AXFL trade opened (in journal)
- Broker order failed (network error)

**Recovery**:
1. Journal shows `unmapped_trades > 0`
2. Manual reconciliation: `make recon`
3. Review `events` table for errors
4. Optionally retry via CLI or flatten orphan

### Scenario 3: Orphaned Broker Position

**State**:
- Broker has open position
- No corresponding journal entry (e.g., manual trade or data loss)

**Recovery**:
1. `on_start()` detects orphan
2. If `flatten_on_conflict=True`: closes position
3. Logs `FLATTEN_ORPHAN` event with reason

---

## CLI Workflows

### 1. Reconciliation Check

```bash
make recon
```

**Output**:
```
###BEGIN-AXFL-RECON###
{"ok":true,"broker_positions":0,"journal_positions":0,"flattened":0,"linked":0,"errors":[]}
###END-AXFL-RECON###
```

**Use Cases**:
- Pre-flight check before going live
- Post-crash recovery
- Daily health check

---

### 2. Live Trading with OANDA

```bash
make live_oanda_ws
```

**Flow**:
1. Load OANDA broker credentials from env
2. Run startup reconciliation
3. Initialize portfolio engine
4. Start WebSocket streaming (or fallback to replay)
5. Print `LIVE-PORT` JSON status every N seconds

**Output** (first status):
```
###BEGIN-AXFL-LIVE-PORT###
{"ok":true,"mode":"ws","source":"finnhub","interval":"5m",...,"journal":{"enabled":true,"mapped":3,"unmapped":0},...}
###END-AXFL-LIVE-PORT###
```

**Journal Monitoring**:
```json
"journal": {
  "enabled": true,
  "mapped": 3,      // Trades successfully linked to broker
  "unmapped": 0     // Trades pending broker link
}
```

---

### 3. Intraday Digest

```bash
make digest_now
```

**Output**:
```
###BEGIN-AXFL-DIGEST###
{"ok":true,"date":"20251020","png":"reports/intraday_pnl_20251020.png","totals":{"trades":5,"r":2.35,"pnl":587.50}}
###END-AXFL-DIGEST###
```

**Features**:
- Last 6 hours of trades (configurable)
- PNG chart of cumulative P&L
- Auto-sends to Discord if `DISCORD_WEBHOOK_URL` env var set
- Lightweight (no CSV/MD, just chart)

---

## Configuration

### Environment Variables

```bash
# OANDA Broker
export OANDA_API_KEY="your-practice-api-key"
export OANDA_ACCOUNT_ID="101-xxx-xxxxxxxx-xxx"
export OANDA_ENV="practice"  # or "live"

# Discord Notifications
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
```

### Safety Settings (axfl/reconcile/engine.py)

```python
ReconcileEngine(broker, safety={
    'flatten_on_conflict': True,  # Auto-close orphans
    'max_retries': 3              # Retry limit
})
```

---

## LIVE-PORT JSON Extensions

### New Fields

```json
{
  "journal": {
    "enabled": true,
    "mapped": 3,      // Trades linked to broker
    "unmapped": 0     // Trades pending link
  }
}
```

**Interpretation**:
- `enabled=true`: Journal active, broker mirroring on
- `mapped=N`: N trades successfully mirrored
- `unmapped=0`: No pending links (healthy)
- `unmapped>0`: Review reconciliation, check errors

---

## Testing Checklist

### Pre-Go-Live

- [ ] Environment variables set (OANDA_API_KEY, OANDA_ACCOUNT_ID)
- [ ] `make recon` passes with no errors
- [ ] Journal database created: `data/journal.db`
- [ ] Test order placement: `make broker_test`
- [ ] Verify idempotency: place same order twice, check no duplicate

### During Trading

- [ ] Monitor `unmapped_trades` in LIVE-PORT JSON
- [ ] Check `logs/broker_oanda_*.jsonl` for errors
- [ ] Run `make digest_now` periodically
- [ ] Verify Discord notifications received

### Post-Trading

- [ ] Run `make recon` to verify clean state
- [ ] Review `data/journal.db` events table
- [ ] Generate daily digest: `make digest`
- [ ] Archive logs and reports

---

## Troubleshooting

### Issue: `unmapped_trades` increasing

**Cause**: Broker orders failing but AXFL trades succeeding

**Fix**:
1. Check broker logs: `logs/broker_oanda_*.jsonl`
2. Run `make recon` to attempt linking
3. Review `events` table: `SELECT * FROM events WHERE kind='order_error'`

### Issue: Orphaned broker positions

**Cause**: Manual trades or journal data loss

**Fix**:
1. Run `make recon` (will flatten if `flatten_on_conflict=True`)
2. Review flattened positions in `events` table
3. Update journal if positions were intentional

### Issue: Reconciliation fails

**Cause**: Broker API unavailable or auth failure

**Fix**:
1. Test connection: `make broker_test`
2. Verify env vars: `echo $OANDA_API_KEY`
3. Check broker status (OANDA maintenance)
4. Review error in CLI output

### Issue: Digest finds no trades

**Cause**: Log file missing or empty

**Fix**:
1. Check `logs/portfolio_live_YYYYMMDD.jsonl` exists
2. Verify trades recorded (non-zero file size)
3. Run with correct date: `make digest`

---

## Best Practices

### 1. Daily Routine
```bash
# Morning: Pre-flight check
make recon

# During trading: Monitor status
tail -f logs/portfolio_live_$(date +%Y%m%d).jsonl | jq '{journal, positions}'

# Evening: Generate digest
make digest
```

### 2. Error Handling
- Always check `journal.unmapped` in LIVE-PORT
- Review `events` table daily: `SELECT * FROM events WHERE level='ERROR' ORDER BY id DESC LIMIT 10`
- Keep broker logs for 30 days

### 3. Backup
```bash
# Backup journal database
cp data/journal.db backups/journal_$(date +%Y%m%d).db

# Backup logs
tar -czf backups/logs_$(date +%Y%m%d).tar.gz logs/
```

### 4. Monitoring Alerts
- Set up Discord webhook for critical events
- Monitor `unmapped_trades > 3` (trigger review)
- Alert on `reconcile` errors

---

## API Reference

### Journal Functions (axfl/journal/store.py)

```python
# Initialize database
init_db()

# Record broker order
upsert_broker_order(order_id, client_tag, symbol, side, units, ...)

# Record AXFL trade
upsert_axfl_trade(axfl_id, symbol, strategy, side, entry, ...)

# Link trade to order
link(axfl_id, order_id)

# Log diagnostic event
log_event(level, kind, payload)

# Query open positions
positions = open_positions()  # Returns {'broker_orders', 'axfl_trades', 'mappings'}

# Query pending mappings
pending = pending_mappings()  # Returns list of unmapped AXFL trades

# Query recent events
events = last_n_events(n=50)
```

### Reconciliation (axfl/reconcile/engine.py)

```python
from axfl.reconcile.engine import ReconcileEngine
from axfl.brokers.oanda import OandaPractice

broker = OandaPractice()
reconcile_engine = ReconcileEngine(broker, safety={'flatten_on_conflict': True})

# Startup sync
summary = reconcile_engine.on_start()

# Link pending trades
linked_count = reconcile_engine.link_pending()

# Full reconciliation
result = reconcile_engine.reconcile()
# Returns: {'ok', 'broker_positions', 'journal_positions', 'flattened', 'linked', 'errors'}
```

### Intraday Digest (axfl/monitor/digest.py)

```python
from axfl.monitor.digest import intraday_digest

result = intraday_digest(out_dir='reports', since_hours=6)
# Returns: {'ok', 'date', 'png', 'totals': {'trades', 'r', 'pnl'}}
```

---

## Future Enhancements

### Planned

1. **Multi-Broker Support**: Add Alpaca, Interactive Brokers
2. **Automated Recovery**: Retry failed orders with exponential backoff
3. **Position Reconciliation**: Verify units match between AXFL and broker
4. **Real-Time Alerts**: Slack/Telegram integration
5. **Web Dashboard**: Real-time monitoring UI

### Under Consideration

- **Partial Fills**: Handle broker partial fills vs AXFL all-or-nothing
- **Slippage Tracking**: Compare AXFL entry vs actual broker fill
- **Commission Tracking**: Record actual broker commissions
- **Audit Log**: Immutable append-only event log

---

## Example Workflow

### Full Day Trading Session

```bash
# 1. Morning: Pre-flight check
make recon
# ✓ Reconciliation complete: broker_positions=0, journal_positions=0, flattened=0

# 2. Start live trading (WebSocket mode)
make live_oanda_ws
# ... streaming data, executing trades ...

# 3. Monitor (separate terminal)
watch -n 60 'make digest_now'

# 4. Lunchtime: Quick check
make recon
# ✓ All positions mapped

# 5. Evening: Generate full digest
make digest
# ✓ Digest complete: pnl_20251020.{csv,md,png}

# 6. Review logs
sqlite3 data/journal.db "SELECT * FROM events WHERE kind='order_error';"
# (empty = no errors)

# 7. Backup
cp data/journal.db backups/journal_$(date +%Y%m%d).db
```

---

## Changelog

### v2.0 (October 20, 2025)

**Added**:
- SQLite journal persistence (`axfl/journal/store.py`)
- OANDA idempotent tagging (`axfl/brokers/oanda.py`)
- Reconciliation engine (`axfl/reconcile/engine.py`)
- Portfolio journal hooks (`axfl/portfolio/engine.py`)
- Intraday digest (`axfl/monitor/digest.py`)
- CLI commands: `live-oanda`, `reconcile`, `digest-now`
- Makefile targets: `live_oanda_ws`, `recon`, `digest_now`

**Changes**:
- `LIVE-PORT` JSON now includes `journal` field
- Startup reconciliation runs automatically before trading
- Client tags stored in position metadata

**Guarantees**:
- Idempotent order placement (no duplicates on retry)
- Startup sync (broker vs journal drift detection)
- Safe recovery (orphan flattening, pending linking)

---

**Updated**: October 20, 2025  
**Status**: ✅ Production Ready
