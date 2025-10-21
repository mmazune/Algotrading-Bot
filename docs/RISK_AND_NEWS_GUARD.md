# Portfolio Risk & News Guard - Technical Documentation

**Version**: 1.0  
**Date**: October 20, 2025  
**Status**: Production Ready ✅

---

## Overview

AXFL now features comprehensive portfolio risk management and news event filtering to enhance capital preservation and avoid volatile market conditions.

### Three Major Features

1. **Portfolio Risk & Capital v1** - Dynamic position sizing with equity tracking
2. **News/Event Guard** - Automated blocking of entries around high-impact announcements
3. **OANDA Practice Mirror Self-Test** - Safe broker integration verification

---

## Part A: Portfolio Risk & Capital v1

### Architecture

```
Risk Management Stack
├─ Position Sizing (units_from_risk)
│   ├─ ATR-aware stop distance
│   ├─ Symbol pip values
│   └─ Dynamic equity allocation
│
├─ Capital Allocator (compute_budgets)
│   ├─ Per-strategy budgets
│   ├─ Daily risk limits
│   └─ Volatility targeting (future)
│
└─ Portfolio Engine Integration
    ├─ Real-time equity tracking
    ├─ Budget enforcement
    └─ LIVE-PORT JSON reporting
```

### Position Sizing Module

**File**: `axfl/risk/position_sizing.py`

#### `units_from_risk()`

Calculates position size based on stop distance and risk parameters.

**Formula**:
```python
risk_amount = equity_usd * risk_fraction
sl_distance_pips = abs(entry - sl) / pip_size(symbol)
per_unit_loss = sl_distance_pips * pip_value(symbol) / 100000
units = floor(risk_amount / per_unit_loss)
```

**Example**:
```python
from axfl.risk import units_from_risk

# Risk 0.5% of $100k on EURUSD with 20 pip stop
units = units_from_risk(
    symbol="EURUSD",
    entry=1.1000,
    sl=1.0980,  # 20 pips
    equity_usd=100000,
    risk_fraction=0.005  # 0.5%
)
# Result: 2500 units
# Calculation: $500 / (20 pips * $10/pip / 100k) = 2500
```

#### `pip_value()`

Returns pip value in USD per standard lot (100k units).

**Constants**:
- **EURUSD, GBPUSD**: $10 per pip per 100k units
- **XAUUSD** (Gold): $1000 per pip per 100k units ($1 per $0.1 move per 100 units)
- **Default**: $10 (for most USD pairs)

**Example**:
```python
from axfl.risk import pip_value

pip_value("EURUSD")   # 10.0
pip_value("XAUUSD")   # 1000.0
```

### Capital Allocator Module

**File**: `axfl/risk/allocator.py`

#### `PortfolioBudgets` Dataclass

```python
@dataclass
class PortfolioBudgets:
    equity_usd: float = 100000.0
    daily_risk_fraction: float = 0.02          # 2% total daily risk
    per_strategy_fraction: float = 0.34        # ~33% per strategy
    per_trade_fraction: float = 0.005          # 0.5% per trade
    volatility_target_annual: float = 0.10     # 10% vol target
```

#### `compute_budgets()`

Allocates capital across strategies with risk budgets.

**Returns**:
```json
{
  "equity_usd": 100000.0,
  "daily_r_total": 2000.0,
  "per_strategy": {
    "lsg": 666.67,
    "orb": 666.67,
    "arls": 666.67
  },
  "per_trade_r": 500.0,
  "daily_risk_fraction": 0.02,
  "per_trade_fraction": 0.005,
  "notes": "Simple equal split; risk-parity hooks ready"
}
```

**Example**:
```python
from axfl.risk import compute_budgets

budgets = compute_budgets(
    symbols=["EURUSD", "GBPUSD", "XAUUSD"],
    strategies=["lsg", "orb", "arls"],
    spreads={"EURUSD": 0.6, "GBPUSD": 0.9, "XAUUSD": 2.5},
    equity_usd=100000.0,
    daily_risk_fraction=0.02,
    per_trade_fraction=0.005
)
```

### Portfolio Engine Integration

**File**: `axfl/portfolio/engine.py`

#### Initialization

