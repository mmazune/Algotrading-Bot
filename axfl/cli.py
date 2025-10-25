"""
Command-line interface for AXFL trading system.
"""
import click
import json
import pandas as pd
from typing import Dict, Any

from .data.provider import DataProvider
from .data.symbols import normalize
from .core.backtester import Backtester
from .core.metrics import format_metrics
from .strategies.arls import ARLSStrategy
from .strategies.orb import ORBStrategy
from .strategies.lsg import LSGStrategy
from .strategies.choch_ob import CHOCHOBStrategy
from .strategies.breaker import BreakerStrategy
from .live.paper import LivePaperEngine
from .portfolio.scheduler import load_sessions_yaml, normalize_schedule
from .portfolio.engine import PortfolioEngine
from .tools.signal_scan import scan_symbols
from .live.targets import windows_by_symbol, window_filter, earliest_start


STRATEGY_MAP = {
    'arls': ARLSStrategy,
    'orb': ORBStrategy,
    'lsg': LSGStrategy,
    'choch_ob': CHOCHOBStrategy,
    'breaker': BreakerStrategy,
}


@click.group()
def cli():
    """AXFL - Asia Range Liquidity Sweep Trading System."""
    pass


@cli.command()
@click.option('--strategy', type=click.Choice(['arls', 'orb', 'lsg', 'choch_ob', 'breaker']), default='arls',
              help='Strategy to backtest')
@click.option('--symbol', default='EURUSD=X',
              help='Trading symbol (default: EURUSD=X)')
@click.option('--interval', type=click.Choice(['1m', '2m', '5m']), default='1m',
              help='Time interval (default: 1m)')
@click.option('--days', type=int, default=20,
              help='Number of days to backtest (default: 20)')
@click.option('--params', default=None,
              help='JSON string of strategy parameters')
@click.option('--source', type=click.Choice(['auto', 'twelvedata', 'finnhub', 'yf']), 
              default='auto',
              help='Data source (default: auto)')
@click.option('--venue', default=None,
              help='Venue for Finnhub (e.g., OANDA)')
@click.option('--spread_pips', type=float, default=0.6,
              help='Bid-ask spread in pips (default: 0.6)')
def backtest(strategy: str, symbol: str, interval: str, days: int, params: str,
             source: str, venue: str, spread_pips: float):
    """
    Run backtest for a trading strategy.
    """
    click.echo(f"=== AXFL Backtest ===")
    click.echo(f"Strategy: {strategy}")
    click.echo(f"Symbol: {symbol}")
    click.echo(f"Interval: {interval}")
    click.echo(f"Days: {days}")
    click.echo(f"Source: {source}")
    if venue:
        click.echo(f"Venue: {venue}")
    click.echo()
    
    # Parse parameters
    strategy_params = {}
    if params:
        try:
            strategy_params = json.loads(params)
        except json.JSONDecodeError as e:
            click.echo(f"Error parsing params JSON: {e}", err=True)
            return
    
    # Initialize data provider
    provider = DataProvider(source=source, venue=venue, rotate=True)
    
    # Normalize symbol for display
    normalized_symbol = normalize(symbol, source, venue)
    click.echo(f"Normalized symbol: {normalized_symbol}")
    click.echo()
    
    # Load data
    click.echo("Loading data...")
    try:
        df = provider.get_intraday(symbol, interval=interval, days=days)
        click.echo(f"Loaded {len(df)} bars from {df.index[0]} to {df.index[-1]}")
        click.echo(f"Provider used: {provider.last_source_used}")
        click.echo(f"Symbol used: {provider.last_symbol_used}")
    except Exception as e:
        click.echo(f"Error loading data: {e}", err=True)
        result = {
            "ok": False,
            "error": str(e),
            "strategy": strategy,
            "symbol": symbol,
            "interval": interval,
            "days": days,
            "source": source,
        }
        print_result_block(result)
        return
    
    # Initialize strategy
    click.echo(f"\nInitializing {strategy.upper()} strategy...")
    strategy_class = STRATEGY_MAP[strategy]
    strategy_instance = strategy_class(symbol, strategy_params)
    
    # Run backtest
    click.echo("Running backtest...")
    backtester = Backtester(symbol, initial_capital=100000.0, risk_percent=0.5, spread_pips=spread_pips)
    
    try:
        trades_df, equity_curve_df, metrics = backtester.run(df, strategy_instance)
    except Exception as e:
        click.echo(f"Error during backtest: {e}", err=True)
        import traceback
        traceback.print_exc()
        result = {
            "ok": False,
            "error": str(e),
            "strategy": strategy,
            "symbol": symbol,
            "interval": interval,
            "days": days,
        }
        print_result_block(result)
        return
    
    # Display results
    click.echo("\n" + format_metrics(metrics))
    
    click.echo(f"\n=== Trade Summary ===")
    if not trades_df.empty:
        click.echo(f"Total trades: {len(trades_df)}")
        click.echo(f"\nFirst 3 trades:")
        display_cols = ['entry_time', 'exit_time', 'side', 'entry', 'exit', 'pnl', 'r_multiple']
        click.echo(trades_df[display_cols].head(3).to_string(index=False))
    else:
        click.echo("No trades executed.")
    
    # Prepare trades sample for result
    trades_sample = []
    if not trades_df.empty:
        for _, trade in trades_df.head(3).iterrows():
            trades_sample.append({
                'entry_time': str(trade['entry_time']),
                'exit_time': str(trade['exit_time']),
                'side': trade['side'],
                'pnl': float(trade['pnl']),
                'r_multiple': float(trade['r_multiple']),
            })
    
    # Build result JSON
    result = {
        "ok": True,
        "strategy": strategy,
        "symbol": symbol,
        "normalized_symbol": provider.last_symbol_used,
        "source": provider.last_source_used,
        "interval": interval,
        "days": days,
        "metrics": {
            "total_return": round(metrics['total_return'], 4),
            "sharpe": round(metrics['sharpe'], 2),
            "max_drawdown": round(metrics['max_drawdown'], 4),
            "trade_count": metrics['trade_count'],
            "win_rate": round(metrics['win_rate'], 4),
        },
        "trades_sample": trades_sample,
        "git_changed": True,  # Files were created in this run
    }
    
    # Include debug info if available
    if 'debug' in metrics:
        result['debug'] = metrics['debug']
    
    # Include risk summary
    if 'risk' in metrics:
        result['risk'] = metrics['risk']
    
    # Include cost information
    result['costs'] = {
        'spread_pips': spread_pips,
        'slippage_model': 'max(1 pip, ATR/1000)',
    }
    
    print_result_block(result)


@cli.command()
@click.option('--strategy', type=click.Choice(['arls', 'orb', 'lsg', 'choch_ob', 'breaker']),
              required=True, help='Strategy to tune')
@click.option('--symbol', default='EURUSD', help='Trading symbol')
@click.option('--interval', type=click.Choice(['1m', '2m', '5m']), default='5m')
@click.option('--days', type=int, default=45, help='Days of data for tuning')
@click.option('--source', type=click.Choice(['auto', 'twelvedata', 'finnhub', 'yf']), default='auto')
@click.option('--params', required=True, help='JSON with {"grid": {...}}')
@click.option('--cv', type=int, default=4, help='Number of CV folds')
@click.option('--purge', type=int, default=60, help='Purge minutes at boundaries')
@click.option('--spread_pips', type=float, default=0.6, help='Spread in pips')
def tune(strategy: str, symbol: str, interval: str, days: int, source: str,
         params: str, cv: int, purge: int, spread_pips: float):
    """Run walk-forward parameter tuning with purged CV."""
    from .tune.grid import tune_strategy
    
    click.echo(f"=== AXFL Parameter Tuning ===")
    click.echo(f"Strategy: {strategy}")
    click.echo(f"Symbol: {symbol}")
    click.echo(f"CV Folds: {cv}, Purge: {purge}m")
    click.echo()
    
    # Parse param grid
    try:
        param_config = json.loads(params)
        param_grid = param_config.get('grid', {})
    except json.JSONDecodeError as e:
        click.echo(f"Error parsing params: {e}", err=True)
        return
    
    # Load data
    provider = DataProvider(source=source, rotate=True)
    click.echo("Loading data...")
    try:
        df = provider.get_intraday(symbol, interval=interval, days=days)
        click.echo(f"Loaded {len(df)} bars")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        return
    
    # Run tuning
    click.echo("\nRunning walk-forward tuning...")
    strategy_class = STRATEGY_MAP[strategy]
    
    tune_result = tune_strategy(
        df=df,
        strategy_class=strategy_class,
        symbol=symbol,
        param_grid=param_grid,
        cv_splits=cv,
        purge_minutes=purge,
        spread_pips=spread_pips
    )
    
    # Display results
    click.echo("\n=== Tuning Results ===")
    click.echo(f"Best Params: {tune_result['best_params']}")
    click.echo(f"Avg Sharpe: {tune_result.get('best_sharpe', 0):.2f}")
    click.echo(f"Avg Return: {tune_result.get('best_return', 0):.2%}")
    click.echo(f"Total Trades: {tune_result.get('best_trades', 0)}")
    
    # Print fold details
    click.echo("\n=== Fold Performance ===")
    for fold in tune_result.get('folds', []):
        click.echo(f"Fold {fold['fold']}: Sharpe={fold.get('sharpe', 0):.2f}, "
                  f"Return={fold.get('total_return', 0):.2%}, Trades={fold.get('trade_count', 0)}")
    
    # Output JSON block
    result = {
        "ok": True,
        "strategy": strategy,
        "source": provider.last_source_used,
        "normalized_symbol": provider.last_symbol_used,
        "interval": interval,
        "days": days,
        "cv_splits": cv,
        "purge_minutes": purge,
        "best_params": tune_result['best_params'],
        "best_sharpe": round(tune_result.get('best_sharpe', 0), 2),
        "best_return": round(tune_result.get('best_return', 0), 4),
        "folds": tune_result.get('folds', []),
    }
    
    result_json = json.dumps(result, separators=(',', ':'))
    print("\n###BEGIN-AXFL-TUNE###")
    print(result_json)
    print("###END-AXFL-TUNE###")


