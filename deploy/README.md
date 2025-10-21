# AXFL Systemd Service Deployment

## Overview

This directory contains production-ready systemd service files for running AXFL Daily Runner as a persistent background service that starts automatically at boot.

## Files

- **axfl-daily-runner.service** - Systemd unit file
- **axfl.env.sample** - Environment variable template

## Installation

### 1. Install the Service

```bash
make service_install
```

This will:
- Create `/etc/axfl/` directory
- Copy `axfl.env.sample` to `/etc/axfl/axfl.env`
- Set secure permissions (600, root-owned)
- Install systemd service as `axfl-daily-runner@USERNAME.service`
- Enable service to start at boot
- Start the service immediately

### 2. Configure Secrets

Edit the environment file with your real credentials:

```bash
sudo nano /etc/axfl/axfl.env
```

Update these values:
```bash
OANDA_API_KEY=your_actual_oanda_practice_token
OANDA_ACCOUNT_ID=your_actual_oanda_practice_account_id
OANDA_ENV=practice
FINNHUB_API_KEYS=key1,key2,key3
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

### 3. Restart the Service

After updating credentials:

```bash
sudo systemctl restart axfl-daily-runner@$(USER).service
```

## Management

### Check Status

```bash
make service_status
# or
sudo systemctl status axfl-daily-runner@$(USER).service
```

### View Logs

```bash
make service_logs
# or
journalctl -u axfl-daily-runner@$(USER).service -n 200 -f
```

### Stop Service

```bash
sudo systemctl stop axfl-daily-runner@$(USER).service
```

### Disable Auto-start

```bash
sudo systemctl disable axfl-daily-runner@$(USER).service
```

### Uninstall

```bash
sudo systemctl stop axfl-daily-runner@$(USER).service
sudo systemctl disable axfl-daily-runner@$(USER).service
sudo rm /etc/systemd/system/axfl-daily-runner@$(USER).service
sudo systemctl daemon-reload
# Optional: remove config
sudo rm -rf /etc/axfl
```

## Service Features

- **Auto-restart**: Service restarts automatically on failure (10s delay)
- **Boot persistence**: Starts automatically when system boots
- **Log management**: All output captured in systemd journal
- **Security**: Runs as non-root user with NoNewPrivileges flag
- **Environment isolation**: Secrets stored in `/etc/axfl/axfl.env` (600 permissions)

## Architecture

```
┌─────────────────────────────────────────┐
│  systemd (pid 1)                        │
│  ┌────────────────────────────────────┐ │
│  │ axfl-daily-runner@USER.service     │ │
│  │  ├─ WorkingDirectory: ~/Algo...    │ │
│  │  ├─ EnvironmentFile: /etc/axfl/... │ │
│  │  └─ ExecStart: scripts/run_daily...│ │
│  └────────────────────────────────────┘ │
└─────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────┐
│  scripts/run_daily_runner.sh            │
│  ├─ Load /etc/axfl/axfl.env             │
│  ├─ Activate .venv if present           │
│  ├─ Verify OANDA credentials            │
│  └─ Launch: python -m axfl.cli daily... │
└─────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────┐
│  AXFL Daily Runner                      │
│  ├─ London session: 07:00-10:00 UTC     │
│  ├─ NY session: 12:30-16:00 UTC         │
│  ├─ WebSocket data + replay failover    │
│  ├─ Discord alerts                      │
│  └─ Daily PnL snapshot @ 16:05 UTC      │
└─────────────────────────────────────────┘
```

## Troubleshooting

### Service won't start

```bash
# Check service status
sudo systemctl status axfl-daily-runner@$(USER).service

# Check logs
journalctl -u axfl-daily-runner@$(USER).service -n 100 --no-pager

# Verify environment file
sudo cat /etc/axfl/axfl.env

# Test script manually
cd ~/Algotrading-Bot
./scripts/run_daily_runner.sh
```

### Missing dependencies

```bash
# Ensure Python packages installed
cd ~/Algotrading-Bot
make setup
```

### Permissions issues

```bash
# Verify ownership
ls -la ~/Algotrading-Bot/scripts/run_daily_runner.sh

# Ensure executable
chmod +x ~/Algotrading-Bot/scripts/run_daily_runner.sh
```

## Production Checklist

- [ ] Repository cloned to `/home/USERNAME/Algotrading-Bot`
- [ ] Python dependencies installed (`make setup`)
- [ ] Environment file configured at `/etc/axfl/axfl.env`
- [ ] OANDA credentials valid (test with `make broker_test`)
- [ ] Finnhub keys configured
- [ ] Discord webhook configured (optional)
- [ ] Service installed (`make service_install`)
- [ ] Service enabled (`sudo systemctl enable axfl-daily-runner@USER`)
- [ ] Service running (`sudo systemctl status axfl-daily-runner@USER`)
- [ ] Logs streaming correctly (`make service_logs`)

## Security Notes

1. **Secrets**: `/etc/axfl/axfl.env` is owned by root with 600 permissions
2. **User**: Service runs as your user account (not root)
3. **NoNewPrivileges**: Prevents privilege escalation
4. **Network**: Service waits for network to be online before starting

## Monitoring

The service logs to systemd journal. Monitor with:

```bash
# Tail logs in real-time
journalctl -u axfl-daily-runner@$(USER).service -f

# Search for errors
journalctl -u axfl-daily-runner@$(USER).service | grep -i error

# Show logs from last boot
journalctl -u axfl-daily-runner@$(USER).service -b
```

## See Also

- [SURGICAL_FIXES_SUMMARY.md](../SURGICAL_FIXES_SUMMARY.md) - Profile system
- [GO_LIVE_V2_SUMMARY.md](../GO_LIVE_V2_SUMMARY.md) - Live trading guide
- [QUICK_REFERENCE.md](../QUICK_REFERENCE.md) - Command reference
