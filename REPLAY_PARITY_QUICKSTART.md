# Replay Parity Pack - Quick Start Guide

## What is Replay Parity?

**Problem:** When you scan for signals and replay them, you want the EXACT same parameters that were used in the backtest to be applied during replay. Otherwise, you might get different results.

**Solution:** The Replay Parity Pack embeds the exact parameters from the backtester into the scan output, then applies them during replay.

## Quick Start (3 Steps)

### Step 1: Scan with Heuristic Mode (Recommended for Development)
```bash
python -m axfl.cli scan --symbols EURUSD,GBPUSD --strategies lsg,orb \
  --days 30 --source auto --venue OANDA \
  --method heuristic --pad_before 60 --pad_after 60
```

**Output:**
```
###BEGIN-AXFL-SCANS###
{"meta":{...},"targets":[...]}
###END-AXFL-SCANS###
```

### Step 2: Copy the SCANS JSON Block

Copy everything between `###BEGIN-AXFL-SCANS###` and `###END-AXFL-SCANS###` (including the curly braces).

### Step 3: Replay the Windows
```bash
python -m axfl.cli replay-slice --scans 'PASTE_JSON_HERE' \
  --use_scan_params false \
  --warmup_days 3 \
  --assert_min_trades 0
```

**Why `use_scan_params false`?** Heuristic mode doesn't embed params, so we use default strategy params instead.

**Why `assert_min_trades 0`?** Heuristic patterns don't guarantee actual trade entries, just high-probability windows.

## Advanced Usage (With Parameter Parity)

When you have access to more historical data (paid API or local cache):

### Step 1: Scan with Exact Mode
```bash
python -m axfl.cli scan --symbols EURUSD,GBPUSD --strategies lsg,orb \
  --days 90 --source auto --venue OANDA \
  --method exact --pad_before 60 --pad_after 60
```

This runs the REAL backtester and embeds exact params in the output.

### Step 2: Replay with Param Parity
```bash
python -m axfl.cli replay-slice --scans 'PASTE_JSON_HERE' \
  --use_scan_params true \
  --warmup_days 3 \
  --assert_min_trades 1
```

Now the replay uses the EXACT same params that produced trades in the scan.

## Command Reference

### Scan Flags
| Flag | Values | Description |
|------|--------|-------------|
| `--symbols` | EURUSD,GBPUSD,... | Comma-separated symbols |
| `--strategies` | lsg,orb,arls | Comma-separated strategies |
| `--days` | 30, 90, 180 | Lookback period |
| `--method` | exact, heuristic, volatility, auto | Scan method |
| `--pad_before` | 60 | Minutes to add before entry |
| `--pad_after` | 60 | Minutes to add after entry |
| `--top` | 3 | Top N windows (volatility mode) |

### Replay Flags
| Flag | Default | Description |
|------|---------|-------------|
| `--scans` | Required | JSON from scan output |
| `--use_scan_params` | true | Apply embedded params |
| `--warmup_days` | 3 | Days of warmup data |
| `--assert_min_trades` | 1 | Expected minimum trades |
| `--extend` | 0 | Extra minutes per window |

## Scan Methods Explained

### 1. `exact` (Backtester - Slowest, Most Accurate)
- Runs full backtest for each (symbol, strategy)
- Captures real trade entry times
- **Embeds params** in output
- Use for: Production verification

### 2. `heuristic` (Pattern-Based - Fast, Reliable)
- Looks for strategy-specific patterns
- LSG: BOS + pullback
- ORB: Range breakout during open
- ARLS: Liquidity sweep
- **No params** embedded
- Use for: Development, testing

### 3. `volatility` (ATR-Based - Fastest)
- Selects top N days by average ATR
- No strategy logic
- **No params** embedded
- Use for: Quick smoke tests

### 4. `auto` (Fallback Chain)
- Tries: exact → heuristic → volatility
- Use for: Robust scanning

## Makefile Shortcuts

### Quick Heuristic Scan
```bash
make scan_london_auto
```
Scans EURUSD/GBPUSD/XAUUSD with LSG/ORB/ARLS using auto method (45 days).

### Exact Mode Scan
```bash
make scan_exact
```
Scans EURUSD/GBPUSD with LSG/ORB/ARLS using exact method (30 days, 60m padding).

### Replay Template
```bash
# Edit Makefile first, replace SCANS_JSON with actual JSON
make replay_exact
```

## Understanding the Output