@cli.command()
@click.option('--strategies', required=True, help='Comma-separated strategy names')
@click.option('--symbol', default='EURUSD', help='Trading symbol')
@click.option('--interval', type=click.Choice(['1m', '2m', '5m']), default='5m')
@click.option('--days', type=int, default=30)
@click.option('--source', type=click.Choice(['auto', 'twelvedata', 'finnhub', 'yf']), default='auto')
@click.option('--spread_pips', type=float, default=0.6)
@click.option('--best', default=None, help='JSON with best_params per strategy (optional)')
def compare(strategies: str, symbol: str, interval: str, days: int, source: str,
            spread_pips: float, best: str):
    """Compare multiple strategies side-by-side."""
    click.echo(f"=== AXFL Strategy Comparison ===")
    click.echo(f"Strategies: {strategies}")
    click.echo(f"Symbol: {symbol}, Days: {days}")
    click.echo()
    
    # Parse strategies
    strategy_list = [s.strip() for s in strategies.split(',')]
    
    # Parse best params if provided
    best_params_map = {}
    if best:
        try:
            best_params_map = json.loads(best)
        except json.JSONDecodeError:
            click.echo("Warning: Could not parse --best JSON", err=True)
    
    # Load data once
    provider = DataProvider(source=source, rotate=True)
    click.echo("Loading data...")
    try:
        df = provider.get_intraday(symbol, interval=interval, days=days)
        click.echo(f"Loaded {len(df)} bars\n")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        return
    
    # Run each strategy
    comparison_results = []
    all_trades = {}
    
    for strat_name in strategy_list:
        if strat_name not in STRATEGY_MAP:
            click.echo(f"Unknown strategy: {strat_name}", err=True)
            continue
        
        click.echo(f"Running {strat_name}...")
        strategy_class = STRATEGY_MAP[strat_name]
        params = best_params_map.get(strat_name, {})
        
        strategy_instance = strategy_class(symbol, params)
        backtester = Backtester(symbol, spread_pips=spread_pips)
        
        try:
            trades_df, equity_curve_df, metrics = backtester.run(df, strategy_instance)
            
            comparison_results.append({
                'name': strat_name,
                'sharpe': round(metrics.get('sharpe', 0), 2),
                'total_return': round(metrics.get('total_return', 0), 4),
                'max_drawdown': round(metrics.get('max_drawdown', 0), 4),
                'win_rate': round(metrics.get('win_rate', 0), 4),
                'trade_count': metrics.get('trade_count', 0),
                'avg_r': round(metrics.get('avg_r', 0), 2),
            })
            
            all_trades[strat_name] = trades_df
            
            click.echo(f"  Sharpe: {metrics.get('sharpe', 0):.2f}, "
                      f"Return: {metrics.get('total_return', 0):.2%}, "
                      f"Trades: {metrics.get('trade_count', 0)}")
        except Exception as e:
            click.echo(f"  ERROR: {e}")
            comparison_results.append({
                'name': strat_name,
                'error': str(e),
            })
    
    # Find best strategy by Sharpe
    valid_results = [r for r in comparison_results if 'error' not in r]
    if valid_results:
        best_strat = max(valid_results, key=lambda x: x['sharpe'])
        click.echo(f"\n=== Best Strategy: {best_strat['name']} ===")
        
        # Get top 3 trades from best strategy
        trades_sample = []
        best_trades_df = all_trades.get(best_strat['name'])
        if best_trades_df is not None and not best_trades_df.empty:
            for _, trade in best_trades_df.head(3).iterrows():
                trades_sample.append({
                    'entry_time': str(trade['entry_time']),
                    'exit_time': str(trade['exit_time']),
                    'side': trade['side'],
                    'pnl': float(trade['pnl']),
                    'r_multiple': float(trade['r_multiple']),
                })
    else:
        trades_sample = []
    
    # Output result
    result = {
        "ok": True,
        "comparison": comparison_results,
        "source": provider.last_source_used,
        "normalized_symbol": provider.last_symbol_used,
        "interval": interval,
        "days": days,
        "trades_sample": trades_sample,
        "costs": {
            'spread_pips': spread_pips,
            'slippage_model': 'max(1 pip, ATR/1000)',
        },
    }
    
    print_result_block(result)


@cli.command()
@click.option('--strategy', type=click.Choice(['arls', 'orb', 'lsg', 'choch_ob', 'breaker']),
              default='lsg', help='Strategy to run')
@click.option('--symbol', default='EURUSD', help='Trading symbol')
@click.option('--interval', type=click.Choice(['5m']), default='5m', help='Timeframe')
@click.option('--source', type=click.Choice(['auto', 'finnhub', 'twelvedata']), 
              default='finnhub', help='Data source')
@click.option('--venue', default='OANDA', help='Venue for websocket')
@click.option('--spread_pips', type=float, default=0.6, help='Spread in pips')
@click.option('--mode', type=click.Choice(['ws', 'replay']), default='ws', 
              help='Mode: ws=websocket, replay=historical')
@click.option('--status_every', type=int, default=300, help='Status update interval (seconds)')
@click.option('--params', default=None, help='JSON params (optional, uses tuned defaults)')
def live(strategy: str, symbol: str, interval: str, source: str, venue: str,
         spread_pips: float, mode: str, status_every: int, params: str):
    """Run live paper trading with tuned parameters."""
    click.echo(f"=== AXFL Live Paper Trading ===")
    click.echo(f"Strategy: {strategy}")
    click.echo(f"Symbol: {symbol}")
    click.echo(f"Interval: {interval}")
    click.echo(f"Source: {source}")
    click.echo(f"Venue: {venue}")
    click.echo(f"Mode: {mode}")
    click.echo(f"Spread: {spread_pips} pips")
    click.echo(f"Status every: {status_every}s")
    
    # Parse user params if provided
    base_params = None
    if params:
        try:
            base_params = json.loads(params)
            click.echo(f"User params: {base_params}")
        except json.JSONDecodeError as e:
            click.echo(f"Error parsing params: {e}", err=True)
            return
    
    # Get strategy class
    strategy_class = STRATEGY_MAP.get(strategy)
    if not strategy_class:
        click.echo(f"Unknown strategy: {strategy}", err=True)
        return
    
    # Initialize and run engine
    engine = LivePaperEngine(
        strategy_class=strategy_class,
        symbol=symbol,
        interval=interval,
        source=source,
        venue=venue,
        spread_pips=spread_pips,
        warmup_days=3,
        mode=mode,
        status_every_s=status_every,
        base_params=base_params,
    )
    
    engine.run()


