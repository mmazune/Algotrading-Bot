# Portfolio Live Trading Implementation Summary

## Files Created/Modified

```
NEW:
axfl/portfolio/__init__.py          # Portfolio package exports
axfl/portfolio/scheduler.py         # SessionWindow, now_in_any_window(), load/normalize config
axfl/portfolio/engine.py             # PortfolioEngine (multi-strategy, multi-symbol orchestrator)
axfl/config/sessions.yaml            # Default London session schedule

MODIFIED:
axfl/cli.py                          # Added 'live-port' command
Makefile                             # Added live_port_replay, live_port_ws targets
```

## Command & Execution

```bash
make live_port_replay
```

Equivalent to:
```bash
python -m axfl.cli live-port --cfg axfl/config/sessions.yaml --mode replay --source auto
```

## Output (Last 30 Lines)

```
###BEGIN-AXFL-LIVE-PORT###
{"ok":true,"mode":"replay","source":"twelvedata","interval":"5m","since":"2025-10-15 07:25:00+00:00","now":"2025-10-17 18:25:00+00:00","symbols":["EURUSD"],"positions":[],"today":{"r_total":0.0,"pnl_total":0.0,"by_strategy":[{"name":"lsg","r":0.0,"trades":0,"pnl":0.0}]},"risk":{"halted":false,"global_daily_stop_r":-5.0},"costs":{"spread_pips":0.6,"slippage_model":"max(1 pip, ATR/1000)"},"ws":{"connected":false,"errors":0}}
###END-AXFL-LIVE-PORT###


###BEGIN-AXFL-LIVE-PORT###
{"ok":true,"mode":"replay","source":"twelvedata","interval":"5m","since":"2025-10-15 07:25:00+00:00","now":"2025-10-17 21:35:00+00:00","symbols":["EURUSD"],"positions":[],"today":{"r_total":0.0,"pnl_total":0.0,"by_strategy":[{"name":"lsg","r":0.0,"trades":0,"pnl":0.0}]},"risk":{"halted":false,"global_daily_stop_r":-5.0},"costs":{"spread_pips":0.6,"slippage_model":"max(1 pip, ATR/1000)"},"ws":{"connected":false,"errors":0}}
###END-AXFL-LIVE-PORT###


###BEGIN-AXFL-LIVE-PORT###
{"ok":true,"mode":"replay","source":"twelvedata","interval":"5m","since":"2025-10-15 07:25:00+00:00","now":"2025-10-18 00:40:00+00:00","symbols":["EURUSD"],"positions":[],"today":{"r_total":0.0,"pnl_total":0.0,"by_strategy":[{"name":"lsg","r":0.0,"trades":0,"pnl":0.0}]},"risk":{"halted":false,"global_daily_stop_r":-5.0},"costs":{"spread_pips":0.6,"slippage_model":"max(1 pip, ATR/1000)"},"ws":{"connected":false,"errors":0}}
###END-AXFL-LIVE-PORT###


###BEGIN-AXFL-LIVE-PORT###
{"ok":true,"mode":"replay","source":"twelvedata","interval":"5m","since":"2025-10-15 07:25:00+00:00","now":"2025-10-18 03:45:00+00:00","symbols":["EURUSD"],"positions":[],"today":{"r_total":0.0,"pnl_total":0.0,"by_strategy":[{"name":"lsg","r":0.0,"trades":0,"pnl":0.0}]},"risk":{"halted":false,"global_daily_stop_r":-5.0},"costs":{"spread_pips":0.6,"slippage_model":"max(1 pip, ATR/1000)"},"ws":{"connected":false,"errors":0}}
###END-AXFL-LIVE-PORT###


###BEGIN-AXFL-LIVE-PORT###
{"ok":true,"mode":"replay","source":"twelvedata","interval":"5m","since":"2025-10-15 07:25:00+00:00","now":"2025-10-18 06:45:00+00:00","symbols":["EURUSD"],"positions":[],"today":{"r_total":0.0,"pnl_total":0.0,"by_strategy":[{"name":"lsg","r":0.0,"trades":0,"pnl":0.0}]},"risk":{"halted":false,"global_daily_stop_r":-5.0},"costs":{"spread_pips":0.6,"slippage_model":"max(1 pip, ATR/1000)"},"ws":{"connected":false,"errors":0}}
###END-AXFL-LIVE-PORT###


###BEGIN-AXFL-LIVE-PORT###
{"ok":true,"mode":"replay","source":"twelvedata","interval":"5m","since":"2025-10-15 07:25:00+00:00","now":"2025-10-18 08:35:00+00:00","symbols":["EURUSD"],"positions":[],"today":{"r_total":0.0,"pnl_total":0.0,"by_strategy":[{"name":"lsg","r":0.0,"trades":0,"pnl":0.0}]},"risk":{"halted":false,"global_daily_stop_r":-5.0},"costs":{"spread_pips":0.6,"slippage_model":"max(1 pip, ATR/1000)"},"ws":{"connected":false,"errors":0}}
###END-AXFL-LIVE-PORT###


Replay complete. Portfolio stats:
  Total R: 0.0
  Total PnL: $0.0
    lsg: 0.0R, 0 trades
```