```python
# Computed on startup
self.budgets = compute_budgets(
    symbols=self.symbols,
    strategies=[s['name'] for s in self.strategies_cfg],
    spreads=self.spreads,
    equity_usd=100000.0,
    daily_risk_fraction=0.02,
    per_trade_fraction=0.005
)

self.equity_usd = 100000.0  # Starting equity
self.daily_r_used_by_strategy = {s: 0.0 for s in strategies}
```

#### Position Opening (Dynamic Sizing)

```python
# In _open_position_with_mirror()
units = units_from_risk(
    symbol=symbol,
    entry=entry,
    sl=sl,
    equity_usd=self.equity_usd,
    risk_fraction=self.budgets['per_trade_fraction']
)
```

#### Position Closing (Equity Update)

```python
# In _close_position_with_mirror()
if engine.trades:
    last_trade = engine.trades[-1]
    realized_pnl = last_trade.get('pnl', 0.0)
    realized_r = last_trade.get('r', 0.0)
    
    # Update equity
    self.equity_usd += realized_pnl
    
    # Track daily R by strategy
    self.daily_r_used_by_strategy[strategy_name] += realized_r
```

#### Budget Enforcement

```python
# In _process_bar(), before opening new positions
daily_r_for_strategy = self.daily_r_used_by_strategy.get(strategy_name, 0.0)
strategy_budget = self.budgets['per_strategy'].get(strategy_name, float('inf'))

budget_blocked = abs(daily_r_for_strategy) >= abs(strategy_budget)

can_trade = (
    in_window and
    not self.halted and
    not news_blocked and
    not budget_blocked and  # NEW: Budget check
    engine.risk_manager.can_open(today) and
    open_positions < self.max_open_positions
)
```

#### LIVE-PORT JSON Output

```json
{
  "budgets": {
    "equity_usd": 101250.50,
    "daily_r_total": 2000.0,
    "per_strategy": {
      "lsg": 666.67,
      "orb": 666.67,
      "arls": 666.67
    },
    "per_trade_r": 500.0,
    "daily_r_used": {
      "lsg": -1.2,
      "orb": 0.8,
      "arls": 0.0
    }
  }
}
```

---

## Part B: News/Event Guard

### Architecture

```
News Guard System
├─ Event Calendar (CSV)
│   └─ High-impact announcements
│
├─ Window Calculator
│   ├─ Event time + padding
│   └─ Symbol-currency mapping
│
└─ Portfolio Integration
    ├─ Real-time window checks
    ├─ Entry blocking
    └─ Position management allowed
```

### News Calendar Module

**File**: `axfl/news/calendar.py`

#### CSV Format

**File**: `samples/news_events.sample.csv`

```csv
date,time_utc,currencies,impact,title
2025-10-20,12:30,USD,high,Core Retail Sales (MoM)
2025-10-20,14:00,USD,high,Existing Home Sales
2025-10-21,07:00,GBP,high,CPI (YoY)
```

**Required Columns**:
- `date`: YYYY-MM-DD
- `time_utc`: HH:MM (24-hour format)
- `currencies`: Comma-separated currency codes (USD,EUR,GBP)
- `impact`: high, medium, low
- `title`: Event name

#### `load_events_csv()`

```python
from axfl.news import load_events_csv

df = load_events_csv('samples/news_events.sample.csv')
# Returns DataFrame with datetime index, currencies list, impact, title
```

#### `upcoming_windows()`

Generates risk windows with padding around events.

**Parameters**:
- `pad_before_m`: Minutes before event (default 30)
- `pad_after_m`: Minutes after event (default 30)
- `lookahead_hours`: Hours to scan ahead (default 24)

**Example**:
```python
from axfl.news import upcoming_windows
import pandas as pd

now = pd.Timestamp.now(tz='UTC')
windows = upcoming_windows(df, now, pad_before_m=30, pad_after_m=30)

# Returns:
[
  {
    "start": "2025-10-20T12:00:00+00:00",
    "end": "2025-10-20T13:00:00+00:00",
    "event_time": "2025-10-20T12:30:00+00:00",
    "currencies": ["USD"],
    "impact": "high",
    "title": "Core Retail Sales"
  }
]
```