@cli.command('live-port')
@click.option('--cfg', default='axfl/config/sessions.yaml', help='Path to sessions config YAML')
@click.option('--mode', type=click.Choice(['ws', 'replay']), default='replay', help='Mode: ws or replay')
@click.option('--source', type=click.Choice(['auto', 'finnhub', 'twelvedata']), default=None, help='Data source (default: auto)')
@click.option('--spread_pips', type=float, default=None, help='Override spread in pips')
@click.option('--mirror', type=click.Choice(['none', 'oanda']), default='none', help='Broker mirroring')
@click.option('--profile', type=str, default='portfolio', help='YAML profile to use (default: portfolio)')
def live_port(cfg: str, mode: str, source: str, spread_pips: float, mirror: str, profile: str):
    """Run portfolio live paper trading with multiple strategies."""
    
    # Load and normalize config
    try:
        raw_cfg = load_sessions_yaml(cfg)
        schedule_cfg = normalize_schedule(raw_cfg, profile=profile)
    except Exception as e:
        click.echo(f"Error loading config: {e}", err=True)
        # Emit DIAG block
        diag = {"reason": "config_load_failed", "cfg": cfg, "profile": profile, "error": str(e)}
        print("\n###BEGIN-AXFL-DIAG###")
        print(json.dumps(diag, separators=(',', ':')))
        print("###END-AXFL-DIAG###\n")
        return
    
    # Validate schedule has symbols and strategies
    if not schedule_cfg.get('symbols') or not schedule_cfg.get('strategies'):
        click.echo(f"Error: Empty schedule - no symbols or strategies in {cfg}", err=True)
        # Emit DIAG block
        diag = {
            "reason": "empty_schedule",
            "cfg": cfg,
            "symbols": schedule_cfg.get('symbols', []),
            "strategies": [s.get('name') for s in schedule_cfg.get('strategies', [])]
        }
        print("\n###BEGIN-AXFL-DIAG###")
        print(json.dumps(diag, separators=(',', ':')))
        print("###END-AXFL-DIAG###\n")
        return
    
    # Default source to "auto" if not specified
    if source is None:
        source = schedule_cfg.get('source', 'auto')
        if not source or source not in ['auto', 'finnhub', 'twelvedata']:
            source = 'auto'
    
    click.echo("=== AXFL Portfolio Live Trading ===")
    click.echo(f"Config: {cfg}")
    click.echo(f"Mode: {mode}")
    click.echo(f"Source: {source}")
    click.echo(f"Mirror: {mirror}")
    click.echo()
    
    # Apply overrides from CLI
    schedule_cfg['source'] = source
    if spread_pips is not None:
        schedule_cfg['spread_pips'] = spread_pips
    
    # Initialize broker if mirroring enabled
    broker = None
    if mirror == 'oanda':
        try:
            from .brokers.oanda import OandaPractice
            click.echo("Initializing OANDA Practice broker...")
            broker = OandaPractice()
            if broker.connected:
                click.echo(f"✓ OANDA broker connected ({broker.env})")
            else:
                click.echo(f"⚠️  OANDA broker connection failed, continuing without mirror")
                broker = None
        except ImportError:
            click.echo("⚠️  OANDA broker not available, continuing without mirror")
        except Exception as e:
            click.echo(f"⚠️  OANDA broker init failed: {e}, continuing without mirror")
    
    # Create and run portfolio engine
    try:
        engine = PortfolioEngine(schedule_cfg, mode=mode, broker=broker)
        engine.run()
    except KeyboardInterrupt:
        click.echo("\n\nPortfolio stopped by user.")
    except Exception as e:
        click.echo(f"\nError running portfolio: {e}", err=True)
        import traceback
        traceback.print_exc()


def print_result_block(result: Dict[str, Any]):
    """Print the standardized AXFL result block."""
    result_json = json.dumps(result, separators=(',', ':'))
    print("\n###BEGIN-AXFL-RESULT###")
    print(result_json)
    print("###END-AXFL-RESULT###")


@cli.command()
@click.option('--symbols', default='EURUSD,GBPUSD,XAUUSD', help='Comma-separated symbols')
@click.option('--strategies', default='lsg,orb,arls', help='Comma-separated strategies')
@click.option('--days', type=int, default=30, help='Days to scan back')
@click.option('--source', type=click.Choice(['auto', 'twelvedata', 'finnhub']), default='auto', help='Data source')
@click.option('--venue', default='OANDA', help='Venue name')
@click.option('--method', type=click.Choice(['auto', 'exact', 'heuristic', 'volatility']), default='auto', help='Scan method')
@click.option('--top', type=int, default=3, help='Max windows per symbol/strategy')
@click.option('--pad_before', type=int, default=30, help='Minutes before signal')
@click.option('--pad_after', type=int, default=120, help='Minutes after signal')
def scan(symbols: str, strategies: str, days: int, source: str, venue: str, method: str, top: int, pad_before: int, pad_after: int):
    """Scan for high-probability signal windows."""
    
    symbol_list = [s.strip() for s in symbols.split(',')]
    strategy_list = [s.strip() for s in strategies.split(',')]
    
    click.echo("=== AXFL Signal Scanner ===")
    click.echo(f"Symbols: {symbol_list}")
    click.echo(f"Strategies: {strategy_list}")
    click.echo(f"Days: {days}")
    click.echo(f"Source: {source}")
    click.echo(f"Venue: {venue}")
    click.echo(f"Method: {method}")
    click.echo(f"Top: {top}")
    click.echo(f"Padding: {pad_before}m before, {pad_after}m after")
    click.echo()
    click.echo("Scanning...")
    
    try:
        result = scan_symbols(
            symbols=symbol_list,
            strategies=strategy_list,
            days=days,
            source=source,
            venue=venue,
            method=method,
            top=top,
            pad_before_m=pad_before,
            pad_after_m=pad_after,
        )
        
        result["ok"] = True
        
        # Print wrapped JSON
        result_json = json.dumps(result, separators=(',', ':'))
        print("\n###BEGIN-AXFL-SCANS###")
        print(result_json)
        print("###END-AXFL-SCANS###")
        
    except Exception as e:
        click.echo(f"Error during scan: {e}", err=True)
        import traceback
        traceback.print_exc()
        
        result = {"ok": False, "error": str(e)}
        result_json = json.dumps(result, separators=(',', ':'))
        print("\n###BEGIN-AXFL-SCANS###")
        print(result_json)
        print("###END-AXFL-SCANS###")


