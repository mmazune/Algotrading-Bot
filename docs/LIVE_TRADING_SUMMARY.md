# AXFL Live Trading Guide

## Overview

AXFL supports live paper trading with optional broker mirroring for practice/live accounts. The system can operate in two modes:

- **Replay Mode**: Historical 1m data aggregated to 5m bars for testing
- **WebSocket Mode**: Real-time streaming from Finnhub (forex via OANDA venue)

AXFL maintains PnL as the source of truth; broker mirroring is best-effort with reconciliation logs.

## Environment Variables

### Required for WebSocket Mode

```bash
# Finnhub API Keys (comma-separated for rotation)
export FINNHUB_API_KEYS="key1,key2,key3"
```

### Required for OANDA Mirroring

```bash
# OANDA Practice/Live credentials
export OANDA_API_KEY="your-practice-or-live-token"
export OANDA_ACCOUNT_ID="your-account-id"
export OANDA_ENV="practice"  # or "live"
```

## Running the Portfolio

### Replay Mode (No Mirror)

```bash
python -m axfl.cli live-port \
  --cfg axfl/config/sessions.yaml \
  --mode replay \
  --mirror none
```

### WebSocket Mode (No Mirror)

```bash
python -m axfl.cli live-port \
  --cfg axfl/config/sessions.yaml \
  --mode ws \
  --source finnhub \
  --mirror none
```

### WebSocket Mode with OANDA Mirroring

**Prerequisites:**
1. Set OANDA environment variables (see above)
2. Set FINNHUB_API_KEYS environment variable
3. Verify OANDA credentials with practice account

```bash
python -m axfl.cli live-port \
  --cfg axfl/config/sessions.yaml \
  --mode ws \
  --source finnhub \
  --mirror oanda
```

## Architecture

### WebSocket Streaming

- **Source**: Finnhub WebSocket API
- **Venue**: OANDA forex quotes
- **Symbols**: OANDA:EUR_USD, OANDA:GBP_USD, OANDA:XAU_USD
- **Aggregation**: 1m ticks → 5m bars via CascadeAggregator
- **Reconnection**: Automatic with exponential backoff
- **Key Rotation**: Automatic on 429/403 errors

### Broker Mirroring

- **Mode**: Best-effort, non-blocking
- **Position Sizing**: Fixed $500 risk per trade
- **Order Type**: Market orders with attached SL/TP
- **Reconciliation**: Logged to `logs/broker_oanda_YYYYMMDD.jsonl`
- **Failures**: Logged but do not affect AXFL position tracking

### Weekday Gating

- **Active Days**: Monday–Friday (UTC)
- **Weekends**: No trading (Sat=5, Sun=6)
- **Holidays**: Manual calendar integration (future TODO)

## LIVE PORT JSON Structure

The system emits unified status blocks with the following structure:

```json
{
  "ok": true,
  "mode": "replay|ws",
  "source": "twelvedata|finnhub",
  "interval": "5m",
  "since": "2025-10-15 07:25:00+00:00",
  "now": "2025-10-17 23:55:00+00:00",
  "symbols": ["EURUSD", "GBPUSD", "XAUUSD"],
  "engines": [
    {
      "symbol": "EURUSD",
      "strategy": "lsg",
      "windows": ["07:00-10:00"],
      "active": true,
      "spread_pips": 0.6,
      "live_overrides": true
    }
    // ... 8 more engines (3 symbols × 3 strategies)
  ],
  "positions": [],
  "today": {
    "r_total": 0.0,
    "pnl_total": 0.0,
    "by_strategy": [
      {"name": "lsg", "r": 0.0, "trades": 0, "pnl": 0.0},
      {"name": "orb", "r": 0.0, "trades": 0, "pnl": 0.0},
      {"name": "arls", "r": 0.0, "trades": 0, "pnl": 0.0}
    ]
  },
  "risk": {
    "halted": false,
    "global_daily_stop_r": -5.0
  },
  "costs": {
    "spreads": {"EURUSD": 0.6, "GBPUSD": 0.9, "XAUUSD": 2.5},
    "slippage_model": "max(1 pip, ATR/1000)"
  },
  "broker": {
    "mirror": "none|oanda",
    "connected": false,
    "errors": 0
  },
  "ws": {
    "connected": false,
    "errors": 0,
    "key_index": 0
  }
}
```

