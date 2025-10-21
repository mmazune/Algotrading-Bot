# Risk-Parity & Drawdown Lock - Technical Documentation

**Version**: 1.0  
**Date**: October 20, 2025  
**Status**: Production Ready ✅

---

## Overview

AXFL now features advanced portfolio risk management with three major enhancements:

1. **Risk-Parity Allocation** - Inverse-volatility weighting across symbols
2. **Trailing Drawdown Lock** - Automatic halt with cooloff on equity drawdown
3. **Daily PnL Digest** - Comprehensive reporting with charts and Discord integration

---

## Part A: Risk-Parity Allocation

### Concept

**Risk-parity** allocates capital inversely proportional to volatility:
- High-volatility symbols → Lower allocation
- Low-volatility symbols → Higher allocation
- Result: Equal risk contribution from each symbol

### Formula

```
vol_i = ATR_14(symbol_i) in pips
w_i = 1 / vol_i  (inverse volatility)
w_i_clamped = clamp(w_i, floor, cap)
w_i_final = w_i_clamped / sum(w_clamped)  (normalize to sum=1)
```

### Configuration

**File**: `axfl/config/sessions.yaml`

```yaml
portfolio:
  symbols: ["EURUSD", "GBPUSD", "XAUUSD"]
  risk_parity:
    enabled: true
    lookback_d: 20      # Days for volatility estimation
    floor: 0.15         # Minimum 15% per symbol
    cap: 0.60           # Maximum 60% per symbol
```

### Implementation

**File**: `axfl/risk/vol.py`

#### Key Functions

**`compute_atr(df, period=14)`**
- Computes Average True Range from OHLC data
- Uses exponential moving average of True Range
- Standard period: 14 bars

**`realized_vol_pips(df_5m, lookback_d, pip, session_start_hour=7, session_end_hour=16)`**
- Filters data to trading session (07:00-16:00 UTC by default)
- Computes mean ATR over lookback period
- Converts to pips for cross-symbol comparison

**`inv_vol_weights(symbols, data_map, lookback_d, pip_map, floor=0.15, cap=0.60)`**
- Returns `(weights, vols)` tuple
- Weights sum to 1.0
- Vols in pips for diagnostics

### Portfolio Integration

**File**: `axfl/portfolio/engine.py`

#### Startup (after warmup)

```python
if self.risk_parity_enabled:
    pip_map = {sym: pip_size(sym) for sym in self.symbols}
    self.weights, self.symbol_vols = inv_vol_weights(
        symbols=self.symbols,
        data_map=warmup_data,
        lookback_d=self.risk_parity_lookback_d,
        pip_map=pip_map,
        floor=self.risk_parity_floor,
        cap=self.risk_parity_cap
    )
```

#### Position Sizing

```python
# In _open_position_with_mirror()
symbol_weight = self.weights.get(symbol, 1.0 / len(self.symbols))
scaled_risk_fraction = self.budgets['per_trade_fraction'] * symbol_weight

units = units_from_risk(
    symbol=symbol,
    entry=entry,
    sl=sl,
    equity_usd=self.equity_usd,
    risk_fraction=scaled_risk_fraction
)
```

#### LIVE-PORT JSON

```json
{
  "weights": {
    "EURUSD": 0.3500,
    "GBPUSD": 0.4000,
    "XAUUSD": 0.2500
  },
  "volatilities_pips": {
    "EURUSD": 12.50,
    "GBPUSD": 10.80,
    "XAUUSD": 18.20
  }
}
```

### CLI Command

```bash
make risk_parity
# Or:
python -m axfl.cli risk-parity --cfg axfl/config/sessions.yaml --lookback 20
```