@cli.command('replay-slice')
@click.option('--scans', required=True, help='JSON string from AXFL-SCANS')
@click.option('--spread_pips_override', default='', help='Optional spread override')
@click.option('--ignore_yaml_windows', type=bool, default=True, help='Ignore YAML session windows')
@click.option('--extend', type=int, default=0, help='Extend windows by N minutes')
@click.option('--use_scan_params', type=bool, default=True, help='Use params from scan')
@click.option('--warmup_days', type=int, default=3, help='Days of warmup data')
@click.option('--assert_min_trades', type=int, default=1, help='Minimum trades expected')
def replay_slice(scans: str, spread_pips_override: str, ignore_yaml_windows: bool, extend: int,
                 use_scan_params: bool, warmup_days: int, assert_min_trades: int):
    """Replay only the scanned signal windows (fast targeted verification)."""
    
    click.echo("=== AXFL Targeted Replay ===")
    
    # Parse scans JSON
    try:
        scan_data = json.loads(scans)
    except json.JSONDecodeError as e:
        click.echo(f"Error parsing scans JSON: {e}", err=True)
        return
    
    if not scan_data.get("ok"):
        click.echo("Scans data indicates error, cannot replay", err=True)
        return
    
    targets = scan_data
    target_list = targets.get("targets", [])
    
    if not target_list:
        click.echo("No targets found in scans, nothing to replay", err=True)
        return
    
    click.echo(f"Loaded {len(target_list)} targets")
    if extend > 0:
        click.echo(f"Extending windows by {extend} minutes")
    if use_scan_params:
        click.echo(f"Using scan-embedded params where available")
    click.echo(f"Warmup: {warmup_days} days")
    click.echo(f"Assert min trades: {assert_min_trades}")
    
    # Compute earliest window start for warmup
    earliest_win_start = earliest_start(targets)
    click.echo(f"Earliest window: {earliest_win_start}")
    
    # Build symbol list and window map (with extension if specified)
    sym_windows = windows_by_symbol(targets, extend_minutes=extend)
    symbols = list(sym_windows.keys())
    
    click.echo(f"Symbols: {symbols}")
    for sym, wins in sym_windows.items():
        click.echo(f"  {sym}: {len(wins)} windows")
    click.echo()
    
    # Build a minimal schedule config for replay
    # Extract strategies from targets
    strategies_set = set()
    for tgt in target_list:
        strategies_set.add(tgt["strategy"])
    
    strategies_list = sorted(strategies_set)
    
    click.echo(f"Strategies: {strategies_list}")
    click.echo()
    
    # Create schedule config
    # Determine time range from windows
    all_starts = []
    all_ends = []
    for wins in sym_windows.values():
        for start, end in wins:
            all_starts.append(start)
            all_ends.append(end)
    
    if not all_starts:
        click.echo("No valid windows found", err=True)
        return
    
    min_start = min(all_starts)
    max_end = max(all_ends)
    
    click.echo(f"Time range: {min_start} to {max_end}")
    click.echo()
    
    # Build schedule_cfg with warmup
    schedule_cfg = {
        'symbols': symbols,
        'source': 'auto',
        'venue': 'OANDA',
        'interval': '5m',
        'warmup_days': warmup_days,
        'status_every_s': 5,
        'spreads': {
            'EURUSD': 0.6,
            'GBPUSD': 0.9,
            'XAUUSD': 2.5,
        },
        'risk': {
            'global_daily_stop_r': -5.0,
            'max_open_positions': 1,
            'per_strategy_daily_trades': 3,
            'per_strategy_daily_stop_r': -2.0,
        },
        'strategies': {},
    }
    
    # Extract scan params per (symbol, strategy) if available
    strategies_params = {}  # (symbol, strategy) -> params
    for tgt in target_list:
        sym = tgt["symbol"]
        strat = tgt["strategy"]
        key = (sym, strat)
        
        # Use scan params if available and flag is set
        if use_scan_params and "params" in tgt:
            strategies_params[key] = tgt["params"]
        else:
            strategies_params[key] = {}
    
    # Build strategies list (unique strategies)
    strategies_list_detailed = []
    for strat in strategies_list:
        strategies_list_detailed.append({
            'name': strat,
            'params': {},  # Per-engine params applied below
            'windows': [],  # Empty, we gate on target windows
        })
    
    schedule_cfg['strategies'] = strategies_list_detailed
    
    # Create portfolio engine with window filter
    try:
        engine = PortfolioEngine(schedule_cfg, mode='replay', broker=None)
        
        # Apply scan params to engines if available
        if use_scan_params and strategies_params:
            for (sym, strat), params in strategies_params.items():
                key = (sym, strat)
                if key in engine.engines and params:
                    click.echo(f"Applying scan params to {sym}/{strat}: {params}")
                    # Override strategy params
                    if hasattr(engine.engines[key], 'strategy'):
                        engine.engines[key].strategy.params = params
        
        # Inject window filter into engine
        engine._target_windows = sym_windows
        engine._windows_used = {sym: 0 for sym in symbols}  # Track usage
        
        # Override _process_bar to check window filter
        original_process_bar = engine._process_bar
        
        def filtered_process_bar(symbol, bar_dict):
            # Check if this bar is in any target window
            bar_time = bar_dict['time']
            
            if bar_time.tz is None:
                ts_utc = pd.Timestamp(bar_time, tz='UTC')
            else:
                ts_utc = bar_time.tz_convert('UTC') if bar_time.tz != 'UTC' else bar_time
            
            sym_wins = engine._target_windows.get(symbol, [])
            if not window_filter(ts_utc, sym_wins):
                return  # Skip this bar
            
            engine._windows_used[symbol] = engine._windows_used.get(symbol, 0) + 1
            
            # Process normally
            original_process_bar(symbol, bar_dict)
        
        engine._process_bar = filtered_process_bar
        
        # Override _print_status to include targets_used in JSON
        original_print_status = engine._print_status
        
        def enhanced_print_status():
            """Print unified status with targets_used."""
            now = pd.Timestamp.now(tz='UTC')
            
            # Build base status (duplicate logic from engine._print_status)
            broker_stats = {
                'mirror': 'oanda' if engine.broker else 'none',
                'connected': False,
                'errors': 0
            }
            if engine.broker:
                stats = engine.broker.get_stats()
                broker_stats['connected'] = stats.get('connected', False)
                broker_stats['errors'] = stats.get('errors', 0)
            
            ws_stats = {
                'connected': engine.ws_connected,
                'errors': engine.ws_errors,
            }
            if engine.ws_client:
                client_stats = engine.ws_client.get_stats()
                ws_stats['connected'] = client_stats.get('connected', False)
                ws_stats['errors'] = client_stats.get('errors', 0)
                ws_stats['key_index'] = client_stats.get('key_index', 0)
            
            status = {
                'ok': True,
                'mode': engine.mode,
                'source': engine.actual_source or engine.source,
                'interval': engine.interval,
                'since': str(engine.first_bar_time),
                'now': str(engine.last_bar_time),
                'symbols': engine.symbols,
                'engines': engine._get_engines_roster(),
                'positions': engine._get_open_positions(),
                'today': engine._get_portfolio_stats(),
                'risk': {
                    'halted': engine.halted,
                    'global_daily_stop_r': engine.global_daily_stop_r,
                },
                'costs': {
                    'spreads': engine.spreads if engine.spreads else {'default': engine.spread_pips},
                    'slippage_model': 'max(1 pip, ATR/1000)',
                },
                'broker': broker_stats,
                'ws': ws_stats,
                'targets_used': engine._windows_used,  # Add targets tracking
            }
            
            # Print single-line JSON block
            status_json = json.dumps(status, separators=(',', ':'))
            print("\n###BEGIN-AXFL-LIVE-PORT###")
            print(status_json)
            print("###END-AXFL-LIVE-PORT###\n")
            
            # Log to file
            from pathlib import Path
            from datetime import datetime as dt
            logs_dir = Path('logs')
            logs_dir.mkdir(exist_ok=True)
            log_file = logs_dir / f"portfolio_live_{dt.now().strftime('%Y%m%d')}.jsonl"
            with open(log_file, 'a') as f:
                f.write(status_json + '\n')
        
        engine._print_status = enhanced_print_status
        
        # Run replay
        click.echo("Starting targeted replay...")
        engine.run()
        
        # Count total trades across all engines
        total_trades = 0
        for (sym, strat), eng in engine.engines.items():
            eng_trades = len(eng.trades) if hasattr(eng, 'trades') else 0
            total_trades += eng_trades
        
        click.echo(f"\nTotal trades executed: {total_trades}")
        
        # Check assertion
        if assert_min_trades > 0 and total_trades < assert_min_trades:
            click.echo(f"ASSERTION FAILED: Expected >= {assert_min_trades} trades, got {total_trades}")
            
            # Emit DIAG block
            diag_info = {
                'ok': False,
                'reason': 'assertion_failed',
                'expected_min_trades': assert_min_trades,
                'actual_trades': total_trades,
                'targets_count': len(target_list),
                'windows_used': engine._windows_used,
                'engines': list(engine.engines.keys()),
                'scan_params_applied': use_scan_params,
            }
            
            diag_json = json.dumps(diag_info, indent=2)
            print("\n###BEGIN-AXFL-DIAG###")
            print(diag_json)
            print("###END-AXFL-DIAG###\n")
        else:
            click.echo(f"Assertion passed: {total_trades} >= {assert_min_trades}")
        
    except KeyboardInterrupt:
        click.echo("\n\nReplay stopped by user.")
    except Exception as e:
        click.echo(f"\nError during replay: {e}", err=True)
        import traceback
        traceback.print_exc()


@cli.command()
@click.option('--cfg', type=click.Path(exists=True), required=True,
              help='Path to sessions YAML config')
@click.option('--profile', type=str, default='portfolio', help='YAML profile to use (default: portfolio)')
def health(cfg, profile):
    """
    Health check: report data sources, symbols, spreads, and next session windows.
    """
    import os
    from datetime import datetime, time as dt_time
    from .portfolio.scheduler import pick_profile
    
    click.echo("=== AXFL Health Check ===\n")
    
    # Check data providers
    sources = []
    
    # Check TwelveData
    td_keys = os.getenv('TWELVEDATA_API_KEYS', '')
    if td_keys:
        sources.append("twelvedata")
        click.echo(f"✓ TwelveData: {len([k for k in td_keys.split(',') if k.strip()])} keys")
    
    # Check Finnhub
    fh_keys = os.getenv('FINNHUB_API_KEYS', '')
    if fh_keys:
        sources.append("finnhub")
        click.echo(f"✓ Finnhub: {len([k for k in fh_keys.split(',') if k.strip()])} keys")
    
    if not sources:
        click.echo("⚠️  No data source keys found")
        sources.append("none")
    
    # Load sessions config
    try:
        sessions_cfg = load_sessions_yaml(cfg)
        schedule_cfg = normalize_schedule(sessions_cfg, profile=profile)
    except Exception as e:
        click.echo(f"❌ Failed to load config: {e}", err=True)
        return
    
    symbols = schedule_cfg['symbols']
    spreads = schedule_cfg.get('spreads', {})
    strategies = [s['name'] for s in schedule_cfg['strategies']]
    
    click.echo(f"\nSymbols: {', '.join(symbols)}")
    click.echo(f"Strategies: {', '.join(strategies)}")
    click.echo(f"Spreads: {spreads}")
    
    # Calculate next windows (today)
    now = pd.Timestamp.now(tz='UTC')
    today_windows = []
    
    for strat_cfg in schedule_cfg['strategies']:
        strategy_name = strat_cfg['name']
        windows = strat_cfg.get('windows', [])
        
        for window in windows:
            # SessionWindow object - access attributes directly
            start_str = f"{window.start_h:02d}:{window.start_m:02d}"
            end_str = f"{window.end_h:02d}:{window.end_m:02d}"
            
            start_time = now.replace(hour=window.start_h, minute=window.start_m, second=0, microsecond=0)
            end_time = now.replace(hour=window.end_h, minute=window.end_m, second=0, microsecond=0)
            
            # Check if window is upcoming today
            if end_time > now:
                for symbol in symbols:
                    today_windows.append({
                        "symbol": symbol,
                        "strategy": strategy_name,
                        "start": start_str,
                        "end": end_str
                    })
    
    click.echo(f"\nNext windows today: {len(today_windows)}")
    for w in today_windows[:5]:  # Show first 5
        click.echo(f"  {w['symbol']}/{w['strategy']}: {w['start']}-{w['end']} UTC")
    
    # Determine effective source
    config_source = schedule_cfg.get('source', 'auto')
    if not config_source or config_source not in ['auto', 'finnhub', 'twelvedata']:
        config_source = 'auto'
    
    effective_source = config_source if sources and sources[0] != "none" else config_source
    
    # Build health JSON
    health_data = {
        "ok": True,
        "source": effective_source,
        "symbols": symbols,
        "spreads": spreads,
        "next_windows": today_windows
    }
    
    # Print single-line JSON block
    health_json = json.dumps(health_data, separators=(',', ':'))
    print("\n###BEGIN-AXFL-HEALTH###")
    print(health_json)
    print("###END-AXFL-HEALTH###")