#### `affects_symbol()`

Maps symbols to currencies and checks overlap.

**Symbol-Currency Mapping**:
- `EURUSD` → EUR, USD
- `GBPUSD` → GBP, USD
- `XAUUSD` → USD (gold priced in USD)
- `USDJPY` → USD, JPY

**Example**:
```python
from axfl.news import affects_symbol

affects_symbol("EURUSD", ["USD"])     # True
affects_symbol("EURUSD", ["GBP"])     # False
affects_symbol("XAUUSD", ["USD"])     # True (gold in USD)
```

### Portfolio Engine Integration

#### Configuration

**File**: `axfl/config/sessions.yaml`

```yaml
portfolio:
  symbols: ["EURUSD", "GBPUSD", "XAUUSD"]
  news_guard:
    enabled: true
    csv_path: "news_events.csv"  # User must create/copy
    pad_before_m: 30
    pad_after_m: 30
```

#### Initialization

```python
# In PortfolioEngine.__init__()
news_guard_cfg = schedule_cfg.get('news_guard', {})
self.news_guard_enabled = news_guard_cfg.get('enabled', False)
self.news_guard_csv_path = news_guard_cfg.get('csv_path', '')
self.news_guard_pad_before_m = news_guard_cfg.get('pad_before_m', 30)
self.news_guard_pad_after_m = news_guard_cfg.get('pad_after_m', 30)
self.news_blocked_entries = 0
self.news_active_windows = []

if self.news_guard_enabled:
    self.news_events_df = load_events_csv(self.news_guard_csv_path)
```

#### Entry Blocking

```python
# In _process_bar(), before generating signals
if self.news_guard_enabled and self.news_events_df is not None:
    self.news_active_windows = upcoming_windows(
        self.news_events_df,
        ts_utc,
        pad_before_m=self.news_guard_pad_before_m,
        pad_after_m=self.news_guard_pad_after_m,
        lookahea_hours=4
    )

news_blocked = False
if self.news_guard_enabled and self.news_active_windows:
    news_blocked = is_in_event_window(symbol, ts_utc, self.news_active_windows)
    if news_blocked:
        self.news_blocked_entries += 1

can_trade = (
    in_window and
    not self.halted and
    not news_blocked and  # NEW: News guard check
    not budget_blocked and
    engine.risk_manager.can_open(today) and
    open_positions < self.max_open_positions
)
```

**Behavior**:
- ✅ **Existing positions**: Can be managed (SL tightening, TP adjustments)
- ❌ **New entries**: Blocked during event windows
- ✅ **Position closes**: Always allowed (SL/TP/Time exits)

#### LIVE-PORT JSON Output

```json
{
  "news_guard": {
    "enabled": true,
    "blocked_entries": 3,
    "active_windows": 2
  }
}
```

---

## Part C: OANDA Practice Mirror Self-Test

### CLI Command

**File**: `axfl/cli.py`

#### `broker-test` Command

Safe, idempotent testing of OANDA broker connection.

**Usage**:
```bash
# Dry run (no actual order)
make broker_test
python -m axfl.cli broker-test --mirror oanda --symbol EURUSD --risk_perc 0.001

# With actual test order placement
python -m axfl.cli broker-test --mirror oanda --symbol EURUSD --risk_perc 0.001 --place
```

**Parameters**:
- `--mirror`: Broker name (only "oanda" supported)
- `--symbol`: Symbol for test calculation (EURUSD, GBPUSD, XAUUSD)
- `--risk_perc`: Risk percentage (default 0.1% = 0.001)
- `--place`: Flag to actually place order (default: dry run)

### Environment Variables

```bash
export OANDA_API_KEY="your-practice-or-live-token"
export OANDA_ACCOUNT_ID="101-123-456-789"
export OANDA_ENV="practice"  # or "live"
```

### Test Flow

1. **Check Environment**: Validate OANDA_API_KEY and OANDA_ACCOUNT_ID
2. **Authenticate**: GET account info to verify credentials
3. **Calculate Size**: Use `units_from_risk()` with test parameters
4. **Dry Run** (default): Display calculation, no order
5. **Place Order** (if `--place`): 
   - Place 1/10th of calculated units (minimum 1)
   - Client tag: `AXFL_SELFTEST`
   - 10 pip SL, 20 pip TP (2:1 RR)
   - **Manual close required**

