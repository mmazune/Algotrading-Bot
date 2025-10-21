# Risk-Parity, DD Lock & Digest - Quick Reference

**Version**: 1.0 | **Status**: Production Ready ✅

---

## ⚡ Quick Commands

```bash
# Check risk-parity weights
make risk_parity

# Generate daily digest
make digest

# Run portfolio with all features
make demo_replay

# Monitor live trading
tail -f logs/portfolio_live_$(date +%Y%m%d).jsonl | jq '{weights, dd_lock}'
```

---

## 🎯 Risk-Parity Formula

```
vol_i = ATR_14(symbol_i) in pips (last 20 days, session-filtered)
w_i = 1 / vol_i  (inverse volatility)
w_i_clamped = clamp(w_i, 0.15, 0.60)  (floor/cap)
w_i_final = w_i_clamped / sum(w_clamped)  (normalize to 1.0)
```

**Position Sizing**:
```python
scaled_risk = base_risk * weight[symbol]
# Example: 0.5% * 0.35 = 0.175% for EURUSD
```

---

## 🛡️ Drawdown Lock Behavior

| Equity Condition | Action |
|------------------|--------|
| DD < Threshold | ✅ Trading active |
| DD ≥ Threshold | 🚨 Halt + Start cooloff |
| Cooloff active, DD recovered | ✓ Resume trading |
| Cooloff active, DD still high | ⏳ Extend cooloff |

**Default Settings**:
- Threshold: 5% from peak
- Cooloff: 120 minutes

---

## 📊 Daily Digest Output

| File | Description |
|------|-------------|
| `pnl_YYYYMMDD.csv` | Trade-by-trade details |
| `pnl_YYYYMMDD.md` | Summary with breakdowns |
| `pnl_YYYYMMDD.png` | Cumulative P&L chart |
| Discord webhook | Instant notification with chart |

---

## ⚙️ Configuration (sessions.yaml)

```yaml
portfolio:
  symbols: ["EURUSD", "GBPUSD", "XAUUSD"]
  
  risk_parity:
    enabled: true
    lookback_d: 20
    floor: 0.15
    cap: 0.60
  
  dd_lock:
    enabled: true
    trailing_pct: 5.0
    cooloff_min: 120
```

---

## 📈 Example Scenario: Risk-Parity

**Measured Volatilities** (20-day ATR):
- EURUSD: 12.5 pips → Weight: 35%
- GBPUSD: 10.0 pips → Weight: 40%
- XAUUSD: 20.0 pips → Weight: 25%

**Position Sizing** (0.5% base risk):
- EURUSD: 0.175% ($175 on $100k)
- GBPUSD: 0.200% ($200 on $100k)
- XAUUSD: 0.125% ($125 on $100k)

---

## 🚨 Example Scenario: DD Lock

**Timeline**:
1. **Peak**: $102,500 equity
2. **Loss**: -$6,000 → Equity = $96,500
3. **DD Calc**: (102500-96500)/102500 = 5.85% ≥ 5.0%
4. **Action**: 🚨 HALT + Cooloff until +120min
5. **Recovery**: Equity rises to $97,600 (DD=4.78%)
6. **Resume**: ✓ Trading enabled

---

## 📧 Discord Webhook Setup

```bash
# 1. Create webhook in Discord server settings
# 2. Copy URL
export DISCORD_WEBHOOK="https://discord.com/api/webhooks/..."

# 3. Use in digest
python -m axfl.cli digest --discord-webhook "$DISCORD_WEBHOOK"

# 4. Automate (cron at 18:00 UTC)
0 18 * * * cd /path/to/Algotrading-Bot && make digest
```

---

## 🔍 LIVE-PORT JSON Monitoring

```bash
# Watch risk-parity weights
tail -f logs/portfolio_live_*.jsonl | jq '.weights'

# Watch DD lock status
tail -f logs/portfolio_live_*.jsonl | jq '.dd_lock'

# Watch both
tail -f logs/portfolio_live_*.jsonl | jq '{weights, volatilities_pips, dd_lock}'
```

**Example Output**:
```json
{
  "weights": {
    "EURUSD": 0.35,
    "GBPUSD": 0.40,
    "XAUUSD": 0.25
  },
  "volatilities_pips": {
    "EURUSD": 12.5,
    "GBPUSD": 10.8,
    "XAUUSD": 18.2
  },
  "dd_lock": {
    "enabled": true,
    "active": false,
    "dd_pct": 2.15,
    "peak_equity": 102500.00,
    "threshold_pct": 5.0
  }
}
```

---

## 🧪 Testing

```bash
# Test risk-parity module
python axfl/risk/vol.py

# Run validation suite
python test_risk_parity_dd_validation.py

# Test CLI commands
make risk_parity
make digest

# Test in replay mode
make demo_replay
```

---

## 🚨 Troubleshooting

### Risk-parity weights all equal?
**Cause**: Insufficient data or vol variance  
**Fix**: Increase lookback_d or check data quality

### DD lock triggers immediately?
**Cause**: Threshold too tight  
**Fix**: Increase trailing_pct from 5% to 7-10%

### Digest finds no trades?
**Cause**: Wrong date or no trades that day  
**Fix**: Check logs directory and date format (YYYYMMDD)

### Discord webhook fails?
**Cause**: Invalid URL  
**Fix**: Verify webhook URL in Discord settings

---

## 📚 Documentation

**Comprehensive Guide**: `docs/RISK_PARITY_AND_DD_LOCK.md`  
**Delivery Summary**: `RISK_PARITY_DD_DIGEST_SUMMARY.md`

---

## 🎓 Key Files

| File | Purpose | Lines |
|------|---------|-------|
| `axfl/risk/vol.py` | Risk-parity allocation | ~330 |
| `axfl/monitor/digest.py` | Daily PnL reports | ~420 |
| `axfl/portfolio/engine.py` | Integration | ~180 mod |
| `axfl/cli.py` | Commands | ~160 new |
| `axfl/config/sessions.yaml` | Configuration | ~18 added |
| `test_risk_parity_dd_validation.py` | Testing | ~380 |

---

## 📊 Default Values

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `lookback_d` | 20 | Days for vol estimation |
| `floor` | 0.15 (15%) | Min weight per symbol |
| `cap` | 0.60 (60%) | Max weight per symbol |
| `trailing_pct` | 5.0 (5%) | DD threshold |
| `cooloff_min` | 120 (2h) | Cooloff duration |

---

## ✅ Validation Status

```
✅ ALL TESTS PASSED

Risk-Parity:
  ✅ ATR computation
  ✅ Realized vol in pips
  ✅ Inverse-vol weights
  ✅ Floor/cap constraints
  ✅ Normalization to 1.0

Drawdown Lock:
  ✅ DD calculation
  ✅ Lock trigger
  ✅ Cooloff timer
  ✅ Recovery check

Daily Digest:
  ✅ Stats computation
  ✅ CSV generation
  ✅ Markdown generation
  ✅ PNG chart generation
  ✅ By-symbol/strategy breakdowns

Integration:
  ✅ Config parsing
  ✅ CLI commands
  ✅ Module imports
  ✅ LIVE-PORT JSON
```

---

**Updated**: October 20, 2025  
**Status**: ✅ Production Ready
