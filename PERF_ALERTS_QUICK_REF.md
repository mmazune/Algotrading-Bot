# Performance Alerts - Quick Reference

## 🚀 Quick Start

### 1. Set Environment Variables
```bash
export DISCORD_WEBHOOK_URL_FILE=/path/to/webhook.txt
export OANDA_ENV=practice  # or "live"
export AXFL_DB=/opt/axfl/app/data/axfl.db  # optional
```

### 2. Create Webhook File
```bash
echo "https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN" > /opt/axfl/secrets/discord_webhook.txt
export DISCORD_WEBHOOK_URL_FILE=/opt/axfl/secrets/discord_webhook.txt
```

### 3. Run Your Bot
The hooks are automatically called when trades open/close via broker mirroring.

---

## 📋 What You Get

### Every Trade Open
- ✅ Discord notification with all details (instrument, side, units, entry, SL/TP, spread, strategy, account)
- ✅ SQLite record in `trades` table

### Every Trade Close
- ✅ Discord notification with PnL (pips & money), entry→exit prices
- ✅ SQLite record updated with exit, pips, money

### Scheduled Reports (Daily/Weekly/Monthly)
- ✅ Totals: #trades, win%, pips, money, best, worst, avg
- ✅ Per-strategy ranking sorted by money PnL

---

## 🗓️ Alert Schedule

| Period  | Time         | Example     |
|---------|--------------|-------------|
| Daily   | 23:59 UTC    | Every day   |
| Weekly  | Sun 23:59    | Every Sunday|
| Monthly | Last 23:59   | Nov 30, Dec 31, etc. |

*5-minute window for delivery (23:59-00:04)*

---

## 🔍 Verify Installation

```bash
# Test imports
python -c "import axfl.notify.trades, axfl.metrics.perf, axfl.hooks; print('✅ OK')"

# Check database
sqlite3 $AXFL_DB "SELECT COUNT(*) FROM trades;"

# Check state file
cat /opt/axfl/app/reports/.perf_state.json
```

---

## 🗄️ Database Queries

```bash
# View all trades
sqlite3 $AXFL_DB "SELECT * FROM trades ORDER BY opened_at DESC LIMIT 10;"

# Today's trades
sqlite3 $AXFL_DB "SELECT * FROM trades WHERE date(opened_at) = date('now');"

# Strategy performance
sqlite3 $AXFL_DB "
SELECT strategy, COUNT(*) trades, SUM(money) pnl, AVG(money) avg
FROM trades WHERE closed_at IS NOT NULL
GROUP BY strategy ORDER BY pnl DESC;
"

# Win rate by strategy
sqlite3 $AXFL_DB "
SELECT strategy,
  COUNT(*) total,
  SUM(CASE WHEN money > 0 THEN 1 ELSE 0 END) wins,
  ROUND(100.0 * SUM(CASE WHEN money > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) win_rate
FROM trades WHERE closed_at IS NOT NULL
GROUP BY strategy;
"
```

---

## 🐛 Troubleshooting

### No Discord Notifications
1. Check env var: `echo $DISCORD_WEBHOOK_URL_FILE`
2. Check file contents: `cat $DISCORD_WEBHOOK_URL_FILE`
3. Test webhook manually: `curl -X POST -H "Content-Type: application/json" -d '{"content":"test"}' $(cat $DISCORD_WEBHOOK_URL_FILE)`

### No Database Records
1. Check DB path: `echo $AXFL_DB`
2. Check directory exists: `ls -la $(dirname $AXFL_DB)`
3. Check table exists: `sqlite3 $AXFL_DB ".tables"`

### No Performance Alerts
1. Check state file: `cat /opt/axfl/app/reports/.perf_state.json`
2. Check time: `date -u` (must be within 5 min of trigger time)
3. Check logs for "PERF_ALERT_ERROR"

---

## 📊 Performance Report Example

```
🔵 DAILY PERFORMANCE
Period: daily
Trades: 12
Win Rate: 66.7%
Pips: 38.5
Money: 385.00
Best: 125.00
Worst: -45.00
Avg: 32.08

#1 lsg
Trades 7 • Win 71.4% • PnL 245.00 • Pips 24.5 • Avg 35.00

#2 breaker
Trades 3 • Win 66.7% • PnL 98.00 • Pips 9.8 • Avg 32.67

#3 orb
Trades 2 • Win 50.0% • PnL 42.00 • Pips 4.2 • Avg 21.00
```

---

## 🔐 Security Notes

- Store webhook URL in a file, not in code
- Set file permissions: `chmod 600 /opt/axfl/secrets/discord_webhook.txt`
- Never commit webhook URL to git
- Rotate webhook if compromised

---

## 📝 File Locations

| File/Dir                                | Purpose                          |
|-----------------------------------------|----------------------------------|
| `/opt/axfl/app/data/axfl.db`            | SQLite trade database            |
| `/opt/axfl/app/reports/.perf_state.json`| Alert delivery tracking          |
| `/opt/axfl/secrets/discord_webhook.txt` | Discord webhook URL              |
| `axfl/notify/trades.py`                 | Notification functions           |
| `axfl/metrics/perf.py`                  | DB & performance computation     |
| `axfl/hooks.py`                         | Trade lifecycle hooks            |

---

## 🎯 Key Features

✅ **Zero Dependencies** - stdlib only  
✅ **Idempotent** - safe to restart anytime  
✅ **Production-Safe** - errors don't crash engine  
✅ **Automatic** - no manual intervention  
✅ **Rich Data** - all trade details captured  
✅ **Scheduled** - daily/weekly/monthly reports  

---

**Need Help?** Check `PERF_ALERTS_IMPLEMENTATION.md` for full details.
