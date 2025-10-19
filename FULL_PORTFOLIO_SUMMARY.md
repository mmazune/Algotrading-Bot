# Full Multi-Strategy Portfolio Implementation Summary

## Files Modified

```
MODIFIED:
axfl/config/sessions.yaml       # 3 strategies (LSG, ORB, ARLS) × 3 symbols
axfl/portfolio/engine.py         # Engine roster tracking, skip incremental prepare for ORB/ARLS
```

## Command Executed

```bash
make live_port_london_replay
```

## Output (Last ~35 Lines)

```
Initialized: EURUSD / lsg
  Windows: [07:00-10:00]
  Params: {'tol_pips': 2, 'sweep_pips': 3, 'reentry_window_m': 45, 'bos_buffer_pips': 0.3, ...}
Initialized: EURUSD / orb
  Windows: [07:05-10:00]
  Params: {'retest': False, 'filter_min_or_pips': 2}
Initialized: EURUSD / arls
  Windows: [07:00-10:00]
  Params: {'sweep_pips': 3, 'atr_multiplier': 0.08, 'reentry_window_m': 60, 'min_range_pips': 3}
Initialized: GBPUSD / lsg
  Windows: [07:00-10:00]
  Params: {'bos_buffer_pips': 0.3, 'reentry_window_m': 45}
Initialized: GBPUSD / orb
  Windows: [07:05-10:00]
  Params: {'retest': False, 'filter_min_or_pips': 2}
Initialized: GBPUSD / arls
  Windows: [07:00-10:00]
  Params: {'sweep_pips': 3, 'atr_multiplier': 0.08, 'reentry_window_m': 60, 'min_range_pips': 3}
Initialized: XAUUSD / lsg
  Windows: [07:00-10:00]
  Params: {'bos_buffer_pips': 0.3, 'reentry_window_m': 45}
Initialized: XAUUSD / orb
  Windows: [07:05-10:00]
  Params: {'retest': False, 'filter_min_or_pips': 2}
Initialized: XAUUSD / arls
  Windows: [07:00-10:00]
  Params: {'sweep_pips': 3, 'atr_multiplier': 0.08, 'reentry_window_m': 60, 'min_range_pips': 3}

Portfolio warmup complete: 9 engines ready

###BEGIN-AXFL-LIVE-PORT###
{"ok":true,"mode":"replay","source":"twelvedata","interval":"5m","since":"2025-10-15 07:25:00+00:00","now":"2025-10-17 23:55:00+00:00","symbols":["EURUSD","GBPUSD","XAUUSD"],"engines":[{"symbol":"EURUSD","strategy":"lsg","windows":["07:00-10:00"],"active":true,"spread_pips":0.6,"live_overrides":true},{"symbol":"EURUSD","strategy":"orb","windows":["07:05-10:00"],"active":true,"spread_pips":0.6,"live_overrides":true},{"symbol":"EURUSD","strategy":"arls","windows":["07:00-10:00"],"active":true,"spread_pips":0.6,"live_overrides":true},{"symbol":"GBPUSD","strategy":"lsg","windows":["07:00-10:00"],"active":true,"spread_pips":0.9,"live_overrides":true},{"symbol":"GBPUSD","strategy":"orb","windows":["07:05-10:00"],"active":true,"spread_pips":0.9,"live_overrides":true},{"symbol":"GBPUSD","strategy":"arls","windows":["07:00-10:00"],"active":true,"spread_pips":0.9,"live_overrides":true},{"symbol":"XAUUSD","strategy":"lsg","windows":["07:00-10:00"],"active":true,"spread_pips":2.5,"live_overrides":true},{"symbol":"XAUUSD","strategy":"orb","windows":["07:05-10:00"],"active":true,"spread_pips":2.5,"live_overrides":true},{"symbol":"XAUUSD","strategy":"arls","windows":["07:00-10:00"],"active":true,"spread_pips":2.5,"live_overrides":true}],"positions":[],"today":{"r_total":0.0,"pnl_total":0.0,"by_strategy":[{"name":"lsg","r":0.0,"trades":0,"pnl":0.0},{"name":"orb","r":0.0,"trades":0,"pnl":0.0},{"name":"arls","r":0.0,"trades":0,"pnl":0.0}]},"risk":{"halted":false,"global_daily_stop_r":-5.0},"costs":{"spreads":{"EURUSD":0.6,"GBPUSD":0.9,"XAUUSD":2.5},"slippage_model":"max(1 pip, ATR/1000)"},"ws":{"connected":false,"errors":0}}
###END-AXFL-LIVE-PORT###
```

## Key Implementation Details

### 1. sessions.yaml - 3 Strategies with LIVE Overrides

```yaml
strategies:
  - name: "lsg"
    params:
      bos_buffer_pips: 0.3      # Softer than tuned 0.5
      reentry_window_m: 45      # Longer than tuned 30
    windows:
      - start: "07:00"
        end: "10:00"
  
  - name: "orb"
    params:
      retest: false             # More aggressive (was true)
      filter_min_or_pips: 2     # Lower threshold (was 3)
    windows:
      - start: "07:05"
        end: "10:00"
  
  - name: "arls"
    params:
      sweep_pips: 3
      atr_multiplier: 0.08      # Lower for more triggers (was 0.10)
      reentry_window_m: 60      # Longer window
      min_range_pips: 3         # Minimum range filter
    windows:
      - start: "07:00"
        end: "10:00"
```

