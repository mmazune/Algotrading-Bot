# NY Session Pack - Quick Reference

## Commands

### Daily Runner (Production)
```bash
# Start automated daily runner
make daily_runner

# Or with custom config
python -m axfl.cli daily-runner --cfg axfl/config/sessions.yaml
```

### Manual Session Testing

**London Session:**
```bash
python -m axfl.cli live-port --cfg axfl/config/sessions.yaml --mode replay
```

**NY Session (requires config edit):**
```yaml
# Temporarily rename portfolio_ny → portfolio in sessions.yaml
python -m axfl.cli live-port --cfg axfl/config/sessions.yaml --mode replay
```

## Session Windows

| Session | Time (UTC) | Opening Range | Markets |
|---------|-----------|---------------|---------|
| **London** | 07:00-10:00 | 07:00 | European open |
| **New York** | 12:30-16:00 | 12:30 | US market open |

## Daily Runner Schedule

```
06:00 UTC  Wake up, check if weekday
07:00 UTC  Start London session (Finnhub WS → replay failover)
10:00 UTC  London session ends
12:30 UTC  Start NY session (Finnhub WS → replay failover)
16:00 UTC  NY session ends
16:05 UTC  Generate daily PnL snapshot + Discord alert
SLEEP      Until 06:00 UTC next day
```

## Configuration Profiles

### London (Default)
```yaml
portfolio:
  symbols: ["EURUSD", "GBPUSD", "XAUUSD"]
  strategies:
    - name: "lsg"
      windows: [{start: "07:00", end: "10:00"}]
    - name: "orb"
      windows: [{start: "07:05", end: "10:00"}]
```

### NY (Extended)
```yaml
portfolio_ny:
  symbols: ["EURUSD", "GBPUSD", "XAUUSD"]
  strategies:
    - name: "lsg"
      params: {bos_buffer_pips: 0.5, tol_pips: 2.5}
      windows: [{start: "12:30", end: "16:00"}]
    - name: "orb"
      params: {session: "ny", thr_break_pips: 4, filter_min_or_pips: 5}
      windows: [{start: "12:30", end: "16:00"}]
```

## Parameter Differences

| Strategy | Parameter | London | NY | Why? |
|----------|-----------|--------|----|----|
| **LSG** | bos_buffer_pips | 0.3 | 0.5 | Wider NY ranges |
| | tol_pips | 2.0 | 2.5 | Higher volatility |
| | sweep_pips | 3 | 4 | Larger sweeps |
| **ORB** | thr_break_pips | 3 | 4 | Wider breakouts |
| | filter_min_or_pips | 4 | 5 | Larger OR |
| | session | london | ny | Opening range time |
| **ARLS** | sweep_pips | 3 | 4 | Wider liquidity |
| | atr_multiplier | 0.08 | 0.1 | Higher volatility |

## Discord Alerts

Set webhook URL:
```bash
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN"
```

**Alert Types:**
- 🚀 Session start (London/NY)
- ✅ Session complete + stats
- ⚠️ WebSocket failover
- ❌ Session failure
- 📊 Daily PnL snapshot

## Environment Variables

### Required
```bash
export FINNHUB_API_KEYS="key1,key2,key3"
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
```

### Optional (for OANDA mirroring)
```bash
export OANDA_API_KEY="your-token"
export OANDA_ACCOUNT_ID="your-account-id"
export OANDA_ENV="practice"  # or "live"
```

## Systemd Service (Production)

**Create service:**
```bash
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
```

**Enable and start:**
```bash
sudo systemctl enable axfl-daily
sudo systemctl start axfl-daily
```

**Monitor logs:**
```bash
sudo journalctl -u axfl-daily -f
```

## Monitoring

### Check Health
```bash
make health
```

### View Daily Report
```bash
cat reports/pnl_$(date +%Y%m%d).md
```

### Watch Live Logs
```bash
tail -f logs/portfolio_live_$(date +%Y%m%d).jsonl
```

### View Trades
```bash
cat data/trades/trades_$(date +%Y%m%d).csv
```

## Troubleshooting

### Runner exits immediately
**Cause**: Weekend (Sat/Sun)  
**Action**: Normal - check again on Monday

### NY session not starting
**Cause**: Missing `portfolio_ny` in config  
**Action**: Verify sessions.yaml has both profiles

### WebSocket keeps failing
**Cause**: API rate limits  
**Action**: System auto-falls back to replay

### No Discord alerts
**Cause**: DISCORD_WEBHOOK_URL not set  
**Action**: Export environment variable

### Wrong OR time for NY
**Cause**: Missing `session: "ny"` in ORB params  
**Action**: Add to portfolio_ny → strategies → orb → params

## Testing Checklist

- [ ] Run `make health` - verify config loads
- [ ] Test London session in replay mode
- [ ] Test NY session separately (edit config)
- [ ] Send test Discord message
- [ ] Run `make demo_replay` to validate
- [ ] Start daily runner and monitor first day
- [ ] Check Discord alerts arrive correctly
- [ ] Verify daily PnL snapshot at 16:05 UTC
- [ ] Review trade logs for accuracy
- [ ] Confirm weekend detection works

## Safety Notes

⚠️ **Weekend Trading**: System automatically skips Sat/Sun  
⚠️ **Rate Limits**: Finnhub has 60 calls/min limit  
⚠️ **Failover**: WS → Replay automatic, max 3 retries  
⚠️ **Time Zone**: All times UTC, ensure system clock correct  
⚠️ **First Week**: Monitor Discord alerts closely  

## Performance Tips

✅ Use multiple Finnhub API keys for rotation  
✅ Set status_every_s to 90 for NY (less noise)  
✅ Archive trade logs weekly  
✅ Review daily snapshots for parameter tuning  
✅ Start with practice OANDA account  

---

**Status**: Production Ready 🚀  
**Version**: 1.0  
**Last Updated**: October 20, 2025