## Monitoring

### Real-time Logs

- **Portfolio Status**: Emitted every `status_every_s` seconds
- **Broker Events**: `logs/broker_oanda_YYYYMMDD.jsonl`
- **Portfolio Events**: `logs/portfolio_live_YYYYMMDD.jsonl`

### Status Fields

- **engines**: Complete roster of (symbol, strategy) pairs
- **positions**: Currently open positions with broker_order_id if mirrored
- **today.by_strategy**: Per-strategy R and PnL aggregation
- **broker**: Mirror status and error count
- **ws**: WebSocket connection status and key rotation index

## Troubleshooting

### WebSocket Connection Failures

1. Check FINNHUB_API_KEYS is set correctly
2. Verify keys are valid (test with curl)
3. Check logs for rate limit errors (429)
4. System will auto-rotate keys on failure

### OANDA Mirror Failures

1. Verify OANDA_API_KEY and OANDA_ACCOUNT_ID are set
2. Check account has sufficient margin
3. Review `logs/broker_oanda_*.jsonl` for detailed errors
4. Mirror failures do not affect AXFL paper trading

### No Trades Generated

1. Verify trading windows align with current UTC time
2. Check weekday gating (no trading on weekends)
3. Review strategy-specific debug counters
4. Confirm risk limits not exceeded

## Deployment Notes

### Production Considerations

1. **API Keys**: Rotate Finnhub keys regularly
2. **Monitoring**: Set up alerts on `broker.errors` and `ws.errors`
3. **Reconciliation**: Daily review of broker mirror logs
4. **Failover**: System falls back to replay if WebSocket unavailable
5. **Holidays**: Manual calendar updates required (future enhancement)

### Performance

- **WebSocket**: ~10-50ms latency for tick delivery
- **Aggregation**: Sub-millisecond bar completion
- **Broker Mirror**: ~100-300ms per order (non-blocking)
- **Status Updates**: Configurable (default: 90s)

## Support

For issues or questions:
- Check logs in `logs/` directory
- Review broker reconciliation logs
- Verify environment variables are set correctly
- Test with replay mode first before WebSocket
- Start without mirror before enabling broker integration

---

## Go-Live v1: Monitoring & Alerts

### Discord Alerts (Optional)

Set up optional Discord webhook notifications for key events:

```bash
# Set webhook URL (if not set, alerts are no-op)
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
```

**Alert Events:**
- `WS_CONNECTED`: First WebSocket connection established
- `TRADE_OPEN`: Position opened (includes "first_of_day" flag)
- `TRADE_CLOSE`: Position closed with P&L
- `DAILY_STOP_HIT`: Global daily stop loss triggered
- `ENGINE_STOP`: Graceful shutdown or user interrupt
- `ENGINE_ERROR`: Critical error occurred

### Health Check

Check system health before going live:

```bash
make health
# OR
python -m axfl.cli health --cfg axfl/config/sessions.yaml
```

**Output:**
```json
###BEGIN-AXFL-HEALTH###
{
  "ok": true,
  "source": "twelvedata",
  "symbols": ["EURUSD", "GBPUSD", "XAUUSD"],
  "spreads": {"EURUSD": 0.6, "GBPUSD": 0.9, "XAUUSD": 2.5},
  "next_windows": [
    {"symbol": "EURUSD", "strategy": "lsg", "start": "07:00", "end": "10:00"},
    ...
  ]
}
###END-AXFL-HEALTH###
```

### Daily PnL Snapshot

Generate daily performance reports:

```bash
make snapshot
# OR
python -m axfl.cli snapshot
```

