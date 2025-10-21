# AXFL Quick Reference Card

## Production Commands

### Health Check
```bash
make health
```
**What it does**: Validates config, checks API keys, lists upcoming session windows  
**Output**: `AXFL-HEALTH` JSON block with status, source, symbols, spreads, windows

---

### Daily PnL Snapshot
```bash
make snapshot
```
**What it does**: Scans trade logs, generates daily P&L report (CSV + Markdown)  
**Output**: `AXFL-PNL` JSON block + report files in `reports/`

---

### Demo Replay
```bash
make demo_replay
```
**What it does**: Replays last London session (06:30-10:30 UTC) with all configured symbols  
**Output**: `AXFL-LIVE-PORT` JSON block with guaranteed valid timestamps  
**Use case**: Test roster + timestamps without WebSocket complexity

---

### Live Portfolio (Replay Mode)
```bash
make live_port_replay
```
**What it does**: Runs portfolio engine in replay mode (historical data)  
**Output**: `AXFL-LIVE-PORT` blocks every 5 seconds

---

### Live Portfolio (WebSocket Mode)
```bash
make live_port_ws
```
**What it does**: Runs portfolio engine with live streaming data (Finnhub)  
**Output**: `AXFL-LIVE-PORT` blocks every 5 seconds  
**⚠️ Requires**: Valid Finnhub API keys

---

## JSON Block Reference

### AXFL-HEALTH
```json
{
  "ok": true,
  "source": "finnhub",
  "symbols": ["EURUSD", "GBPUSD", "XAUUSD"],
  "spreads": {"EURUSD": 0.6, "GBPUSD": 0.9, "XAUUSD": 2.5},
  "next_windows": [
    {"symbol": "EURUSD", "strategy": "lsg", "start": "07:00", "end": "10:00"},
    ...
  ]
}
```

### AXFL-PNL
```json
{
  "date": "2025-10-20",
  "totals": {"r": 2.5, "trades": 5, "pnl": 125.0},
  "by_strategy": [
    {"name": "lsg", "r": 1.5, "trades": 3, "wr": 66.7, "pnl": 75.0},
    ...
  ],
  "by_symbol": [...],
  "csv": "reports/pnl_20251020.csv",
  "md": "reports/pnl_20251020.md"
}
```

### AXFL-LIVE-PORT
```json
{
  "ok": true,
  "mode": "replay",
  "source": "auto",
  "interval": "5m",
  "since": "2025-10-18 06:15:00+00:00",  // Never None
  "now": "2025-10-20 10:45:00+00:00",    // Never None
  "symbols": ["EURUSD", "GBPUSD", "XAUUSD"],
  "engines": [
    {"symbol": "EURUSD", "strategy": "lsg", "state": "idle", ...},
    ...
  ],
  "positions": [],
  "today": {"r_total": 0.0, "pnl_total": 0.0, "by_strategy": [...]},
  "risk": {"halted": false, "global_daily_stop_r": -5.0},
  "costs": {"spreads": {...}, "slippage_model": "..."},
  "broker": {"mirror": "none", "connected": false, "errors": 0},
  "ws": {"connected": false, "errors": 0}
}
```

### AXFL-DIAG (Diagnostics)
```json
{
  "reason": "empty_schedule",
  "cfg": "path/to/config.yaml",
  "symbols": [],
  "strategies": []
}
```

---

## Troubleshooting

### Issue: "Empty schedule - no symbols or strategies"
**Cause**: Config file has empty `symbols` or `strategies` list  
**Fix**: Edit `axfl/config/sessions.yaml` to add symbols/strategies  
**Output**: DIAG block with details

### Issue: "All data providers failed"
**Cause**: API rate limits exceeded or invalid keys  
**Fix**: 
1. Check `FINNHUB_API_KEYS` and `TWELVEDATA_API_KEYS` env vars
2. Use `source: auto` for automatic fallback
3. Wait for rate limit reset (hourly/daily)

