"""
Walk-forward grid search tuner with purged cross-validation.
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Tuple
from itertools import product
from datetime import timedelta

from ..core.backtester import Backtester
from ..core.metrics import compute_metrics


def param_grid_product(param_grid: Dict[str, List]) -> List[Dict]:
    """
    Generate all combinations from parameter grid.
    
    Args:
        param_grid: Dictionary mapping param names to lists of values
    
    Returns:
        List of parameter dictionaries
    """
    if not param_grid:
        return [{}]
    
    keys = list(param_grid.keys())
    values = list(param_grid.values())
    
    combinations = []
    for combo in product(*values):
        combinations.append(dict(zip(keys, combo)))
    
    return combinations


def tune_strategy(df: pd.DataFrame, 
                 strategy_class: Any,
                 symbol: str,
                 param_grid: Dict[str, List],
                 cv_splits: int = 4,
                 purge_minutes: int = 60,
                 spread_pips: float = 0.6) -> Dict[str, Any]:
    """
    Walk-forward parameter tuning with purged cross-validation.
    
    Args:
        df: Full OHLCV DataFrame with DatetimeIndex
        strategy_class: Strategy class to instantiate
        symbol: Trading symbol
        param_grid: Dictionary mapping param names to lists of values
        cv_splits: Number of CV folds
        purge_minutes: Minutes to exclude at fold boundaries
        spread_pips: Spread cost in pips
    
    Returns:
        Dictionary with best_params and fold results
    """
    # Generate all parameter combinations
    param_combinations = param_grid_product(param_grid)
    
    if len(param_combinations) == 0:
        return {'best_params': {}, 'folds': [], 'error': 'Empty param grid'}
    
    # Split data chronologically
    total_bars = len(df)
    bars_per_fold = total_bars // cv_splits
    purge_bars = int(purge_minutes / 5)  # Assuming 5m bars
    
    folds = []
    for k in range(cv_splits):
        # Test window: fold k
        test_start_idx = k * bars_per_fold
        test_end_idx = min((k + 1) * bars_per_fold, total_bars)
        
        # Train window: all bars before fold k, excluding purge
        train_start_idx = 0
        train_end_idx = max(0, test_start_idx - purge_bars)
        
        # Skip if insufficient data
        if train_end_idx <= train_start_idx or test_end_idx <= test_start_idx:
            continue
        
        folds.append({
            'fold': k,
            'train_idx': (train_start_idx, train_end_idx),
            'test_idx': (test_start_idx, test_end_idx),
            'train_range': (df.index[train_start_idx], df.index[train_end_idx - 1]),
            'test_range': (df.index[test_start_idx], df.index[test_end_idx - 1]),
        })
    
    # Evaluate each parameter combination
    results = []
    
    for params in param_combinations:
        fold_scores = []
        
        for fold_info in folds:
            train_start, train_end = fold_info['train_idx']
            test_start, test_end = fold_info['test_idx']
            
            # Test on fold (we don't "train" anything, just evaluate)
            test_df = df.iloc[test_start:test_end].copy()
            
            if len(test_df) < 10:
                continue
            
            try:
                # Run backtest on test fold
                strategy = strategy_class(symbol, params)
                backtester = Backtester(symbol, spread_pips=spread_pips)
                trades_df, equity_curve_df, metrics = backtester.run(test_df, strategy)
                
                fold_scores.append({
                    'fold': fold_info['fold'],
                    'sharpe': metrics.get('sharpe', 0.0),
                    'total_return': metrics.get('total_return', 0.0),
                    'max_drawdown': metrics.get('max_drawdown', 0.0),
                    'trade_count': metrics.get('trade_count', 0),
                    'win_rate': metrics.get('win_rate', 0.0),
                })
            except Exception as e:
                # Skip failed backtests
                fold_scores.append({
                    'fold': fold_info['fold'],
                    'sharpe': -999,
                    'total_return': -999,
                    'max_drawdown': 1.0,
                    'trade_count': 0,
                    'win_rate': 0.0,
                    'error': str(e),
                })
        
        # Aggregate fold scores
        if len(fold_scores) > 0:
            avg_sharpe = np.mean([f['sharpe'] for f in fold_scores if f['sharpe'] > -900])
            avg_return = np.mean([f['total_return'] for f in fold_scores if f['total_return'] > -900])
            avg_dd = np.mean([f['max_drawdown'] for f in fold_scores])
            total_trades = sum([f['trade_count'] for f in fold_scores])
            
            results.append({
                'params': params,
                'avg_sharpe': avg_sharpe,
                'avg_return': avg_return,
                'avg_dd': avg_dd,
                'total_trades': total_trades,
                'folds': fold_scores,
            })
    
    # Rank by sharpe, then return, then drawdown
    if len(results) == 0:
        return {'best_params': {}, 'folds': [], 'error': 'No successful evaluations'}
    
    results_sorted = sorted(results, 
                           key=lambda x: (-x['avg_sharpe'], -x['avg_return'], x['avg_dd']))
    
    best = results_sorted[0]
    
    return {
        'best_params': best['params'],
        'best_sharpe': best['avg_sharpe'],
        'best_return': best['avg_return'],
        'best_dd': best['avg_dd'],
        'best_trades': best['total_trades'],
        'folds': best['folds'],
        'all_results': results_sorted[:5],  # Top 5
        'fold_info': folds,
    }