## Key Diff Patches

### 1. Portfolio Engine - Window Gating Logic

**File: `axfl/portfolio/engine.py` (lines 190-275)**

```python
def _process_bar(self, symbol: str, bar_dict: Dict):
    """Process a completed 5m bar for a symbol across all its strategies."""
    bar_time = bar_dict['time']
    self.last_bar_time = bar_time
    self.last_tick_time = bar_time
    
    # Get current UTC time for window checks (ensure UTC timezone)
    if bar_time.tz is None:
        ts_utc = pd.Timestamp(bar_time, tz='UTC')
    else:
        ts_utc = bar_time.tz_convert('UTC') if bar_time.tz != 'UTC' else bar_time
    
    # Count open positions for this symbol
    open_positions = sum(
        1 for (sym, _), engine in self.engines.items()
        if sym == symbol and engine.position is not None
    )
    
    # Process each strategy for this symbol
    for strat_cfg in self.strategies_cfg:
        strategy_name = strat_cfg['name']
        windows = strat_cfg['windows']  # List of SessionWindow objects
        key = (symbol, strategy_name)
        engine = self.engines.get(key)
        
        if engine is None:
            continue
        
        # Update engine's DataFrame with new bar
        bar = pd.Series({
            'Open': bar_dict['Open'],
            'High': bar_dict['High'],
            'Low': bar_dict['Low'],
            'Close': bar_dict['Close'],
            'Volume': bar_dict.get('Volume', 0),
        }, name=bar_time)
        
        new_row = pd.DataFrame([bar]).set_index(pd.DatetimeIndex([bar_time]))
        engine.df = pd.concat([engine.df, new_row])
        engine.df = engine.strategy.prepare(engine.df)
        engine.last_bar_time = bar_time
        
        # ===== WINDOW GATING =====
        # Check if current UTC time is inside any session window for this strategy
        in_window = now_in_any_window(ts_utc, windows)
        
        # Handle existing position
        if engine.position is not None:
            # Always check SL/TP
            pos = engine.position
            side = pos['side']
            sl = pos['sl']
            tp = pos['tp']
            
            if side == 'long':
                if bar_dict['Low'] <= sl:
                    engine._close_position(bar, bar_time, 'SL', sl)
                elif bar_dict['High'] >= tp:
                    engine._close_position(bar, bar_time, 'TP', tp)
            else:  # short
                if bar_dict['High'] >= sl:
                    engine._close_position(bar, bar_time, 'SL', sl)
                elif bar_dict['Low'] <= tp:
                    engine._close_position(bar, bar_time, 'TP', tp)
            
            # If outside window, close position (time stop)
            if not in_window and engine.position is not None:
                print(f"[{bar_time}] {symbol}/{strategy_name}: Outside window, closing position (time stop)")
                engine._close_position(bar, bar_time, 'TIME', engine.position['entry'])
            
            continue  # Don't generate new signals if in position
        
        # ===== ENTRY GATING =====
        # Check if we can open new positions
        today = bar_time.date()
        can_trade = (
            in_window and                          # Inside session window
            not self.halted and                    # Portfolio not halted
            engine.risk_manager.can_open(today) and # Strategy risk OK
            open_positions < self.max_open_positions # Position limit not hit
        )
        
        if not can_trade:
            continue
        
        # Generate signals
        i = len(engine.df) - 1
        row = engine.df.iloc[i]
        signals = engine.strategy.generate_signals(i, row, engine.strategy_state)
        
        for signal in signals:
            if signal['action'] == 'open' and engine.position is None:
                engine._open_position(signal, bar, bar_time)
                open_positions += 1
                break  # One position per bar
```

### 2. Portfolio Engine - Portfolio Risk Aggregation

**File: `axfl/portfolio/engine.py` (lines 277-294)**

```python
def _check_global_risk(self):
    """Check portfolio-level risk limits."""
    if self.halted:
        return
    
    # ===== PORTFOLIO RISK AGGREGATION =====
    # Sum today's R across all engines
    today = datetime.now().date()
    total_r = sum(
        engine.risk_manager._get_state(today).cum_r
        for engine in self.engines.values()
    )
    
    # Check global daily stop
    if total_r <= self.global_daily_stop_r:
        self.halted = True
        print(f"\n⚠️  PORTFOLIO HALTED: Global daily stop hit ({total_r:.2f}R <= {self.global_daily_stop_r}R)")

def _get_portfolio_stats(self) -> Dict[str, Any]:
    """Get aggregated portfolio statistics."""
    total_r = 0.0
    total_pnl = 0.0
    by_strategy = {}
    
    today = datetime.now().date()
    
    # ===== AGGREGATE ACROSS ALL ENGINES =====
    for (symbol, strategy_name), engine in self.engines.items():
        state = engine.risk_manager._get_state(today)
        r = state.cum_r
        pnl = sum(t['pnl'] for t in engine.trades)
        trades = len(engine.trades)
        
        total_r += r
        total_pnl += pnl
        
        if strategy_name not in by_strategy:
            by_strategy[strategy_name] = {'r': 0.0, 'trades': 0, 'pnl': 0.0}
        
        by_strategy[strategy_name]['r'] += r
        by_strategy[strategy_name]['trades'] += trades
        by_strategy[strategy_name]['pnl'] += pnl
    
    by_strategy_list = [
        {'name': name, **stats}
        for name, stats in by_strategy.items()
    ]
    
    return {
        'r_total': round(total_r, 2),
        'pnl_total': round(total_pnl, 2),
        'by_strategy': by_strategy_list,
    }
```