### JSON Output

```json
{
  "ok": true,
  "mirror": "oanda",
  "auth": true,
  "units": 2500,
  "placed": false,
  "order_id": null,
  "error": null
}
```

**Block Wrapper**:
```
###BEGIN-AXFL-BROKER###
{...json...}
###END-AXFL-BROKER###
```

### Error Handling

**Missing Environment Variables**:
```json
{
  "ok": false,
  "mirror": "oanda",
  "auth": false,
  "error": "Missing OANDA environment variables"
}
```

**Authentication Failure**:
```json
{
  "ok": false,
  "mirror": "oanda",
  "auth": false,
  "error": "Broker error: 401 Unauthorized"
}
```

**Order Placement Failure**:
```json
{
  "ok": true,
  "auth": true,
  "units": 2500,
  "placed": false,
  "order_id": null,
  "error": "Order failed: Insufficient margin"
}
```

---

## CLI Commands Reference

### `risk` - Display Risk Budgets

```bash
make risk
python -m axfl.cli risk --cfg axfl/config/sessions.yaml
```

**Output**:
```
=== AXFL Risk Budgets ===

Portfolio Equity: $100,000
Daily Risk Limit: $2,000 (2.0%)
Per-Trade Risk: $500 (0.50%)

Per-Strategy Budgets:
  lsg: $667 (0.67%)
  orb: $667 (0.67%)
  arls: $667 (0.67%)

Note: Simple equal split; risk-parity hooks ready

###BEGIN-AXFL-RISK###
{"equity_usd":100000.0,"daily_r_total":2000.0,...}
###END-AXFL-RISK###
```

### `news` - View Upcoming Events

```bash
make news
python -m axfl.cli news --csv samples/news_events.sample.csv --hours 24
```

**Output**:
```
=== AXFL News Calendar ===

Loaded 20 events from samples/news_events.sample.csv

Upcoming events (3 in next 24h):

  2025-10-20T12:30:00+00:00
    Core Retail Sales (MoM)
    Currencies: USD
    Impact: high
    Window: 2025-10-20T12:00:00+00:00 to 2025-10-20T13:00:00+00:00

###BEGIN-AXFL-NEWS###
{"csv":"samples/news_events.sample.csv","total_events":20,...}
###END-AXFL-NEWS###
```

### `broker-test` - Test OANDA Connection

```bash
make broker_test
python -m axfl.cli broker-test --mirror oanda
```

**Output**:
```
=== AXFL Broker Self-Test ===

Testing connection to OANDA practice...
✓ Authentication successful
  Account: 101-123-456-789
  Balance: $50000.00

Calculating position size for EURUSD...
  Risk: 0.100% of equity
  Calculated units: 250

Dry run mode - no order placed
Use --place flag to actually place test order

###BEGIN-AXFL-BROKER###
{"ok":true,"mirror":"oanda","auth":true,"units":250,...}
###END-AXFL-BROKER###
```

---

## Integration Examples

### Enable News Guard

**Step 1**: Copy sample events
```bash
cp samples/news_events.sample.csv news_events.csv
```

**Step 2**: Add your events
```csv
date,time_utc,currencies,impact,title
2025-10-25,12:30,USD,high,FOMC Rate Decision
2025-10-25,14:00,USD,high,FOMC Press Conference
```

**Step 3**: Enable in config
```yaml
# axfl/config/sessions.yaml
portfolio:
  news_guard:
    enabled: true
    csv_path: "news_events.csv"
    pad_before_m: 30
    pad_after_m: 30
```

**Step 4**: Run portfolio
```bash
python -m axfl.cli live-port --cfg axfl/config/sessions.yaml --mode replay
```

### Test Broker Integration

**Step 1**: Set environment
```bash
export OANDA_API_KEY="your-practice-token"
export OANDA_ACCOUNT_ID="101-123-456-789"
export OANDA_ENV="practice"
```

**Step 2**: Dry run test
```bash
make broker_test
```

**Step 3**: Live test (optional)
```bash
python -m axfl.cli broker-test --place
```