**Output**:
```
=== AXFL Risk-Parity Allocation ===

Symbols: EURUSD, GBPUSD, XAUUSD
Lookback: 20 days
Floor: 15%, Cap: 60%

Loading historical data...
  EURUSD... ✓ (5760 bars)
  GBPUSD... ✓ (5760 bars)
  XAUUSD... ✓ (5760 bars)

Computing risk-parity weights...

Symbol Volatilities (ATR in pips):
  EURUSD :  12.50 pips
  GBPUSD :  10.80 pips
  XAUUSD :  18.20 pips

Risk-Parity Weights:
  EURUSD :  35.00%
  GBPUSD :  40.00%
  XAUUSD :  25.00%

Sum of weights: 1.0000

Per-Symbol Risk Allocation (0.5% base risk):
  EURUSD : $ 175.00 (0.175%)
  GBPUSD : $ 200.00 (0.200%)
  XAUUSD : $ 125.00 (0.125%)

###BEGIN-AXFL-RISK-PARITY###
{...json...}
###END-AXFL-RISK-PARITY###
```

### Example Scenario

**Setup**:
- Portfolio: $100k equity
- Symbols: EURUSD, GBPUSD, XAUUSD
- Base per-trade risk: 0.5% ($500)
- Floor: 15%, Cap: 60%

**Measured Volatilities** (20-day ATR):
- EURUSD: 12.5 pips → w_raw = 1/12.5 = 0.080
- GBPUSD: 10.0 pips → w_raw = 1/10.0 = 0.100
- XAUUSD: 20.0 pips → w_raw = 1/20.0 = 0.050

**After Clamping & Normalization**:
- EURUSD: 35% weight → Risk 0.175% ($175)
- GBPUSD: 40% weight → Risk 0.200% ($200)
- XAUUSD: 25% weight → Risk 0.125% ($125)

**Result**: Gold (highest vol) gets lowest allocation, GBP (lowest vol) gets highest allocation.

---

## Part B: Trailing Drawdown Lock

### Concept

**Drawdown lock** automatically halts trading when equity falls below a threshold from peak, with a cooloff period before resuming.

### Formula

```
dd_pct = (peak_equity - current_equity) / peak_equity * 100
if dd_pct >= threshold:
    halt trading
    start cooloff timer (e.g., 120 minutes)
```

### Configuration

**File**: `axfl/config/sessions.yaml`

```yaml
portfolio:
  dd_lock:
    enabled: true
    trailing_pct: 5.0      # Halt if DD from peak >= 5%
    cooloff_min: 120       # Wait 120min before re-enabling
```

### Implementation

**File**: `axfl/portfolio/engine.py`

#### State Variables

```python
self.peak_equity = self.equity_usd  # Track all-time high
self.dd_lock_active = False
self.dd_lock_since = None
self.dd_lock_cooloff_until = None
self.current_dd_pct = 0.0
```

#### On Trade Close

```python
# In _close_position_with_mirror()
if self.equity_usd > self.peak_equity:
    self.peak_equity = self.equity_usd

if self.dd_lock_enabled:
    self.current_dd_pct = ((self.peak_equity - self.equity_usd) / self.peak_equity) * 100.0
    
    if self.current_dd_pct >= self.dd_lock_trailing_pct and not self.dd_lock_active:
        self.dd_lock_active = True
        self.dd_lock_since = pd.Timestamp.now(tz='UTC')
        self.dd_lock_cooloff_until = self.dd_lock_since + pd.Timedelta(minutes=self.dd_lock_cooloff_min)
        self.halted = True
        
        print(f"\n⚠️  DRAWDOWN LOCK TRIGGERED")
        print(f"  Peak equity: ${self.peak_equity:,.2f}")
        print(f"  Current equity: ${self.equity_usd:,.2f}")
        print(f"  Drawdown: {self.current_dd_pct:.2f}%")
        print(f"  Cooloff until: {self.dd_lock_cooloff_until}")
        
        alerts.send_event("DD_LOCK", {...})
```

#### On Each Bar

