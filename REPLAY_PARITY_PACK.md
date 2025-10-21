# AXFL Replay Parity Pack

## Overview

The **Replay Parity Pack** ensures exact parameter matching between signal scanning and targeted replay, enabling precise verification of trading signals.

### Key Features

1. **Exact Parameter Embedding**: When using `--method exact`, the scanner runs the REAL backtester and embeds the exact parameters used into the scan output
2. **Parameter Application**: The replay-slice command extracts and applies these embedded parameters to each strategy engine
3. **Trade Assertions**: Optionally assert minimum trade count to verify signal quality
4. **Warmup Support**: Configurable warmup period to ensure strategies are properly initialized
5. **Diagnostic Blocks**: Emit AXFL-DIAG block when assertions fail

## Scan Modes

### 1. Exact Mode (Backtester)
```bash
make scan_exact
# OR
python -m axfl.cli scan --symbols EURUSD,GBPUSD --strategies lsg,orb,arls \
  --days 30 --source auto --venue OANDA \
  --method exact --pad_before 60 --pad_after 60
```

**How it works:**
- Runs the full backtester for each (symbol, strategy) combination
- Captures actual trade entry timestamps
- Embeds exact parameters used (including defaults + overrides)
- Returns windows with `params` field containing strategy configuration

**Output format:**
```json
{
  "meta": {
    "source": "auto",
    "interval": "5m",
    "days": 30,
    "method": "exact",
    "pad_before": 60,
    "pad_after": 60,
    "scanned_at": "2025-10-20T03:24:53.124339"
  },
  "targets": [
    {
      "symbol": "EURUSD",
      "strategy": "lsg",
      "params": {
        "tol_pips": 2,
        "sweep_pips": 3,
        "reentry_window_m": 30,
        "bos_buffer_pips": 0.5,
        "confirm_body_required": true,
        "second_move_only": true,
        "bos_required": true
      },
      "windows": [
        {
          "start": "2025-10-18T06:50:00+00:00",
          "end": "2025-10-18T08:50:00+00:00",
          "bar": "2025-10-18T07:50:00+00:00"
        }
      ]
    }
  ],
  "ok": true
}
```

### 2. Heuristic Mode (Pattern-Based)
```bash
python -m axfl.cli scan --symbols EURUSD,GBPUSD --strategies lsg,orb \
  --days 30 --source auto --venue OANDA \
  --method heuristic --pad_before 60 --pad_after 60
```

**How it works:**
- Uses strategy-specific pattern detection (no full backtest)
- LSG: Looks for BOS + pullback patterns
- ORB: Detects range breakouts during opening hours
- ARLS: Finds liquidity sweep candidates
- **Does NOT embed params** (uses default strategy parameters)

### 3. Volatility Mode (ATR-Based)
```bash
python -m axfl.cli scan --symbols EURUSD,GBPUSD --strategies lsg,orb \
  --days 30 --source auto --venue OANDA \
  --method volatility --top 3
```

**How it works:**
- Selects top N days by average ATR
- No params embedded (volatility-agnostic)

### 4. Auto Mode (Fallback Chain)
```bash
python -m axfl.cli scan --symbols EURUSD,GBPUSD --strategies lsg,orb \
  --days 30 --source auto --venue OANDA \
  --method auto --top 3
```

**How it works:**
- Tries: exact → heuristic → volatility
- Falls back to next method if previous returns empty

## Replay-Slice Command

### Basic Usage
```bash
python -m axfl.cli replay-slice --scans 'PASTE_SCANS_JSON_HERE'
```

### Replay Parity Mode (Use Scan Params)
```bash
make replay_exact
# OR
python -m axfl.cli replay-slice --scans 'SCANS_JSON' \
  --use_scan_params true \
  --warmup_days 3 \
  --assert_min_trades 1 \
  --extend 0
```

