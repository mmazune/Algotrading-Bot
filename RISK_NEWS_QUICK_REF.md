# Risk & News Guard - Quick Reference

**Version**: 1.0 | **Status**: Production Ready ✅

---

## ⚡ Quick Commands

```bash
# Check risk budgets
make risk

# View upcoming news events (next 24h)
make news

# Test OANDA connection (dry run)
make broker_test

# Place micro test order (use with caution)
python -m axfl.cli broker-test --mirror oanda --place
```

---

## 🎯 Position Sizing Formula

```
units = floor(equity × risk% / (sl_pips × pip_value / 100k))
```

**Example**: $100k equity, 0.5% risk, 20 pip SL on EURUSD
- Risk: $100k × 0.005 = $500
- SL: 20 pips × $10/pip / 100k = $0.002 per unit
- Units: $500 / $0.002 = **250,000** (2.5 lots)

---

## 📅 News CSV Format

```csv
date,time_utc,currencies,impact,title
2025-10-25,12:30,USD,high,Non-Farm Payrolls
2025-10-25,14:00,USD,high,FOMC Minutes
```

**Location**: Copy `samples/news_events.sample.csv` → `news_events.csv`

---

## ⚙️ Configuration (sessions.yaml)

```yaml
portfolio:
  news_guard:
    enabled: true
    csv_path: "news_events.csv"
    pad_before_m: 30  # Block 30min before
    pad_after_m: 30   # Block 30min after
```

---

## 📊 Default Risk Budgets

| Parameter | Value | Notes |
|-----------|-------|-------|
| Equity | $100,000 | Starting capital |
| Daily Risk | 2% ($2,000) | Total portfolio |
| Per Trade | 0.5% ($500) | Each position |
| Per Strategy | 0.67% ($667) | Equal split (3 strategies) |

---

## 🛡️ Symbol Pip Values

| Symbol | Pip Value (per 100k units) |
|--------|---------------------------|
| EURUSD | $10 |
| GBPUSD | $10 |
| XAUUSD | $1,000 (gold) |

---

## 🚫 News Guard Behavior

| Action | During Event Window | Outside Window |
|--------|---------------------|----------------|
| New Entries | ❌ Blocked | ✅ Allowed |
| Position Management | ✅ Allowed | ✅ Allowed |
| Stop/TP Exits | ✅ Allowed | ✅ Allowed |

**Affected Symbols**:
- USD events → EURUSD, GBPUSD, XAUUSD
- EUR events → EURUSD
- GBP events → GBPUSD

---

## 🔍 LIVE-PORT JSON Monitoring

```bash
# Watch budgets in real-time
tail -f logs/portfolio_live_$(date +%Y%m%d).jsonl | jq '.budgets'

# Watch news guard
tail -f logs/portfolio_live_$(date +%Y%m%d).jsonl | jq '.news_guard'

# Both together
tail -f logs/portfolio_live_$(date +%Y%m%d).jsonl | jq '{budgets, news_guard}'
```

---

## 🧪 Testing Workflow

### 1. Verify Risk Calculation
```bash
make risk
# Check: equity_usd=100000, daily_r_total=2000
```

### 2. Verify News Calendar
```bash
make news
# Check: Loaded 20 events, upcoming events displayed
```

### 3. Verify Broker Auth (Dry Run)
```bash
make broker_test
# Expected: Error (no credentials) or auth success
```

### 4. Enable News Guard
```bash
cp samples/news_events.sample.csv news_events.csv
# Edit axfl/config/sessions.yaml → news_guard.enabled=true
```

### 5. Run Replay Mode
```bash
python -m axfl.cli live-port --cfg axfl/config/sessions.yaml --mode replay
# Watch for "news_blocked_entries" in status
```

---

## 🚨 Troubleshooting

### Position Sizes Too Large
```python
# In axfl/portfolio/engine.py (line ~95)
self.budgets = compute_budgets(
    equity_usd=50000.0,  # ← Reduce from 100k
    per_trade_fraction=0.003  # ← Reduce from 0.005
)
```

### News Guard Not Blocking
1. Check `news_guard.enabled: true` in sessions.yaml
2. Verify CSV path is correct
3. Ensure event dates are in future
4. Check symbol-currency mapping

### Budget Always Blocked
```bash
# Check daily usage
tail logs/portfolio_live_*.jsonl | jq '.budgets.daily_r_used'

# Increase per-strategy allocation (sessions.yaml)
daily_risk_fraction: 0.03  # 3% instead of 2%
```

---

## 📚 Full Documentation

**Comprehensive Guide**: `docs/RISK_AND_NEWS_GUARD.md`  
**Delivery Summary**: `RISK_NEWS_BROKER_V1_SUMMARY.md`

---

## 🎓 Key Files

| File | Purpose | Lines |
|------|---------|-------|
| `axfl/risk/position_sizing.py` | Dynamic sizing | ~170 |
| `axfl/risk/allocator.py` | Budget allocation | ~220 |
| `axfl/news/calendar.py` | Event detection | ~180 |
| `axfl/portfolio/engine.py` | Integration | ~150 mod |
| `axfl/cli.py` | Commands | ~260 new |
| `samples/news_events.sample.csv` | Sample data | 20 events |

---

**Updated**: October 20, 2025  
**Status**: ✅ Production Ready
