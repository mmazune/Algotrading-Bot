# Profile-Aware Configuration - Quick Reference

## CLI Commands with Profile Support

All live trading commands now support `--profile` option:

```bash
# Use default profile (portfolio)
python -m axfl.cli live-oanda --cfg config.yaml --mode ws

# Use NY session profile
python -m axfl.cli live-oanda --cfg config.yaml --mode ws --profile portfolio_ny

# Daily runner with custom profile
python -m axfl.cli daily-runner --cfg config.yaml --profile portfolio_ny

# Health check for specific profile
python -m axfl.cli health --cfg config.yaml --profile portfolio
```

---

## YAML Structure

```yaml
# London Session Profile
portfolio:
  symbols: ["EURUSD", "GBPUSD", "XAUUSD"]
  interval: "5m"
  source: "finnhub"
  venue: "OANDA"
  spreads:
    EURUSD: 0.6
  risk:
    global_daily_stop_r: -5.0

# London Session Strategies
strategies:
  - name: "lsg"
    params:
      bos_buffer_pips: 0.3
    windows:
      - start: "07:00"
        end: "10:00"

# NY Session Profile
portfolio_ny:
  symbols: ["EURUSD", "GBPUSD", "XAUUSD"]
  interval: "5m"
  source: "finnhub"
  venue: "OANDA"
  spreads:
    EURUSD: 0.6
  risk:
    global_daily_stop_r: -5.0

# NY Session Strategies
strategies_ny:
  - name: "lsg"
    params:
      bos_buffer_pips: 0.5
    windows:
      - start: "12:30"
        end: "16:00"
```

---

## Python API

### Load and Normalize Config
```python
from axfl.portfolio.scheduler import load_sessions_yaml, normalize_schedule, pick_profile

# Load YAML
cfg = load_sessions_yaml('axfl/config/sessions.yaml')

# Pick specific profile
profile_cfg = pick_profile(cfg, 'portfolio_ny')

# Normalize for engine
schedule = normalize_schedule(cfg, profile='portfolio_ny')
```

---

### Safe Broker Auth
```python
from axfl.brokers.oanda import OandaPractice

broker = OandaPractice()

# Check auth first
auth = broker.ping_auth()
if not auth['ok']:
    print(f"Auth failed: {auth['error']}")
    exit(1)

# Get account info safely
account = broker.get_account()
if account['ok']:
    print(f"Account: {account['id']}")
    print(f"Balance: ${account['balance']:,.2f} {account['currency']}")
else:
    print(f"Error: {account['error']}")
```

---

## Makefile Targets

```bash
# Test broker authentication
make broker_test

# Test profile loading (London session)
make live_port_profile_replay

# Test reconciliation
make recon

# Health check
make health
```

---

## Profile Selection Logic

1. **Explicit Profile**: Use specified profile name if provided
2. **Default Profile**: Fall back to `'portfolio'` if not specified
3. **Auto-Detect**: Use first available profile if default not found
4. **Validation**: Raise `ValueError` if no valid profile exists

---

## Error Handling

### Config Load Failure
```bash
$ python -m axfl.cli live-port --cfg bad.yaml --profile test
Error loading config: Schedule missing required key: 'strategies'

###BEGIN-AXFL-DIAG###
{"reason":"config_load_failed","cfg":"bad.yaml","profile":"test","error":"..."}
###END-AXFL-DIAG###
```

### Missing Required Keys
```bash
$ python -m axfl.cli live-oanda --cfg incomplete.yaml --profile test
✗ DIAG: Profile 'test' has no 'strategies' defined
```

---

## Backward Compatibility

Legacy imports still work via compatibility shim:

```python
# Old import path
from axfl.core.sessions import normalize_schedule, pick_profile

# Maps to axfl.portfolio.scheduler functions
```

---

## Testing

```bash
# Validate profile loading
python -m axfl.cli health --cfg axfl/config/sessions.yaml --profile portfolio
python -m axfl.cli health --cfg axfl/config/sessions.yaml --profile portfolio_ny

# Validate broker auth
python -m axfl.cli broker-test --mirror oanda --symbol EURUSD --risk_perc 0.001

# Validate reconciliation
python -m axfl.cli reconcile
```

---

**See Also**: [SURGICAL_FIXES_SUMMARY.md](./SURGICAL_FIXES_SUMMARY.md) for full implementation details.
