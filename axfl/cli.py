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


def print_result_block(result: Dict[str, Any]):
    """Print the standardized AXFL result block."""
    result_json = json.dumps(result, separators=(',', ':'))
    print("\n###BEGIN-AXFL-RESULT###")
    print(result_json)
    print("###END-AXFL-RESULT###")


if __name__ == '__main__':
    cli()