```python
# In _process_bar(), at start
if self.dd_lock_active and self.dd_lock_cooloff_until:
    if ts_utc >= self.dd_lock_cooloff_until:
        # Recompute DD
        self.current_dd_pct = ((self.peak_equity - self.equity_usd) / self.peak_equity) * 100.0
        
        if self.current_dd_pct < self.dd_lock_trailing_pct:
            # DD recovered, clear lock
            self.dd_lock_active = False
            self.halted = False
            self.dd_lock_since = None
            self.dd_lock_cooloff_until = None
            
            print(f"\n✓ DD LOCK CLEARED")
            alerts.send_event("DD_LOCK_CLEARED", {...})
        else:
            # Still elevated, extend cooloff
            self.dd_lock_cooloff_until = ts_utc + pd.Timedelta(minutes=self.dd_lock_cooloff_min)
```

#### LIVE-PORT JSON

```json
{
  "dd_lock": {
    "enabled": true,
    "active": false,
    "dd_pct": 2.15,
    "peak_equity": 102500.00,
    "threshold_pct": 5.0,
    "cooloff_min": 120,
    "since": null,
    "cooloff_until": null
  }
}
```

### Example Scenario

**Setup**:
- Starting equity: $100,000
- Threshold: 5% DD from peak
- Cooloff: 120 minutes

**Timeline**:
1. **10:00** - Start trading, equity = $100,000 (peak)
2. **11:30** - Win +$2,500, equity = $102,500 (new peak)
3. **12:00** - Loss -$1,000, equity = $101,500 (DD = 0.98%)
4. **12:30** - Loss -$2,000, equity = $99,500 (DD = 2.93%)
5. **13:00** - Loss -$3,000, equity = $96,500 (DD = 5.85% ≥ 5.0%)
   - **🚨 DRAWDOWN LOCK TRIGGERED**
   - Halted = True
   - Cooloff until 15:00 (120 min from 13:00)
6. **13:30** - No new trades (halted)
7. **14:00** - No new trades (halted)
8. **15:00** - Cooloff expired
   - Check DD: still 5.85% ≥ 5.0%
   - Extend cooloff to 17:00
9. **17:00** - Cooloff expired again
   - Suppose equity now $97,600 from existing position closes
   - DD = 4.78% < 5.0%
   - **✓ DD LOCK CLEARED**
   - Resume trading

---

## Part C: Daily PnL Digest

### Concept

Automated daily report generation with:
- **CSV**: Trade-by-trade details
- **Markdown**: Summary with breakdowns
- **PNG Chart**: Cumulative P&L visualization
- **Discord**: Optional webhook notification

### Implementation

**File**: `axfl/monitor/digest.py`

#### Key Functions

**`load_trades_from_jsonl(log_file)`**
- Parses portfolio JSONL logs
- Extracts all trades with context (symbol, strategy)
- Deduplicates by (entry_time, symbol, strategy)

**`compute_daily_stats(trades, target_date)`**
- Filters trades to target date
- Computes win rate, total R, max/min, etc.
- Breaks down by symbol and strategy

**`generate_csv_report(stats, output_path)`**
- Writes CSV with columns: date, symbol, strategy, side, entry, exit, r, pnl, reason

**`generate_markdown_report(stats, output_path)`**
- Creates formatted Markdown summary
- Includes tables for by-symbol and by-strategy breakdowns
- Full trade log table

**`generate_pnl_chart(stats, output_path)`**
- Plots cumulative R over trade sequence
- Green/red fill based on final result
- Summary annotation box

**`send_discord_webhook(stats, webhook_url, chart_path)`**
- Sends embed with key stats
- Attaches PNG chart
- Color-coded (green=profit, red=loss)

### CLI Command

```bash
make digest
# Or:
python -m axfl.cli digest --date 20251020
python -m axfl.cli digest --date 20251020 --discord-webhook https://discord.com/api/webhooks/...
```