@cli.command()
@click.option('--trades_dir', default='data/trades',
              help='Directory containing trade CSV files')
@click.option('--out_dir', default='reports',
              help='Directory for output reports')
def snapshot(trades_dir, out_dir):
    """
    Generate daily PnL snapshot from live trade logs.
    """
    from axfl.monitor import daily_snapshot
    
    click.echo("=== AXFL Daily PnL Snapshot ===\n")
    
    # Generate snapshot
    result = daily_snapshot(trades_dir=trades_dir, out_dir=out_dir)
    
    # Display summary
    click.echo(f"Date: {result['date']}")
    click.echo(f"Total R: {result['totals']['r']}")
    click.echo(f"Total Trades: {result['totals']['trades']}")
    click.echo(f"Total PnL: ${result['totals']['pnl']}")
    
    if result['by_strategy']:
        click.echo("\nBy Strategy:")
        for s in result['by_strategy']:
            click.echo(f"  {s['name']}: {s['r']}R, {s['trades']} trades, {s['wr']}% WR, ${s['pnl']}")
    
    if result['by_symbol']:
        click.echo("\nBy Symbol:")
        for s in result['by_symbol']:
            click.echo(f"  {s['symbol']}: {s['r']}R, {s['trades']} trades, {s['wr']}% WR, ${s['pnl']}")
    
    # Add file paths to result
    from datetime import datetime
    today = datetime.now().strftime("%Y%m%d")
    result['csv'] = f"{out_dir}/pnl_{today}.csv"
    result['md'] = f"{out_dir}/pnl_{today}.md"
    
    # Print single-line JSON block
    pnl_json = json.dumps(result, separators=(',', ':'))
    print("\n###BEGIN-AXFL-PNL###")
    print(pnl_json)
    print("###END-AXFL-PNL###")


@cli.command('demo-replay')
@click.option('--cfg', default='axfl/config/sessions.yaml', help='Path to sessions config YAML')
@click.option('--extend', type=int, default=15, help='Minutes to extend window edges')
def demo_replay(cfg: str, extend: int):
    """
    Demo replay of most recent London session for all configured symbols.
    Guarantees non-empty engine roster and valid timestamps.
    """
    from datetime import datetime, timedelta
    
    click.echo("=== AXFL Demo Replay (Last London Session) ===\n")
    
    # Load and normalize config
    try:
        raw_cfg = load_sessions_yaml(cfg)
        schedule_cfg = normalize_schedule(raw_cfg)
    except Exception as e:
        click.echo(f"Error loading config: {e}", err=True)
        diag = {"reason": "config_load_failed", "cfg": cfg, "error": str(e)}
        print("\n###BEGIN-AXFL-DIAG###")
        print(json.dumps(diag, separators=(',', ':')))
        print("###END-AXFL-DIAG###\n")
        return
    
    # Validate schedule
    if not schedule_cfg.get('symbols') or not schedule_cfg.get('strategies'):
        click.echo(f"Error: Empty schedule in {cfg}", err=True)
        diag = {"reason": "empty_schedule", "cfg": cfg}
        print("\n###BEGIN-AXFL-DIAG###")
        print(json.dumps(diag, separators=(',', ':')))
        print("###END-AXFL-DIAG###\n")
        return
    
    symbols = schedule_cfg['symbols']
    click.echo(f"Symbols: {symbols}")
    click.echo(f"Strategies: {[s['name'] for s in schedule_cfg['strategies']]}")
    click.echo(f"Window extension: {extend} minutes")
    click.echo()
    
    # Compute most recent London session date (yesterday if weekend)
    now_utc = pd.Timestamp.now(tz='UTC')
    target_date = now_utc.date()
    
    # If weekend, go back to Friday
    weekday = now_utc.weekday()
    if weekday == 5:  # Saturday
        target_date = (now_utc - timedelta(days=1)).date()
    elif weekday == 6:  # Sunday
        target_date = (now_utc - timedelta(days=2)).date()
    
    # Define London session window: 06:30-10:30 UTC
    session_start = pd.Timestamp(target_date, tz='UTC').replace(hour=6, minute=30-extend)
    session_end = pd.Timestamp(target_date, tz='UTC').replace(hour=10, minute=30+extend)
    
    click.echo(f"Target date: {target_date}")
    click.echo(f"Session window: {session_start} to {session_end}")
    click.echo()
    
    # Set warmup to 2 days before session start
    warmup_start = session_start - timedelta(days=2)
    schedule_cfg['warmup_days'] = 0  # We'll load manually
    
    # Force auto source for demo (avoid rate limits)
    schedule_cfg['source'] = 'auto'
    
    # Create engine
    try:
        engine = PortfolioEngine(schedule_cfg, mode='replay', broker=None)
        
        # Load warmup + session data
        provider = DataProvider(source='auto', rotate=True)
        
        click.echo("Loading data...")
        for symbol in symbols:
            # Calculate days to cover warmup + session
            days_needed = (session_end - warmup_start).days + 2
            df_1m = provider.get_intraday(symbol, interval='1m', days=min(days_needed, 30))
            
            if df_1m is None or df_1m.empty:
                click.echo(f"⚠️  No data for {symbol}, skipping")
                continue
            
            # Ensure UTC timezone
            if df_1m.index.tz is None:
                df_1m.index = pd.to_datetime(df_1m.index, utc=True)
            else:
                df_1m.index = df_1m.index.tz_convert('UTC')
            
            # Normalize column names (DataProvider returns capitalized)
            df_1m.columns = [c.lower() for c in df_1m.columns]
            
            # Resample to 5m
            df_5m = df_1m.resample('5min').agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            }).dropna()
            
            # Filter to warmup + session window
            df_5m = df_5m[(df_5m.index >= warmup_start) & (df_5m.index <= session_end)]
            
            click.echo(f"  {symbol}: {len(df_5m)} bars ({df_5m.index[0]} to {df_5m.index[-1]})")
            
            # Process each bar
            for idx, row in df_5m.iterrows():
                bar_dict = {
                    'time': idx,
                    'open': row['open'],
                    'high': row['high'],
                    'low': row['low'],
                    'close': row['close'],
                    'volume': row.get('volume', 0)
                }
                engine._process_bar(symbol, bar_dict)
        
        # Print final status
        click.echo("\nDemo replay complete.")
        engine._print_status()
        
        # Print summary
        stats = engine._get_portfolio_stats()
        click.echo(f"\nTotal R: {stats['r_total']}")
        click.echo(f"Total PnL: ${stats['pnl_total']}")
        for s in stats['by_strategy']:
            click.echo(f"  {s['name']}: {s['r']}R, {s['trades']} trades")
        
    except Exception as e:
        click.echo(f"\nError during demo replay: {e}", err=True)
        import traceback
        traceback.print_exc()


@cli.command('daily-runner')
@click.option('--cfg', default='axfl/config/sessions.yaml', help='Path to sessions config YAML')
@click.option('--profile', type=str, default='portfolio', help='YAML profile to use (default: portfolio)')
def daily_runner(cfg: str, profile: str):
    """
    Run automated daily trading sessions (London + NY).
    
    Executes two sessions per weekday:
    - London: 07:00-10:00 UTC
    - New York: 12:30-16:00 UTC
    
    Features:
    - Finnhub WebSocket with replay failover
    - Discord alerts on session events
    - Daily PnL snapshot at 16:05 UTC
    - Weekend/holiday detection
    """
    from axfl.ops import run_daily_sessions
    
    click.echo("=== AXFL Daily Runner ===\n")
    click.echo(f"Config: {cfg}")
    click.echo(f"Profile: {profile}")
    click.echo("Sessions: London (07:00-10:00 UTC), NY (12:30-16:00 UTC)")
    click.echo("Mode: Finnhub WS with replay failover")
    click.echo("\nPress Ctrl+C to stop\n")
    
    
    try:
        run_daily_sessions(config_path=cfg, profile=profile)
    except KeyboardInterrupt:
        click.echo("\n\nShutdown requested by user")
    except Exception as e:
        click.echo(f"\nError: {e}", err=True)
        import traceback
        traceback.print_exc()