### During Scan
```
=== AXFL Signal Scanner ===
Symbols: ['EURUSD', 'GBPUSD']
Strategies: ['lsg', 'orb']
Method: heuristic
Padding: 60m before, 60m after

Scanning...
DEBUG: EURUSD/lsg: 3 windows found (method: heuristic)
DEBUG: EURUSD/orb: 2 windows found (method: heuristic)

###BEGIN-AXFL-SCANS###
{...}
###END-AXFL-SCANS###
```

**Copy the JSON block** (everything between the `###` markers).

### During Replay
```
=== AXFL Targeted Replay ===
Loaded 5 targets
Using scan-embedded params where available
Warmup: 3 days
Assert min trades: 0
Earliest window: 2025-10-18 06:15:00+00:00

Applying scan params to EURUSD/lsg: {...}  # Only if use_scan_params=true

Starting targeted replay...
Portfolio warmup complete: 2 engines ready

###BEGIN-AXFL-LIVE-PORT###
{...}
###END-AXFL-LIVE-PORT###

Total trades executed: 0
Assertion passed: 0 >= 0
```

## Common Issues & Solutions

### Issue: "No windows found"
**Solution:** Strategies are conservative. Try:
- Increase `--days` (30 → 90 → 180)
- Use `--method heuristic` or `--method auto`
- Try different symbols (XAUUSD often more volatile)

### Issue: "Assertion failed: 0 trades"
**Solution:** Windows don't guarantee trades. Either:
- Set `--assert_min_trades 0` for discovery mode
- Use `--method exact` to ensure windows have real trades
- Check DIAG block for `windows_used` count

### Issue: "Params not applied"
**Solution:** Check:
- Scan used `--method exact` (only exact embeds params)
- Replay has `--use_scan_params true`
- Scan JSON contains `"params"` field in targets

### Issue: "Data provider error"
**Solution:**
- TwelveData free tier caps at 5000 bars (~25 days)
- Use `--days 30` or less
- Consider upgrading to paid tier for longer lookbacks

## Workflow Examples

### Example 1: Quick Discovery
```bash
# Find high-probability windows
python -m axfl.cli scan --symbols EURUSD --strategies lsg,orb \
  --days 30 --method heuristic --pad_before 60 --pad_after 60

# Replay with defaults
python -m axfl.cli replay-slice --scans '{...}' \
  --use_scan_params false --assert_min_trades 0
```

### Example 2: Exact Verification
```bash
# Find real backtest entries
python -m axfl.cli scan --symbols EURUSD --strategies lsg \
  --days 90 --method exact --pad_before 60 --pad_after 60

# Replay with exact params
python -m axfl.cli replay-slice --scans '{...}' \
  --use_scan_params true --assert_min_trades 1
```

### Example 3: Volatility-Based Testing
```bash
# Get top 3 volatile days
python -m axfl.cli scan --symbols EURUSD --strategies lsg,orb \
  --days 45 --method volatility --top 3

# Replay for stress testing
python -m axfl.cli replay-slice --scans '{...}' \
  --warmup_days 5 --assert_min_trades 0
```

## Pro Tips

1. **Start with heuristic mode** for development - it's fast and reliable
2. **Use exact mode for final verification** before deploying live
3. **Set assert_min_trades=0** when exploring new strategies
4. **Increase warmup_days** for strategies that need more context (e.g., LSG needs structure)
5. **Extend windows** if you think entries might be just outside: `--extend 30`
6. **Check DIAG blocks** when assertions fail - they tell you exactly what happened

## What's Next?

- Read full documentation: `REPLAY_PARITY_PACK.md`
- See implementation details: `REPLAY_PARITY_IMPLEMENTATION.md`
- Run smoke tests: `pytest tests/`
- Check live trading guide: `docs/LIVE_TRADING_SUMMARY.md`

## Need Help?

Common questions:
- **Q:** Do I always need to use exact mode?  
  **A:** No! Heuristic mode is great for development. Use exact for final verification.

- **Q:** Why use replay instead of just backtesting?  
  **A:** Replay verifies signals in a live-like environment with warmup, filtering, and real-time aggregation.

- **Q:** Can I scan multiple symbols at once?  
  **A:** Yes! Use `--symbols EURUSD,GBPUSD,XAUUSD` (comma-separated, no spaces).

- **Q:** What if I want to test my own params?  
  **A:** Run a regular backtest with `--params '{...}'`, or use tune command for optimization.

---

**Ready to start?** Run: `make scan_london_auto` and follow the output!