### Parameters

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--scans` | JSON | Required | Paste AXFL-SCANS block from scan output |
| `--use_scan_params` | bool | `true` | Apply embedded params from scan (exact mode only) |
| `--warmup_days` | int | `3` | Days of historical data to warm up strategies |
| `--assert_min_trades` | int | `1` | Minimum trades expected; emit DIAG if not met |
| `--extend` | int | `0` | Minutes to extend each window (before/after) |
| `--ignore_yaml_windows` | bool | `false` | Ignore sessions.yaml windows config |

## Parameter Resolution Flow

### Scan (Exact Mode)
1. Load strategy class (e.g., `LSGStrategy`)
2. Call `resolve_params(strategy, overrides={})`
   - Merges strategy defaults + config defaults + overrides
3. Run backtester with resolved params
4. Embed `params` dict in target output

### Replay-Slice (With use_scan_params=true)
1. Parse scan JSON targets
2. Extract `params` field from each target
3. Build `strategies_params` dict: `{(symbol, strategy): params}`
4. Initialize PortfolioEngine
5. Apply params to each engine: `engine.engines[key].strategy.params = params`
6. Run replay with window filtering

## Trade Assertions

When `--assert_min_trades > 0`, the replay-slice command will:

1. Count total trades across all engines
2. Compare against threshold
3. Emit AXFL-DIAG block if assertion fails

### Example DIAG Block
```json
###BEGIN-AXFL-DIAG###
{
  "ok": false,
  "reason": "assertion_failed",
  "expected_min_trades": 1,
  "actual_trades": 0,
  "targets_count": 2,
  "windows_used": {
    "EURUSD": 30
  },
  "engines": [
    ["EURUSD", "lsg"],
    ["EURUSD", "orb"]
  ],
  "scan_params_applied": true
}
###END-AXFL-DIAG###
```

## Warmup Calculation

The replay automatically computes warmup period:

1. Find earliest window start across all targets
2. Subtract `warmup_days` days
3. Load historical data from `earliest_start - warmup_days` to `earliest_start`
4. Process bars to prepare strategy state before first target window

**Example:**
- Earliest window: `2025-10-18 06:15:00 UTC`
- Warmup: 3 days
- Data loaded from: `2025-10-15 06:15:00 UTC`
- Warmup bars processed: `2025-10-15 06:15` → `2025-10-18 06:15`
- Target replay starts: `2025-10-18 06:15:00 UTC`

## Output Blocks

### AXFL-SCANS (from scan command)
Contains:
- `meta`: Scan configuration
- `targets`: Array of (symbol, strategy, windows, params?)
- `ok`: Success flag

### AXFL-LIVE-PORT (from replay-slice command)
Contains:
- `mode`: "replay"
- `since`: First bar timestamp
- `now`: Last bar timestamp
- `engines`: Strategy roster
- `positions`: Open positions
- `today`: Portfolio stats (R, PnL, trades)
- `targets_used`: Bars processed per symbol
- `ok`: Success flag

**Timestamp Guarantee:** `since <= now` (enforced in portfolio engine)

### AXFL-DIAG (optional, on assertion failure)
Contains:
- `ok`: false
- `reason`: "assertion_failed"
- `expected_min_trades`: Threshold
- `actual_trades`: Observed count
- `targets_count`: Number of scan targets
- `windows_used`: Bars processed per symbol
- `engines`: List of (symbol, strategy) keys
- `scan_params_applied`: Boolean flag

## Complete Workflow Example

### Step 1: Run Exact Scan
```bash
$ make scan_exact

=== AXFL Signal Scanner ===
Symbols: ['EURUSD', 'GBPUSD']
Strategies: ['lsg', 'orb', 'arls']
Days: 30
Method: exact
Padding: 60m before, 60m after

Scanning...
DEBUG: EURUSD/lsg: 2 windows found (method: exact)
DEBUG: EURUSD/orb: 1 windows found (method: exact)

###BEGIN-AXFL-SCANS###
{"meta":{"method":"exact","pad_before":60,"pad_after":60},"targets":[{"symbol":"EURUSD","strategy":"lsg","params":{"tol_pips":2,"sweep_pips":3},"windows":[...]}],"ok":true}
###END-AXFL-SCANS###
```

### Step 2: Copy SCANS JSON

Copy everything between `###BEGIN-AXFL-SCANS###` and `###END-AXFL-SCANS###`

### Step 3: Run Replay with Parity
```bash
$ python -m axfl.cli replay-slice --scans 'PASTE_JSON_HERE' \
    --use_scan_params true --warmup_days 3 --assert_min_trades 1

=== AXFL Targeted Replay ===
Loaded 3 targets
Using scan-embedded params where available
Warmup: 3 days
Assert min trades: 1
Earliest window: 2025-10-18 06:50:00+00:00

Applying scan params to EURUSD/lsg: {'tol_pips': 2, 'sweep_pips': 3, ...}
Applying scan params to EURUSD/orb: {}

Starting targeted replay...
=== Portfolio Warmup Phase ===
Loading 3 days of 1m data for EURUSD...
  ✓ EURUSD: 4320 bars 1m → 875 bars 5m

Initialized: EURUSD / lsg
  Params: {'tol_pips': 2, 'sweep_pips': 3, ...}

Portfolio warmup complete: 2 engines ready

=== Replay Mode ===
Loaded 1440 1m bars for EURUSD

###BEGIN-AXFL-LIVE-PORT###
{"ok":true,"mode":"replay","since":"2025-10-15 12:15:00+00:00","now":"2025-10-18 08:45:00+00:00","targets_used":{"EURUSD":30},...}
###END-AXFL-LIVE-PORT###

Total trades executed: 2
Assertion passed: 2 >= 1
```

## Makefile Targets

### scan_exact
Runs exact mode scan with 60-minute padding on EURUSD/GBPUSD for 30 days.

```bash
make scan_exact
```