**Output:**
```json
###BEGIN-AXFL-PNL###
{
  "ok": true,
  "date": "2025-10-20",
  "totals": {"r": 2.4, "trades": 5, "pnl": 1250.50},
  "by_strategy": [
    {"name": "lsg", "r": 1.2, "trades": 2, "wr": 100.0, "pnl": 625.25},
    {"name": "orb", "r": 1.2, "trades": 3, "wr": 66.7, "pnl": 625.25}
  ],
  "by_symbol": [
    {"symbol": "EURUSD", "r": 1.8, "trades": 3, "wr": 66.7, "pnl": 937.88},
    {"symbol": "GBPUSD", "r": 0.6, "trades": 2, "wr": 100.0, "pnl": 312.62}
  ],
  "csv": "reports/pnl_20251020.csv",
  "md": "reports/pnl_20251020.md"
}
###END-AXFL-PNL###
```

**Reports Generated:**
- `reports/pnl_YYYYMMDD.csv`: CSV format for analysis
- `reports/pnl_YYYYMMDD.md`: Markdown format for documentation

### Pre-Live Checklist

Before enabling live trading:

1. ✅ Run `make health` - verify data sources and session windows
2. ✅ Test replay mode without mirror - validate strategies
3. ✅ Set Discord webhook (optional) - get trade notifications
4. ✅ Run with paper trading first - verify execution logic
5. ✅ Enable OANDA practice mirror - test order placement
6. ✅ Monitor for 1 week - verify stability
7. ✅ Review daily snapshots - check performance metrics
8. ✅ Switch to live environment - start with minimal position sizing

### Daily Operations

**Morning Routine:**
```bash
# 1. Check health before session
make health

# 2. Start live trading
python -m axfl.cli live-port --cfg axfl/config/sessions.yaml --mode ws --mirror oanda
```

**Evening Routine:**
```bash
# 1. Generate daily snapshot
make snapshot

# 2. Review reports
cat reports/pnl_$(date +%Y%m%d).md

# 3. Check logs for errors
tail -50 logs/portfolio_live_$(date +%Y%m%d).jsonl
```

### Monitoring Dashboard (Future)

Planned features for v2:
- Real-time web dashboard
- Automated health checks every 5 minutes
- SMS alerts for critical events
- Performance analytics with charts
- Risk heatmaps by symbol/strategy

---

## NY Session Pack + Daily Runner

### Overview

The **NY Session Pack** extends AXFL to support both London and New York trading sessions with automated daily execution.

**Key Features:**
- Dual-session trading: London (07:00-10:00 UTC) + NY (12:30-16:00 UTC)
- Session-specific parameter tuning (NY markets have higher volatility)
- Automated daily runner with failover
- Discord alerts on session events
- Daily PnL snapshot at 16:05 UTC

### Configuration

The NY session uses a separate config profile in `axfl/config/sessions.yaml`:

```yaml
# London session (existing)
portfolio:
  symbols: ["EURUSD", "GBPUSD", "XAUUSD"]
  strategies:
    - name: "lsg"
      windows:
        - start: "07:00"
          end: "10:00"

# NY session (new)
portfolio_ny:
  symbols: ["EURUSD", "GBPUSD", "XAUUSD"]
  strategies:
    - name: "lsg"
      params:
        bos_buffer_pips: 0.5
        tol_pips: 2.5
      windows:
        - start: "12:30"
          end: "16:00"
    - name: "orb"
      params:
        session: "ny"  # Uses NY opening range (12:30)
        thr_break_pips: 4
        filter_min_or_pips: 5
      windows:
        - start: "12:30"
          end: "16:00"
```

### NY-Specific Overrides

**ORB Strategy:**
- Detects `session: "ny"` parameter
- Uses 12:30 UTC opening range (NY market open)
- Wider break thresholds (4 pips vs 3 pips)
- Larger minimum OR size (5 pips vs 4 pips)

**LSG Strategy:**
- Wider tolerance and sweep ranges
- Adjusted reentry windows for NY volatility

**ARLS Strategy:**
- Higher ATR multipliers
- Larger minimum range filters

### Daily Runner

The **daily-runner** command automates both sessions with intelligent failover:

```bash
# Start daily runner
make daily_runner

# Or with custom config
python -m axfl.cli daily-runner --cfg axfl/config/sessions.yaml
```