**Step 4**: Check OANDA dashboard for test position

**Step 5**: Manually close test position

### Monitor Risk Budgets

**During Live Trading**:
```bash
# Check current budgets
make risk

# View LIVE-PORT status (includes budget usage)
tail -f logs/portfolio_live_$(date +%Y%m%d).jsonl | grep -o '"budgets":{[^}]*}'
```

---

## Configuration Reference

### sessions.yaml Structure

```yaml
portfolio:
  symbols: ["EURUSD", "GBPUSD", "XAUUSD"]
  interval: "5m"
  source: "finnhub"
  venue: "OANDA"
  spreads:
    EURUSD: 0.6
    GBPUSD: 0.9
    XAUUSD: 2.5
  warmup_days: 3
  
  # Risk configuration
  risk:
    global_daily_stop_r: -5.0
    max_open_positions: 2
    per_strategy_daily_trades: 3
    per_strategy_daily_stop_r: -2.0
  
  # News guard configuration
  news_guard:
    enabled: true
    csv_path: "news_events.csv"
    pad_before_m: 30
    pad_after_m: 30

strategies:
  - name: "lsg"
    params: {...}
    windows:
      - start: "07:00"
        end: "10:00"
```

---

## Best Practices

### Risk Management

✅ **Start Conservative**: Use 0.5% per trade, 2% daily limit  
✅ **Monitor Equity**: Check equity drift in LIVE-PORT JSON  
✅ **Review Budgets**: Run `make risk` daily to verify allocation  
✅ **Track by Strategy**: Watch daily_r_used in status blocks  
✅ **Adjust Dynamically**: Reduce per_trade_fraction after drawdowns  

### News Guard

✅ **Update Calendar**: Add major events weekly  
✅ **Use Official Sources**: ECB, Fed, BOE, BoJ calendars  
✅ **Wider Padding**: Use 30+ minutes for NFP, FOMC  
✅ **Symbol-Specific**: USD events affect EURUSD, GBPUSD, XAUUSD  
✅ **Test First**: Run replay mode to verify blocking works  

### Broker Testing

✅ **Always Test First**: Run dry run before --place  
✅ **Practice Account**: Use OANDA practice for testing  
✅ **Monitor Balance**: Verify test doesn't deplete equity  
✅ **Close Immediately**: Manual close of AXFL_SELFTEST positions  
✅ **Document Results**: Save broker-test JSON for records  

---

## Troubleshooting

### Issue: Position sizes too large
**Cause**: Default equity (100k) may be higher than actual  
**Fix**: Adjust `equity_usd` in `compute_budgets()` call

### Issue: News guard not blocking
**Cause**: CSV path incorrect or events in past  
**Fix**: Check csv_path in config, verify event dates are future

### Issue: Broker test auth failure
**Cause**: Wrong API key or account ID  
**Fix**: Verify environment variables, check OANDA dashboard

### Issue: Budget always blocked
**Cause**: Strategy hit daily limit early  
**Fix**: Check daily_r_used, increase per_strategy_fraction

### Issue: No units calculated
**Cause**: Stop loss too wide or equity too low  
**Fix**: Tighten stop or increase risk_fraction temporarily

---

## Future Enhancements

### Risk Module

- **Risk Parity**: Weight strategies by inverse volatility
- **Kelly Fraction**: Optimal sizing based on edge
- **Volatility Scaling**: Adjust size with realized vol
- **Correlation Matrix**: Multi-symbol position limits
- **Monte Carlo**: Simulate equity curves

### News Guard

- **Auto Calendar**: Fetch from ForexFactory/Investing.com API
- **Smart Padding**: Dynamic padding based on event type
- **Partial Sizing**: Reduce size instead of full block
- **Symbol Exposure**: Block correlated pairs (EUR pairs together)

### Broker Integration

- **Auto-Reconciliation**: Compare OANDA vs AXFL positions
- **Slippage Tracking**: Measure execution quality
- **Commission Integration**: Include spread + commission
- **Multi-Broker**: Support for IBKR, Alpaca
- **Order Types**: Limit orders, OCO, trailing stops

---

**Version**: 1.0  
**Status**: Production Ready ✅  
**Last Updated**: October 20, 2025