### Issue: Timestamps showing "None"
**Cause**: Status printed before first bar processed  
**Fix**: Already fixed! `_bar_processed` flag prevents this  
**Guaranteed**: Timestamps always valid after first bar

### Issue: Empty engines roster in demo-replay
**Cause**: No trade signals during selected session window  
**Expected**: Normal behavior - not all sessions have trades  
**Workaround**: Run longer replay or different date range

---

## Configuration Files

### sessions.yaml
**Location**: `axfl/config/sessions.yaml`  
**Purpose**: Portfolio-level config (symbols, strategies, spreads, windows)  
**Key fields**:
- `portfolio.symbols`: List of symbols to trade
- `portfolio.source`: Data provider ("auto", "finnhub", "twelvedata")
- `portfolio.spreads`: Per-symbol spread costs (pips)
- `strategies[].windows`: Trading session windows (HH:MM UTC)

### Environment Variables
```bash
export FINNHUB_API_KEYS="key1,key2,key3"
export TWELVEDATA_API_KEYS="key1,key2,key3"
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
```

---

## Safety Guarantees

✅ **Schedule Validation**: Empty schedules detected before engine start  
✅ **Timestamp Safety**: Never None after first bar processed  
✅ **Source Fallback**: Defaults to "auto" if unset/invalid  
✅ **Fail-Fast**: Early exit with DIAG on configuration errors  
✅ **Rate Limit Handling**: API key rotation with backoff  

---

## Testing Workflow

1. **Validate Config**: `make health`
2. **Test Replay**: `make demo_replay`
3. **Check Snapshot**: `make snapshot` (if trades exist)
4. **Run Portfolio Replay**: `make live_port_replay`
5. **Go Live**: `make live_port_ws` (with valid API keys)

---

## Alert Integration

### Discord Webhook
Set `DISCORD_WEBHOOK_URL` environment variable:
```bash
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/YOUR_WEBHOOK"
```

### Alert Levels
- **send_event()**: Green - Trade executions, key events
- **send_info()**: Blue - Informational messages
- **send_warn()**: Yellow - Warnings, non-critical issues
- **send_error()**: Red - Errors, failed operations
- **send_diag()**: Gray - Diagnostic info, structured data

### Usage in Code
```python
from axfl.monitor import send_info, send_warn, send_error, send_diag

send_info("Portfolio engine started")
send_warn("Low balance detected", {"balance": 1000})
send_error("API connection failed", {"error": "timeout"})
send_diag("Config validation", {"cfg": "sessions.yaml", "valid": True})
```

---

## Performance Tips

- **demo-replay**: Fast testing without API limits (uses cached data)
- **source: auto**: Automatic fallback between providers
- **extend parameter**: Adjust window edges (default 15 minutes)
- **status_every_s**: Control status print frequency (default 5s)
- **warmup_days**: More data = better signals but slower startup

---

## Emergency Procedures

### Stop Live Trading
1. `Ctrl+C` to interrupt process
2. Check `data/trades/` for open positions
3. Manually close positions in broker if needed

### Clear State
```bash
# Remove trade logs
rm data/trades/*.csv

# Remove PnL reports
rm reports/*.csv reports/*.md

# Clean Python cache
make clean
```

### Recover from Crash
1. Check logs for errors: `tail -100 logs/portfolio_live_*.jsonl`
2. Verify no orphaned positions in broker
3. Run `make health` to validate config
4. Restart with `make live_port_ws` or `make live_port_replay`

---

## Support

**Documentation**: See `docs/` directory for detailed guides  
**Testing**: Run `pytest tests/` for unit tests  
**Issues**: Check `COMPREHENSIVE_DIAGNOSTIC_REPORT.md` for known issues

---

**Version**: 1.0  
**Last Updated**: October 20, 2025  
**Status**: Production Ready ✅