**Flow:**
1. **06:00 UTC**: Wake up, check if weekday
2. **07:00-10:00 UTC**: Run London session (Finnhub WS with replay failover)
3. **12:30-16:00 UTC**: Run NY session (Finnhub WS with replay failover)
4. **16:05 UTC**: Generate daily PnL snapshot, send Discord alert
5. **Sleep**: Until 06:00 UTC next day

**Features:**
- Automatic WebSocket failover to replay mode on connection errors
- Retry logic with exponential backoff (up to 3 attempts)
- Weekend/holiday detection (Mon-Fri only)
- Graceful shutdown on SIGINT/SIGTERM
- Discord alerts on session start/end/errors
- Daily PnL snapshot with CSV + Markdown reports

**Discord Alerts:**
- 🚀 Session start (London/NY)
- ✅ Session complete with stats
- ⚠️ WebSocket failover warnings
- ❌ Session failure after retries
- 📊 Daily PnL snapshot

### Testing NY Sessions

**Manual NY Session Test:**
```bash
# Edit sessions.yaml to use portfolio_ny profile
python -m axfl.cli live-port --cfg axfl/config/sessions.yaml --mode replay
```

**Demo Replay (Last Session):**
```bash
make demo_replay
# Automatically detects and replays most recent London session
```

### Production Deployment

**Docker/Systemd Service:**
```bash
# Create systemd service
sudo tee /etc/systemd/system/axfl-daily.service > /dev/null <<EOF
[Unit]
Description=AXFL Daily Trading Runner
After=network.target

[Service]
Type=simple
User=trader
WorkingDirectory=/opt/axfl
Environment="FINNHUB_API_KEYS=key1,key2"
Environment="DISCORD_WEBHOOK_URL=https://..."
ExecStart=/opt/axfl/venv/bin/python -m axfl.cli daily-runner
Restart=on-failure
RestartSec=60

[Install]
WantedBy=multi-user.target
EOF

# Enable and start
sudo systemctl enable axfl-daily
sudo systemctl start axfl-daily

# Monitor logs
sudo journalctl -u axfl-daily -f
```

**Environment Variables:**
```bash
export FINNHUB_API_KEYS="key1,key2,key3"
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
export OANDA_API_KEY="your-token"  # Optional for mirroring
export OANDA_ACCOUNT_ID="your-id"
export OANDA_ENV="practice"
```

### Monitoring

**Daily Snapshot Report:**
```bash
# View today's report
cat reports/pnl_$(date +%Y%m%d).md
```

**Discord Notifications:**
All critical events are sent to Discord webhook:
- Session lifecycle events
- Trade executions
- Errors and warnings
- Daily PnL summaries

**Log Files:**
```bash
# Portfolio engine logs
tail -f logs/portfolio_live_$(date +%Y%m%d).jsonl

# Trade logs
tail -f data/trades/trades_$(date +%Y%m%d).csv
```

### Best Practices

1. **Test Both Sessions**: Run demo_replay for both London and NY windows
2. **Monitor First Week**: Watch Discord alerts carefully during initial deployment
3. **Review Daily Snapshots**: Check PnL reports every evening
4. **Backup Trade Logs**: Archive `data/trades/` directory weekly
5. **Update Parameters**: Tune session-specific params based on performance
6. **Check API Limits**: Monitor Finnhub API usage (60 calls/min limit)
7. **Validate Weekends**: Ensure no trading activity on Sat/Sun

### Troubleshooting

**Issue: Daily runner exits early**
- Check if today is a weekday (Mon-Fri)
- Verify system time is UTC
- Review Discord alerts for error messages

**Issue: NY session not starting**
- Confirm `portfolio_ny` profile exists in sessions.yaml
- Check if current time is within 12:30-16:00 UTC window
- Look for DIAG blocks in output

**Issue: WebSocket keeps failing**
- Verify FINNHUB_API_KEYS environment variable
- Check API rate limits (60 calls/min)
- System will auto-fallback to replay mode

**Issue: No Discord alerts**
- Set DISCORD_WEBHOOK_URL environment variable
- Test webhook with curl:
  ```bash
  curl -X POST $DISCORD_WEBHOOK_URL \
    -H "Content-Type: application/json" \
    -d '{"content":"Test message"}'
  ```

```

````

```