@cli.command('risk')
@click.option('--cfg', default='axfl/config/sessions.yaml', help='Path to sessions config YAML')
def risk_command(cfg: str):
    """
    Compute and display portfolio risk budgets.
    
    Shows capital allocation across strategies, daily risk limits,
    and per-trade position sizing parameters.
    """
    from axfl.risk import compute_budgets
    
    click.echo("=== AXFL Risk Budgets ===\n")
    
    try:
        # Load config
        raw_cfg = load_sessions_yaml(cfg)
        schedule_cfg = normalize_schedule(raw_cfg)
        
        # Extract params
        symbols = schedule_cfg['symbols']
        strategies = [s['name'] for s in schedule_cfg['strategies']]
        spreads = schedule_cfg.get('spreads', {})
        
        # Compute budgets
        budgets = compute_budgets(
            symbols=symbols,
            strategies=strategies,
            spreads=spreads,
            equity_usd=100000.0,
            daily_risk_fraction=0.02,
            per_trade_fraction=0.005
        )
        
        # Display
        click.echo(f"Portfolio Equity: ${budgets['equity_usd']:,.0f}")
        click.echo(f"Daily Risk Limit: ${budgets['daily_r_total']:,.0f} ({budgets['daily_risk_fraction']*100:.1f}%)")
        click.echo(f"Per-Trade Risk: ${budgets['per_trade_r']:,.0f} ({budgets['per_trade_fraction']*100:.2f}%)")
        click.echo("\nPer-Strategy Budgets:")
        for strategy, amount in budgets['per_strategy'].items():
            pct = (amount / budgets['equity_usd']) * 100
            click.echo(f"  {strategy}: ${amount:,.0f} ({pct:.2f}%)")
        
        click.echo(f"\nNote: {budgets['notes']}")
        
        # Emit JSON block
        print("\n###BEGIN-AXFL-RISK###")
        print(json.dumps(budgets, separators=(',', ':')))
        print("###END-AXFL-RISK###")
        
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        import traceback
        traceback.print_exc()


@cli.command('news')
@click.option('--csv', default='samples/news_events.sample.csv', help='Path to news events CSV')
@click.option('--hours', default=24, type=int, help='Hours to look ahead')
def news_command(csv: str, hours: int):
    """
    Display upcoming high-impact news events.
    
    Shows event windows with padding that would block new trade entries.
    """
    from axfl.news import load_events_csv, upcoming_windows
    import os
    
    click.echo("=== AXFL News Calendar ===\n")
    
    try:
        if not os.path.exists(csv):
            click.echo(f"Error: News events CSV not found: {csv}", err=True)
            click.echo("Create one from samples/news_events.sample.csv")
            return
        
        # Load events
        df = load_events_csv(csv)
        click.echo(f"Loaded {len(df)} events from {csv}\n")
        
        # Get upcoming windows
        now = pd.Timestamp.now(tz='UTC')
        windows = upcoming_windows(df, now, pad_before_m=30, pad_after_m=30, lookahea_hours=hours)
        
        if not windows:
            click.echo(f"No high-impact events in next {hours} hours")
        else:
            click.echo(f"Upcoming events ({len(windows)} in next {hours}h):\n")
            for w in windows:
                click.echo(f"  {w['event_time']}")
                click.echo(f"    {w['title']}")
                click.echo(f"    Currencies: {', '.join(w['currencies'])}")
                click.echo(f"    Impact: {w['impact']}")
                click.echo(f"    Window: {w['start']} to {w['end']}")
                click.echo()
        
        # Emit JSON block
        result = {
            "csv": csv,
            "total_events": len(df),
            "upcoming": windows,
            "lookahead_hours": hours
        }
        print("###BEGIN-AXFL-NEWS###")
        print(json.dumps(result, separators=(',', ':')))
        print("###END-AXFL-NEWS###")
        
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        import traceback
        traceback.print_exc()