### replay_exact
Template for replay with parity (requires manual JSON paste).

```bash
# 1. Edit Makefile, replace SCANS_JSON with actual JSON
# 2. Run:
make replay_exact
```

## Implementation Details

### Files Modified

1. **axfl/tools/signal_scan.py**
   - `windows_from_backtest()`: Now returns `tuple[list[dict], dict]` with (windows, params_used)
   - `scan_symbols()`: Uses `resolve_params()` for proper defaults
   - Embeds `params` field in target entries for exact mode

2. **axfl/live/targets.py**
   - Added `earliest_start()` helper: Returns earliest window start for warmup calculation

3. **axfl/cli.py**
   - `replay-slice` command: Added flags for use_scan_params, warmup_days, assert_min_trades
   - Applies embedded params to strategy engines when available
   - Counts trades and emits DIAG block on assertion failure

4. **axfl/portfolio/engine.py**
   - `_print_status()`: Ensures `since <= now` (handles replay edge cases)

5. **Makefile**
   - Added `scan_exact` target
   - Added `replay_exact` target

### Key Functions

#### resolve_params(strategy_class, overrides)
Located in `axfl/config/defaults.py`. Merges:
1. Strategy's built-in defaults
2. Config file defaults
3. User overrides

Returns complete parameter dictionary.

#### earliest_start(targets)
Located in `axfl/live/targets.py`. 
- Iterates all target windows
- Returns earliest start timestamp (tz-aware UTC)
- Used for warmup period calculation: `earliest_start - warmup_days`

#### window_filter(timestamp, windows)
Located in `axfl/live/targets.py`.
- Checks if timestamp falls within any window
- Handles timezone conversions
- Used by replay to skip bars outside target windows

## Limitations

1. **Exact mode may find no trades**: SMC strategies are conservative and may not produce entries in recent data
2. **Data provider limits**: TwelveData free tier caps at 5000 bars (~25 days of 5m data), limiting exact mode effectiveness
3. **Heuristic mode doesn't embed params**: Pattern-based detection can't guarantee exact backtest reproduction
4. **Warmup period must be sufficient**: Strategies need adequate history to build structure context
5. **Assertion failures are informational**: DIAG block emitted but replay doesn't exit with error code

## Practical Usage

Given data provider limitations, the recommended workflow is:

### For Development/Testing (Use Heuristic Mode)
```bash
# Scan with heuristic patterns (works with limited data)
python -m axfl.cli scan --symbols EURUSD,GBPUSD --strategies lsg,orb \
  --days 30 --source auto --venue OANDA \
  --method heuristic --pad_before 60 --pad_after 60

# Replay WITHOUT param parity (uses default strategy params)
python -m axfl.cli replay-slice --scans 'SCANS_JSON' \
  --use_scan_params false \
  --warmup_days 3 \
  --assert_min_trades 0
```

### For Production (Use Exact Mode with Longer Data)
When you have access to more historical data (via paid data provider or local cache):

```bash
# Scan with exact backtest params
python -m axfl.cli scan --symbols EURUSD,GBPUSD --strategies lsg,orb \
  --days 90 --source auto --venue OANDA \
  --method exact --pad_before 60 --pad_after 60

# Replay WITH param parity
python -m axfl.cli replay-slice --scans 'SCANS_JSON' \
  --use_scan_params true \
  --warmup_days 3 \
  --assert_min_trades 1
```

## Troubleshooting

### No windows found in exact mode
- Strategies too selective for recent data
- Try longer time period: `--days 90` or `--days 180`
- Use heuristic mode for discovery: `--method heuristic`

### Assertion failed: 0 trades
- Windows may not contain actual trade opportunities
- Reduce `--assert_min_trades` to 0 for discovery mode
- Check DIAG block for `windows_used` count (may be filtering too aggressively)

### Params not applied
- Verify scan used `--method exact`
- Check target JSON has `params` field
- Ensure `--use_scan_params true` in replay command

### Timestamp errors (since > now)
- Fixed in portfolio engine `_print_status()`
- Handles replay edge cases where processing goes backwards

## Future Enhancements

1. **Auto-paste from clipboard**: Detect scan JSON automatically
2. **Multi-pass assertions**: Track trades per strategy, not just total
3. **Param diff reporting**: Show which params differ from defaults
4. **Window merging**: Combine overlapping windows to reduce data loading
5. **Exit code on assertion failure**: Enable CI/CD integration

## References

- Signal Scanner: `axfl/tools/signal_scan.py`
- Targeted Replay: `axfl/cli.py` (replay-slice command)
- Parameter Resolution: `axfl/config/defaults.py`
- Window Filtering: `axfl/live/targets.py`
- Portfolio Engine: `axfl/portfolio/engine.py`

---

**Version:** 1.0  
**Last Updated:** 2025-10-20  
**Status:** ✅ Complete & Tested