**Output**:
```
=== Generating Daily Digest for 20251020 ===

Loading trades from: logs/portfolio_live_20251020.jsonl
  Found 47 unique trades

  ✓ CSV report: reports/pnl_20251020.csv
  ✓ Markdown report: reports/pnl_20251020.md
  ✓ Chart: reports/pnl_20251020.png
  ✓ Discord webhook sent successfully

✓ Digest complete for 20251020
  Total R: +3.45R
  Total PnL: $1,725.00
  Reports: reports/pnl_20251020.*
```

### CSV Format

```csv
date,symbol,strategy,side,entry,exit,r,pnl,reason
2025-10-20,EURUSD,lsg,long,1.0950,1.0975,2.5,625.0,TP
2025-10-20,GBPUSD,orb,short,1.2700,1.2680,2.0,500.0,TP
2025-10-20,XAUUSD,arls,long,2650.0,2645.0,-1.0,-250.0,SL
...
```

### Markdown Example

```markdown
# Daily Trading Report - 2025-10-20

## Summary

- **Total Trades**: 15
- **Winners**: 9 (60.0%)
- **Losers**: 6
- **Total R**: +3.45R
- **Total PnL**: $+1,725.00
- **Avg R/Trade**: +0.23R
- **Best Trade**: +2.50R
- **Worst Trade**: -1.00R

## By Symbol

| Symbol | Trades | Total R | PnL |
|--------|--------|---------|-----|
| EURUSD | 6 | +2.10R | $+1,050.00 |
| GBPUSD | 5 | +1.80R | $+900.00 |
| XAUUSD | 4 | -0.45R | $-225.00 |

## By Strategy

| Strategy | Trades | Total R | PnL |
|----------|--------|---------|-----|
| lsg | 7 | +2.50R | $+1,250.00 |
| orb | 5 | +1.20R | $+600.00 |
| arls | 3 | -0.25R | $-125.00 |
```

### Discord Webhook Setup

1. **Create Webhook** in Discord server settings → Integrations → Webhooks
2. **Copy URL**: `https://discord.com/api/webhooks/...`
3. **Use in digest**:
   ```bash
   export DISCORD_WEBHOOK="https://discord.com/api/webhooks/..."
   python -m axfl.cli digest --discord-webhook "$DISCORD_WEBHOOK"
   ```

4. **Automated Daily Report** (cron):
   ```bash
   # Add to crontab: Run daily at 18:00 UTC
   0 18 * * * cd /path/to/Algotrading-Bot && make digest --discord-webhook "$DISCORD_WEBHOOK"
   ```

---

## Configuration Reference

### Complete sessions.yaml Example

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
  status_every_s: 90
  
  risk:
    global_daily_stop_r: -5.0
    max_open_positions: 2
    per_strategy_daily_trades: 3
    per_strategy_daily_stop_r: -2.0
  
  # Risk-parity allocation
  risk_parity:
    enabled: true
    lookback_d: 20
    floor: 0.15
    cap: 0.60
  
  # Drawdown lock
  dd_lock:
    enabled: true
    trailing_pct: 5.0
    cooloff_min: 120
  
  # News guard (existing)
  news_guard:
    enabled: true
    csv_path: "news_events.csv"
    pad_before_m: 30
    pad_after_m: 30