### 3. Portfolio Engine - LIVE PORT JSON Output

**File: `axfl/portfolio/engine.py` (lines 336-372)**

```python
def _print_status(self):
    """Print unified AXFL LIVE PORT status block."""
    now = datetime.now(tz=pd.Timestamp.now(tz='UTC').tz)
    
    # ===== BUILD UNIFIED STATUS BLOCK =====
    status = {
        'ok': True,
        'mode': self.mode,
        'source': self.actual_source or self.source,
        'interval': self.interval,
        'since': str(self.first_bar_time),
        'now': str(self.last_bar_time),
        'symbols': self.symbols,
        'positions': self._get_open_positions(),  # All open positions across strategies
        'today': self._get_portfolio_stats(),     # Aggregated portfolio stats
        'risk': {
            'halted': self.halted,
            'global_daily_stop_r': self.global_daily_stop_r,
        },
        'costs': {
            'spread_pips': self.spread_pips,
            'slippage_model': 'max(1 pip, ATR/1000)',
        },
        'ws': {
            'connected': self.ws_connected,
            'errors': self.ws_errors,
        },
    }
    
    # ===== PRINT SINGLE-LINE JSON BLOCK =====
    status_json = json.dumps(status, separators=(',', ':'))
    print("\n###BEGIN-AXFL-LIVE-PORT###")
    print(status_json)
    print("###END-AXFL-LIVE-PORT###\n")
    
    # Log to file
    log_file = self.logs_dir / f"portfolio_live_{datetime.now().strftime('%Y%m%d')}.jsonl"
    with open(log_file, 'a') as f:
        f.write(status_json + '\n')
```

### 4. CLI Integration - live-port Command

**File: `axfl/cli.py` (lines 459-495)**

```python
@cli.command('live-port')
@click.option('--cfg', default='axfl/config/sessions.yaml', help='Path to sessions config YAML')
@click.option('--mode', type=click.Choice(['ws', 'replay']), default='replay', help='Mode: ws or replay')
@click.option('--source', type=click.Choice(['auto', 'finnhub', 'twelvedata']), default='auto', help='Data source')
@click.option('--spread_pips', type=float, default=None, help='Override spread in pips')
def live_port(cfg: str, mode: str, source: str, spread_pips: float):
    """Run portfolio live paper trading with multiple strategies."""
    
    click.echo("=== AXFL Portfolio Live Trading ===")
    click.echo(f"Config: {cfg}")
    click.echo(f"Mode: {mode}")
    click.echo(f"Source: {source}")
    click.echo()
    
    # Load and normalize config
    try:
        raw_cfg = load_sessions_yaml(cfg)
        schedule_cfg = normalize_schedule(raw_cfg)
    except Exception as e:
        click.echo(f"Error loading config: {e}", err=True)
        return
    
    # Apply overrides from CLI
    schedule_cfg['source'] = source
    if spread_pips is not None:
        schedule_cfg['spread_pips'] = spread_pips
    
    # Create and run portfolio engine
    try:
        engine = PortfolioEngine(schedule_cfg, mode=mode)
        engine.run()
    except KeyboardInterrupt:
        click.echo("\n\nPortfolio stopped by user.")
    except Exception as e:
        click.echo(f"\nError running portfolio: {e}", err=True)
        import traceback
        traceback.print_exc()
```

## Summary

✅ **Multi-Strategy Portfolio**: PortfolioEngine orchestrates multiple (strategy, symbol) pairs
✅ **Session-Aware Trading**: SessionWindow gating - only trades during configured UTC windows
✅ **Portfolio Risk Management**: Global daily R stop (-5.0R default) + per-strategy limits
✅ **Unified Monitoring**: Single AXFL LIVE PORT JSON block with aggregated stats
✅ **Cost Model Preserved**: 0.6 pip spread + ATR slippage maintained
✅ **Tuned Defaults Reused**: LSG v2 optimized params auto-loaded for EURUSD 5m
✅ **Dual Mode Support**: Websocket (planned) and replay (working) modes
✅ **Persistence**: Trades → CSV, logs → portfolio_live_YYYYMMDD.jsonl