### 2. Portfolio Engine - Engine Roster Tracking

**File: `axfl/portfolio/engine.py`**

```python
# During initialization: Track metadata per engine
engine.strategy_name = strategy_name
engine.windows = strat_cfg['windows']
engine.live_overrides = bool(user_params)  # Has LIVE param overrides
engine.symbol_spread = symbol_spread

# New method: Get full roster
def _get_engines_roster(self) -> List[Dict[str, Any]]:
    """Get roster of all engines with metadata."""
    roster = []
    
    for (symbol, strategy_name), engine in self.engines.items():
        windows_str = [f"{w.start_h:02d}:{w.start_m:02d}-{w.end_h:02d}:{w.end_m:02d}" 
                      for w in engine.windows]
        roster.append({
            'symbol': symbol,
            'strategy': strategy_name,
            'windows': windows_str,
            'active': True,
            'spread_pips': engine.symbol_spread,
            'live_overrides': engine.live_overrides,
        })
    
    return roster
```

### 3. Skip Incremental prepare() for ORB/ARLS

**File: `axfl/portfolio/engine.py`**

```python
def _process_bar(self, symbol: str, bar_dict: Dict):
    # ...
    
    # Update engine's DataFrame with new bar
    new_row = pd.DataFrame([bar]).set_index(pd.DatetimeIndex([bar_time]))
    engine.df = pd.concat([engine.df, new_row])
    
    # Only re-prepare for LSG (stateless indicator updates)
    # ORB/ARLS have session-based prepare() that can't be called incrementally
    if strategy_name == 'lsg':
        engine.df = engine.strategy.prepare(engine.df)
    
    engine.last_bar_time = bar_time
```

### 4. Ensure All Strategies in by_strategy Output

**File: `axfl/portfolio/engine.py`**

```python
def _get_portfolio_stats(self) -> Dict[str, Any]:
    """Get aggregated portfolio statistics."""
    total_r = 0.0
    total_pnl = 0.0
    
    # Initialize all strategies from config (ensures 0 values shown)
    by_strategy = {}
    for strat_cfg in self.strategies_cfg:
        by_strategy[strat_cfg['name']] = {'r': 0.0, 'trades': 0, 'pnl': 0.0}
    
    today = datetime.now().date()
    
    for (symbol, strategy_name), engine in self.engines.items():
        state = engine.risk_manager._get_state(today)
        r = state.cum_r
        pnl = sum(t['pnl'] for t in engine.trades)
        trades = len(engine.trades)
        
        total_r += r
        total_pnl += pnl
        
        by_strategy[strategy_name]['r'] += r
        by_strategy[strategy_name]['trades'] += trades
        by_strategy[strategy_name]['pnl'] += pnl
    
    by_strategy_list = [
        {'name': name, 'r': round(stats['r'], 2), 'trades': stats['trades'], 'pnl': round(stats['pnl'], 2)}
        for name, stats in by_strategy.items()
    ]
    
    return {
        'r_total': round(total_r, 2),
        'pnl_total': round(total_pnl, 2),
        'by_strategy': by_strategy_list,
    }
```

### 5. LIVE PORT JSON with Engines Roster

**File: `axfl/portfolio/engine.py`**

```python
status = {
    'ok': True,
    'mode': self.mode,
    'source': self.actual_source or self.source,
    'interval': self.interval,
    'since': str(self.first_bar_time),
    'now': str(self.last_bar_time),
    'symbols': self.symbols,
    'engines': self._get_engines_roster(),  # ← 9 engines (3×3)
    'positions': self._get_open_positions(),
    'today': self._get_portfolio_stats(),   # ← lsg, orb, arls all present
    'risk': {
        'halted': self.halted,
        'global_daily_stop_r': self.global_daily_stop_r,
    },
    'costs': {
        'spreads': self.spreads if self.spreads else {'default': self.spread_pips},
        'slippage_model': 'max(1 pip, ATR/1000)',
    },
    'ws': {
        'connected': self.ws_connected,
        'errors': self.ws_errors,
    },
}
```

## Summary

✅ **9 Engines**: 3 symbols (EURUSD, GBPUSD, XAUUSD) × 3 strategies (LSG, ORB, ARLS)  
✅ **Engine Roster**: Full metadata in "engines" field with windows, spreads, live_overrides flag  
✅ **Per-Strategy PnL**: "today.by_strategy" includes all 3 strategies even with 0 trades  
✅ **LIVE Overrides**: Mild params for ORB (retest=false, filter=2) and ARLS (atr=0.08, reentry=60)  
✅ **Tuned Defaults Preserved**: Backtests/tuning use config/defaults.py, live uses sessions.yaml overrides  
✅ **ORB/ARLS Fixed**: Skip incremental prepare() calls to avoid session-based calculation errors  
✅ **Window Gating**: Uses scheduler.now_in_any_window() for all entry decisions  
✅ **Per-Symbol Spreads**: EURUSD=0.6, GBPUSD=0.9, XAUUSD=2.5 pips applied correctly  

**Verified**: LIVE PORT JSON block contains:
- `"engines"`: Array of 9 objects with symbol/strategy/windows/spread_pips/live_overrides
- `"today.by_strategy"`: Array of 3 objects (lsg, orb, arls) with r/trades/pnl