```

---

## CLI Commands Summary

### Risk-Parity Weights

```bash
make risk_parity
python -m axfl.cli risk-parity --cfg axfl/config/sessions.yaml --lookback 20
```

### Daily Digest

```bash
make digest
python -m axfl.cli digest --date 20251020
python -m axfl.cli digest --date 20251020 --discord-webhook "https://..."
```

### Existing Commands

```bash
make risk          # Portfolio risk budgets
make news          # Upcoming news events
make broker_test   # OANDA connection test
```

---

## Best Practices

### Risk-Parity

✅ **Use 20+ days** for stable volatility estimates  
✅ **Set reasonable floor/cap** (15%-60% works well for 3 symbols)  
✅ **Recompute periodically** (e.g., daily or weekly)  
✅ **Monitor weight shifts** in LIVE-PORT JSON  
✅ **Backtest with historical weights** to validate allocation  

### Drawdown Lock

✅ **Start conservative** (5% threshold is reasonable)  
✅ **Set adequate cooloff** (120 min = 2 hours allows market conditions to change)  
✅ **Monitor peak equity** to understand lock triggers  
✅ **Alert on DD_LOCK events** for manual review  
✅ **Test in replay mode** before live trading  

### Daily Digest

✅ **Automate with cron** for consistent reporting  
✅ **Use Discord webhooks** for instant notifications  
✅ **Review Markdown reports** for detailed analysis  
✅ **Archive PNG charts** for visual history  
✅ **Compare by-symbol/strategy** to identify strengths  

---

## Troubleshooting

### Issue: Risk-parity weights not updating
**Cause**: Disabled in config or warmup data insufficient  
**Fix**: Ensure `risk_parity.enabled: true` and `warmup_days >= 3`

### Issue: Drawdown lock triggers too often
**Cause**: Threshold too tight or high volatility  
**Fix**: Increase `trailing_pct` from 5% to 7-10%

### Issue: Cooloff never clears
**Cause**: Equity continues declining during cooloff  
**Fix**: Close losing positions manually or increase cooloff to allow recovery

### Issue: Digest finds no trades
**Cause**: Wrong date or log file path  
**Fix**: Check logs directory and date format (YYYYMMDD)

### Issue: Discord webhook fails
**Cause**: Invalid URL or network issue  
**Fix**: Verify webhook URL in Discord settings, check internet connection

---

## Testing

### Test Risk-Parity

```bash
# Check weights computation
make risk_parity

# Verify in replay mode
make demo_replay
# Watch LIVE-PORT JSON for "weights" field
```

### Test Drawdown Lock

```python
# In demo_replay or live_port_replay
# Manually edit sessions.yaml:
dd_lock:
  enabled: true
  trailing_pct: 2.0  # Very tight for testing
  cooloff_min: 5     # Short cooloff for faster test

# Run and watch for DD_LOCK trigger
make demo_replay
```

### Test Digest

```bash
# Generate digest for recent date
python -m axfl.cli digest --date 20251020

# Check output files
ls -lh reports/pnl_20251020.*

# View Markdown report
cat reports/pnl_20251020.md
```

---

## Integration Example

**Full workflow with all features enabled**:

1. **Morning** (08:00 UTC):
   ```bash
   # Check risk-parity weights
   make risk_parity
   
   # Check upcoming news events
   make news
   
   # Start London session trading
   make daily_runner
   ```

2. **During Trading**:
   - Portfolio monitors DD lock automatically
   - Risk-parity weights scale position sizes
   - News guard blocks entries during events

3. **Evening** (18:00 UTC):
   ```bash
   # Generate daily digest
   make digest
   # Sends report to Discord automatically
   ```

4. **Review**:
   - Check `reports/pnl_YYYYMMDD.md` for detailed analysis
   - Review `logs/portfolio_live_YYYYMMDD.jsonl` for LIVE-PORT status
   - Monitor Discord for digest notification

---

## Future Enhancements

### Risk-Parity

- **Correlation adjustment**: Account for symbol correlations
- **Dynamic rebalancing**: Update weights intraday
- **Risk-parity across strategies**: Weight strategies by Sharpe ratio

### Drawdown Lock

- **Tiered thresholds**: Multiple DD levels with escalating cooloffs
- **Recovery mode**: Reduced position sizing after lock clears
- **Volatility-adjusted thresholds**: Tighter lock during high-vol periods

### Daily Digest

- **Multi-day summaries**: Weekly/monthly reports
- **Performance attribution**: Decompose returns by symbol/strategy/time
- **Slack integration**: Alternative to Discord
- **Email reports**: SMTP support for traditional notifications

---

**Version**: 1.0  
**Status**: Production Ready ✅  
**Last Updated**: October 20, 2025