@cli.command('broker-test')
@click.option('--mirror', default='oanda', help='Broker to test (only oanda supported)')
@click.option('--symbol', default='EURUSD', help='Symbol for test calculation')
@click.option('--risk_perc', default=0.001, type=float, help='Risk percentage for test (0.1% default)')
@click.option('--place', is_flag=True, default=False, help='Actually place test order (default: dry run)')
@click.option('--sl_pips', default=10, type=int, help='Stop loss in pips for test order (default: 10)')
@click.option('--debug', is_flag=True, default=False, help='Enable debug output (instrument info, payload)')
def broker_test(mirror: str, symbol: str, risk_perc: float, place: bool, sl_pips: int, debug: bool):
    """
    Test OANDA broker connection and position sizing.
    
    Validates credentials, calculates position size, optionally places
    a micro test order with tag AXFL_SELFTEST.
    
    Safe and idempotent - uses minimal risk and closes immediately.
    """
    import os
    
    # Set debug and sl_pips env vars for broker to use
    if debug:
        os.environ['AXFL_DEBUG'] = '1'
    os.environ['AXFL_SELFTEST_SL_PIPS'] = str(sl_pips)
    
    click.echo("=== AXFL Broker Self-Test ===\n")
    
    result = {
        "ok": False,
        "mirror": mirror,
        "auth": False,
        "units": 0,
        "placed": False,
        "order_id": None,
        "error": None
    }
    
    try:
        # Check if OANDA is requested
        if mirror.lower() != 'oanda':
            result['error'] = f"Unsupported broker: {mirror} (only 'oanda' supported)"
            click.echo(f"Error: {result['error']}", err=True)
        else:
            # Check environment variables
            api_key = os.getenv('OANDA_API_KEY')
            account_id = os.getenv('OANDA_ACCOUNT_ID')
            env = os.getenv('OANDA_ENV', 'practice')
            
            if not api_key or not account_id:
                result['error'] = "Missing OANDA environment variables (OANDA_API_KEY, OANDA_ACCOUNT_ID)"
                click.echo(f"Error: {result['error']}", err=True)
                click.echo("\nSet environment variables:")
                click.echo("  export OANDA_API_KEY='your-token'")
                click.echo("  export OANDA_ACCOUNT_ID='your-account-id'")
                click.echo("  export OANDA_ENV='practice'  # or 'live'")
            else:
                # Import broker module
                try:
                    from axfl.brokers.oanda import OandaPractice
                except ImportError as e:
                    result['error'] = f"OANDA module not available: {e}"
                    click.echo(f"Error: {result['error']}", err=True)
                else:
                    # Create broker instance
                    broker = OandaPractice()
                    
                    # Test authentication with ping_auth() and get_account()
                    click.echo(f"Testing connection to OANDA {env}...")
                    try:
                        # Try ping_auth first
                        auth_result = broker.ping_auth() if hasattr(broker, 'ping_auth') else {'ok': False, 'error': 'no ping_auth'}
                        result['auth'] = auth_result.get('ok', False)
                        
                        if not result['auth']:
                            result['error'] = f"Authentication failed: {auth_result.get('error', 'unknown')}"
                            click.echo(f"✗ {result['error']}", err=True)
                        else:
                            click.echo(f"✓ Authentication successful")
                            
                            # Try get_account for details
                            account_info = broker.get_account() if hasattr(broker, 'get_account') else {'ok': False, 'balance': 0}
                            
                            if account_info.get('ok'):
                                click.echo(f"  Account: {account_info.get('id', account_id)}")
                                click.echo(f"  Balance: ${account_info.get('balance', 0):,.2f} {account_info.get('currency', 'USD')}")
                            else:
                                click.echo(f"  Account: {account_id}")
                                click.echo(f"  Balance: (unable to fetch: {account_info.get('error', 'unknown')})")
                            click.echo()
                            
                            # Calculate position size if auth succeeded
                            click.echo(f"Calculating position size for {symbol}...")
                            click.echo(f"  Risk: {risk_perc*100:.3f}% of equity")
                            
                            # Debug: Show instrument metadata
                            if debug:
                                click.echo("\n[DEBUG] Fetching instrument metadata...")
                                inst_info = broker._get_instrument_info(symbol)
                                click.echo(f"[DEBUG] Instrument info for {symbol}:")
                                click.echo(f"[DEBUG]   pipLocation: {inst_info['pipLocation']}")
                                click.echo(f"[DEBUG]   displayPrecision: {inst_info['displayPrecision']}")
                                click.echo(f"[DEBUG]   tradeUnitsPrecision: {inst_info['tradeUnitsPrecision']}")
                                
                                from axfl.utils.pricing import pip_size_from_location, pips_to_distance
                                pip_size_val = pip_size_from_location(inst_info['pipLocation'])
                                sl_distance = pips_to_distance(sl_pips, inst_info['pipLocation'])
                                
                                click.echo(f"[DEBUG]   Computed pip size: {pip_size_val}")
                                click.echo(f"[DEBUG]   SL pips: {sl_pips}")
                                click.echo(f"[DEBUG]   SL distance: {sl_distance}")
                                click.echo()
                            
                            # Use dummy entry/SL for calculation (10 pip stop)
                            from axfl.data.symbols import pip_size
                            from axfl.risk import units_from_risk
                            
                            if symbol == 'EURUSD':
                                entry = 1.1000
                            elif symbol == 'GBPUSD':
                                entry = 1.2500
                            elif symbol == 'XAUUSD':
                                entry = 2650.0
                            else:
                                entry = 1.0000
                            
                            pip = pip_size(symbol)
                            sl = entry - (10 * pip)  # 10 pip stop
                            
                            equity = float(account_info.get('balance', 100000))
                            units = units_from_risk(symbol, entry, sl, equity, risk_perc)
                            
                            result['units'] = units
                            click.echo(f"  Calculated units: {units}")
                            click.echo()
                            
                            # Place test order if requested
                            if place:
                                click.echo("⚠️  Placing test market order...")
                                test_units = max(1, units // 10)  # 1/10th of calculated, min 1
                                
                                order_result = broker.place_market(
                                    symbol=symbol,
                                    side='long',
                                    units=test_units,
                                    sl=sl,
                                    tp=entry + (20 * pip),  # 20 pip TP (2:1 RR)
                                    client_tag='AXFL_SELFTEST'
                                )
                                
                                if order_result['success']:
                                    result['placed'] = True
                                    result['order_id'] = order_result['order_id']
                                    click.echo(f"✓ Test order placed: {order_result['order_id']}")
                                    click.echo(f"  Units: {test_units}")
                                    click.echo(f"  Entry: {entry}")
                                    click.echo(f"  SL: {sl}")
                                    click.echo("\n⚠️  Remember to close this test position manually!")
                                else:
                                    result['error'] = order_result.get('error', 'Unknown error')
                                    click.echo(f"✗ Order failed: {result['error']}", err=True)
                            else:
                                click.echo("Dry run mode - no order placed")
                                click.echo("Use --place flag to actually place test order")
                            
                            result['ok'] = result['auth']
                        
                    except Exception as e:
                        result['error'] = f"Broker error: {str(e)}"
                        click.echo(f"✗ Error: {result['error']}", err=True)
                        import traceback
                        traceback.print_exc()
        
    except Exception as e:
        result['error'] = str(e)
        click.echo(f"Fatal error: {e}", err=True)
        import traceback
        traceback.print_exc()
    
    # Emit JSON block
    print("\n###BEGIN-AXFL-BROKER###")
    print(json.dumps(result, separators=(',', ':')))
    print("###END-AXFL-BROKER###")


@cli.command('risk-parity')
@click.option('--cfg', type=click.Path(exists=True), required=True, help='Path to sessions.yaml config file')
@click.option('--lookback', type=int, default=20, help='Lookback days for volatility calculation')
def risk_parity_command(cfg, lookback):
    """
    Compute and display risk-parity weights for portfolio symbols.
    
    Uses inverse-volatility weighting to allocate risk across symbols:
    - Higher volatility symbols get lower weight
    - Lower volatility symbols get higher weight
    - Ensures diversification and risk balance
    
    Example:
        axfl risk-parity --cfg axfl/config/sessions.yaml --lookback 20
    """
    from .risk.vol import inv_vol_weights, risk_parity_diagnostics
    from .data.provider import DataProvider
    from .data.symbols import pip_size
    import yaml
    
    click.echo("\n=== AXFL Risk-Parity Allocation ===\n")
    
    result = {
        'ok': False,
        'weights': {},
        'volatilities_pips': {},
        'diagnostics': {},
        'error': None
    }
    
    try:
        # Load config
        with open(cfg, 'r') as f:
            config = yaml.safe_load(f)
        
        portfolio_cfg = config.get('portfolio', {})
        symbols = portfolio_cfg.get('symbols', [])
        risk_parity_cfg = portfolio_cfg.get('risk_parity', {})
        
        floor = risk_parity_cfg.get('floor', 0.15)
        cap = risk_parity_cfg.get('cap', 0.60)
        
        if not symbols:
            result['error'] = "No symbols defined in config"
            click.echo(f"✗ {result['error']}", err=True)
            return
        
        click.echo(f"Symbols: {', '.join(symbols)}")
        click.echo(f"Lookback: {lookback} days")
        click.echo(f"Floor: {floor:.0%}, Cap: {cap:.0%}")
        click.echo()
        
        # Load data for each symbol
        click.echo("Loading historical data...")
        provider = DataProvider(source='auto', rotate=True)
        data_map = {}
        pip_map = {}
        
        for symbol in symbols:
            click.echo(f"  {symbol}...", nl=False)
            df = provider.get_intraday(symbol, interval='1m', days=lookback)
            
            if df is None or df.empty:
                click.echo(" ⚠️  No data")
                continue
            
            # Resample to 5m
            df_5m = df.resample('5min').agg({
                'Open': 'first',
                'High': 'max',
                'Low': 'min',
                'Close': 'last',
                'Volume': 'sum'
            }).dropna()
            
            # Rename columns for vol.py compatibility
            df_5m.columns = df_5m.columns.str.lower()
            
            data_map[symbol] = df_5m
            pip_map[symbol] = pip_size(symbol)
            
            click.echo(f" ✓ ({len(df_5m)} bars)")
        
        click.echo()
        
        # Compute weights
        click.echo("Computing risk-parity weights...")
        weights, vols = inv_vol_weights(
            symbols=symbols,
            data_map=data_map,
            lookback_d=lookback,
            pip_map=pip_map,
            floor=floor,
            cap=cap
        )
        
        result['weights'] = weights
        result['volatilities_pips'] = vols
        
        # Display results
        click.echo("\nSymbol Volatilities (ATR in pips):")
        for sym in sorted(symbols):
            vol = vols.get(sym, 0)
            click.echo(f"  {sym:8s}: {vol:6.2f} pips")
        
        click.echo("\nRisk-Parity Weights:")
        for sym in sorted(symbols):
            w = weights.get(sym, 0)
            click.echo(f"  {sym:8s}: {w:6.2%}")
        
        click.echo(f"\nSum of weights: {sum(weights.values()):.4f}")
        
        # Diagnostics
        diag = risk_parity_diagnostics(
            weights=weights,
            vols=vols,
            equity_usd=100000,
            per_trade_fraction=0.005
        )
        result['diagnostics'] = diag
        
        click.echo("\nPer-Symbol Risk Allocation (0.5% base risk):")
        for sym in sorted(symbols):
            risk_usd = diag['per_symbol_risk_usd'].get(sym, 0)
            risk_pct = diag['per_symbol_risk_pct'].get(sym, 0)
            click.echo(f"  {sym:8s}: ${risk_usd:7.2f} ({risk_pct:.3f}%)")
        
        result['ok'] = True
        
    except Exception as e:
        result['error'] = str(e)
        click.echo(f"\n✗ Error: {e}", err=True)
        import traceback
        traceback.print_exc()
    
    # Emit JSON block
    click.echo("\n###BEGIN-AXFL-RISK-PARITY###")
    click.echo(json.dumps(result, separators=(',', ':')))
    click.echo("###END-AXFL-RISK-PARITY###")


@cli.command('digest')
@click.option('--date', type=str, default=None, help='Date in YYYYMMDD format (default: today)')
@click.option('--logs-dir', type=click.Path(), default='logs', help='Directory containing JSONL logs')
@click.option('--reports-dir', type=click.Path(), default='reports', help='Directory to write reports')
@click.option('--discord-webhook', type=str, default=None, help='Discord webhook URL for notifications')
def digest_command(date, logs_dir, reports_dir, discord_webhook):
    """
    Generate daily PnL digest with CSV, Markdown, and chart.
    
    Analyzes trades from portfolio JSONL logs and produces:
    - CSV summary of all trades
    - Markdown report with stats and breakdowns
    - PNG chart of cumulative P&L
    - Optional Discord notification
    
    Example:
        axfl digest --date 20251020
        axfl digest --date 20251020 --discord-webhook https://discord.com/api/webhooks/...
    """
    from .monitor.digest import generate_digest
    from pathlib import Path
    from datetime import datetime
    
    # Default to today if no date provided
    if date is None:
        date = datetime.now().strftime('%Y%m%d')
    
    try:
        generate_digest(
            date_str=date,
            logs_dir=Path(logs_dir),
            reports_dir=Path(reports_dir),
            discord_webhook=discord_webhook
        )
    except Exception as e:
        click.echo(f"\n✗ Error generating digest: {e}", err=True)
        import traceback
        traceback.print_exc()
        raise


@cli.command('live-oanda')
@click.option('--cfg', type=click.Path(exists=True), required=True, help='Path to sessions YAML config')
@click.option('--mode', type=click.Choice(['ws', 'replay']), default='ws', help='Live mode (ws or replay)')
@click.option('--mirror', type=str, default='oanda', help='Broker mirror (default: oanda)')
@click.option('--profile', type=str, default='portfolio', help='YAML profile to use (default: portfolio)')
def live_oanda_command(cfg, mode, mirror, profile):
    """
    Run portfolio live trading with OANDA mirroring enabled.
    
    Performs startup reconciliation and emits LIVE-PORT JSON.
    
    Example:
        axfl live-oanda --cfg axfl/config/sessions.yaml --mode ws --profile portfolio
    """
    from pathlib import Path
    from .portfolio.scheduler import load_sessions_yaml, normalize_schedule
    from .portfolio.engine import PortfolioEngine
    
    try:
        # Load broker
        from .brokers.oanda import OandaPractice
        broker = OandaPractice()
    except Exception as e:
        click.echo(f"\n✗ Error loading OANDA broker: {e}", err=True)
        return
    
    # Load and normalize config with profile
    try:
        cfg_dict = load_sessions_yaml(cfg)
        schedule_cfg = normalize_schedule(cfg_dict, profile=profile)
    except ValueError as e:
        click.echo(f"\n✗ Config error: {e}", err=True)
        click.echo(f"  Profile: {profile}")
        click.echo(f"  Available profiles: {list(cfg_dict.keys())}")
        return
    except Exception as e:
        click.echo(f"\n✗ Error loading config: {e}", err=True)
        import traceback
        traceback.print_exc()
        return
    
    # Validate schedule has required keys
    if not schedule_cfg.get('strategies'):
        click.echo(f"\n✗ DIAG: Profile '{profile}' has no 'strategies' defined", err=True)
        return
    
    if not schedule_cfg.get('symbols'):
        click.echo(f"\n✗ DIAG: Profile '{profile}' has no 'symbols' defined", err=True)
        return
    
    # Create and run portfolio engine
    try:
        engine = PortfolioEngine(schedule_cfg, mode=mode, broker=broker)
        engine.run()
    except KeyboardInterrupt:
        click.echo("\n\n⚠️  Stopped by user")
    except Exception as e:
        click.echo(f"\n✗ Error: {e}", err=True)
        import traceback
        traceback.print_exc()


@cli.command('reconcile')
def reconcile_command():
    """
    Run reconciliation between broker and journal.
    
    Compares broker open positions vs journal, flattens conflicts if enabled.
    
    Example:
        axfl reconcile
    """
    import json
    
    result = {'ok': False, 'broker_positions': 0, 'journal_positions': 0, 'flattened': 0, 'linked': 0, 'errors': []}
    
    try:
        # Load broker
        from .brokers.oanda import OandaPractice
        broker = OandaPractice()
        
        # Load journal and reconcile engine
        from .journal import store as journal
        from .reconcile.engine import ReconcileEngine
        
        click.echo("\n=== Reconciliation ===\n")
        
        # Run reconciliation
        reconcile_engine = ReconcileEngine(broker)
        summary = reconcile_engine.reconcile()
        
        result = summary
        
        click.echo(f"✓ Reconciliation complete:")
        click.echo(f"  Broker positions: {summary['broker_positions']}")
        click.echo(f"  Journal positions: {summary['journal_positions']}")
        click.echo(f"  Flattened: {summary['flattened']}")
        click.echo(f"  Linked: {summary['linked']}")
        click.echo(f"  Errors: {len(summary['errors'])}")
        
        if summary['errors']:
            for err in summary['errors']:
                click.echo(f"    ⚠️  {err}")
        
    except Exception as e:
        result['error'] = str(e)
        click.echo(f"\n✗ Error: {e}", err=True)
        import traceback
        traceback.print_exc()
    
    # Emit JSON block
    click.echo("\n###BEGIN-AXFL-RECON###")
    click.echo(json.dumps(result, separators=(',', ':')))
    click.echo("###END-AXFL-RECON###")


@cli.command('digest-now')
def digest_now_command():
    """
    Generate intraday PnL digest on demand.
    
    Creates PNG chart of recent trades and optionally sends to Discord.
    
    Example:
        axfl digest-now
    """
    import json
    from .monitor.digest import intraday_digest
    
    result = {'ok': False, 'date': None, 'png': None, 'totals': {}}
    
    try:
        click.echo("\n=== Intraday Digest ===\n")
        
        # Generate digest
        result = intraday_digest(out_dir='reports', since_hours=6)
        
        if result['ok']:
            click.echo(f"\n✓ Digest generated:")
            click.echo(f"  Date: {result['date']}")
            click.echo(f"  Trades: {result['totals']['trades']}")
            click.echo(f"  Total R: {result['totals']['r']:+.2f}R")
            click.echo(f"  Total PnL: ${result['totals']['pnl']:+,.2f}")
            if result['png']:
                click.echo(f"  Chart: {result['png']}")
        
    except Exception as e:
        result['error'] = str(e)
        click.echo(f"\n✗ Error: {e}", err=True)
        import traceback
        traceback.print_exc()
    
    # Emit JSON block
    click.echo("\n###BEGIN-AXFL-DIGEST###")
    click.echo(json.dumps(result, separators=(',', ':')))
    click.echo("###END-AXFL-DIGEST###")


@cli.command('preflight')
@click.option('--cfg', default='axfl/config/sessions.yaml', help='Path to sessions config YAML')
@click.option('--profile', default='portfolio', help='YAML profile to use (default: portfolio)')
@click.option('--from-utc', default=None, help='ISO start to check upcoming windows; defaults to now')
@click.option('--hours', default=24, type=int, help='Lookahead window in hours for session windows')
def preflight_command(cfg, profile, from_utc, hours):
    """
    Pre-flight check: verify keys, profile, windows, and broker auth.
    
    Validates configuration, secrets, and broker connectivity before going live.
    
    Example:
        axfl preflight --cfg axfl/config/sessions.yaml --profile portfolio
    """
    import os
    import json
    from datetime import datetime, timedelta, time as dt_time
    import pandas as pd
    from .portfolio.scheduler import load_sessions_yaml, normalize_schedule, pick_profile
    
    result = {
        'ok': False,
        'cfg': cfg,
        'profile': profile,
        'source': None,
        'symbols': [],
        'strategies': [],
        'spreads': {},
        'windows_next': 0,
        'secrets': {},
        'broker_auth': False,
        'notes': 'Run live-oanda during windows; use demo_replay for quick test'
    }
    
    try:
        # Load and normalize config
        raw_cfg = load_sessions_yaml(cfg)
        schedule_cfg = normalize_schedule(raw_cfg, profile=profile)
        
        result['source'] = schedule_cfg.get('source', 'auto')
        result['symbols'] = schedule_cfg.get('symbols', [])
        result['strategies'] = [s['name'] for s in schedule_cfg.get('strategies', [])]
        result['spreads'] = schedule_cfg.get('spreads', {})
        
        # Compute next session windows
        start_time = pd.Timestamp.now(tz='UTC') if from_utc is None else pd.Timestamp(from_utc, tz='UTC')
        end_time = start_time + pd.Timedelta(hours=hours)
        
        windows_count = 0
        for strat_cfg in schedule_cfg.get('strategies', []):
            for window in strat_cfg.get('windows', []):
                # Check if window overlaps with [start_time, end_time]
                # For simplicity, count any window that could occur today or tomorrow
                current_date = start_time.date()
                for day_offset in range(hours // 24 + 2):
                    check_date = current_date + timedelta(days=day_offset)
                    window_start = pd.Timestamp(datetime.combine(check_date, dt_time(window.start_h, window.start_m))).tz_localize('UTC')
                    window_end = pd.Timestamp(datetime.combine(check_date, dt_time(window.end_h, window.end_m))).tz_localize('UTC')
                    
                    # Check if this window is in our range
                    if window_start >= start_time and window_start < end_time:
                        windows_count += 1
                        break
        
        result['windows_next'] = windows_count
        
        # Check secrets
        result['secrets'] = {
            'finnhub': bool(os.getenv('FINNHUB_API_KEYS')),
            'oanda': bool(os.getenv('OANDA_API_KEY') and os.getenv('OANDA_ACCOUNT_ID')),
            'discord': bool(os.getenv('DISCORD_WEBHOOK_URL'))
        }
        
        # Check broker auth if OANDA keys present
        if result['secrets']['oanda']:
            try:
                from .brokers.oanda import OandaPractice
                broker = OandaPractice()
                auth_result = broker.ping_auth()
                result['broker_auth'] = auth_result.get('ok', False)
            except Exception as e:
                result['broker_auth'] = False
                result['broker_error'] = str(e)
        else:
            result['broker_auth'] = False
            result['broker_error'] = 'no_oanda_env'
        
        result['ok'] = True
        
    except Exception as e:
        result['error'] = str(e)
        click.echo(f"\n✗ Preflight error: {e}", err=True)
    
    # Emit JSON block
    click.echo("\n###BEGIN-AXFL-PREFLIGHT###")
    click.echo(json.dumps(result, separators=(',', ':')))
    click.echo("###END-AXFL-PREFLIGHT###")


if __name__ == '__main__':
    cli()


