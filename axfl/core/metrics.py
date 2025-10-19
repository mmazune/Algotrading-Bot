"""
Performance metrics calculation for trading strategies.
"""
import pandas as pd
import numpy as np
from typing import Dict, Any


def compute_metrics(trades_df: pd.DataFrame, equity_curve: pd.DataFrame, 
                   initial_capital: float = 100000.0) -> Dict[str, Any]:
    """
    Compute comprehensive trading performance metrics.
    
    Args:
        trades_df: DataFrame with trade records (must have 'pnl' and 'r_multiple' columns)
        equity_curve: DataFrame with equity over time
        initial_capital: Starting capital
    
    Returns:
        Dictionary with performance metrics
    """
    metrics = {}
    
    if trades_df.empty:
        return {
            'total_return': 0.0,
            'cagr': 0.0,
            'max_drawdown': 0.0,
            'sharpe': 0.0,
            'trade_count': 0,
            'win_rate': 0.0,
            'avg_r': 0.0,
            'expectancy_r': 0.0,
        }
    
    # Basic trade statistics
    metrics['trade_count'] = len(trades_df)
    
    # Win rate
    winning_trades = trades_df[trades_df['pnl'] > 0]
    metrics['win_rate'] = len(winning_trades) / len(trades_df) if len(trades_df) > 0 else 0.0
    
    # R-multiple statistics
    if 'r_multiple' in trades_df.columns:
        metrics['avg_r'] = trades_df['r_multiple'].mean()
        metrics['expectancy_r'] = trades_df['r_multiple'].mean()
    else:
        metrics['avg_r'] = 0.0
        metrics['expectancy_r'] = 0.0
    
    # Total return
    total_pnl = trades_df['pnl'].sum()
    metrics['total_return'] = total_pnl / initial_capital
    
    # CAGR (assuming trading days)
    if not equity_curve.empty and len(equity_curve) > 1:
        days = (equity_curve.index[-1] - equity_curve.index[0]).days
        trading_days = max(1, days)
        years = trading_days / 252.0
        
        if years > 0:
            final_value = equity_curve['equity'].iloc[-1]
            metrics['cagr'] = (final_value / initial_capital) ** (1.0 / years) - 1.0
        else:
            metrics['cagr'] = 0.0
    else:
        metrics['cagr'] = 0.0
    
    # Maximum drawdown
    if not equity_curve.empty:
        equity = equity_curve['equity']
        running_max = equity.expanding().max()
        drawdown = (equity - running_max) / running_max
        metrics['max_drawdown'] = abs(drawdown.min())
    else:
        metrics['max_drawdown'] = 0.0
    
    # Sharpe ratio (risk-free rate = 0)
    if not equity_curve.empty and len(equity_curve) > 1:
        equity = equity_curve['equity']
        returns = equity.pct_change().dropna()
        
        if len(returns) > 0 and returns.std() > 0:
            # Annualize: assume returns are per bar, scale by sqrt(bars_per_year)
            # For simplicity, use daily returns approximation
            sharpe_daily = returns.mean() / returns.std()
            metrics['sharpe'] = sharpe_daily * np.sqrt(252)
        else:
            metrics['sharpe'] = 0.0
    else:
        metrics['sharpe'] = 0.0
    
    return metrics


def format_metrics(metrics: Dict[str, Any]) -> str:
    """
    Format metrics dictionary as a readable string.
    
    Args:
        metrics: Dictionary of performance metrics
    
    Returns:
        Formatted string
    """
    lines = [
        "=== Performance Metrics ===",
        f"Total Return: {metrics.get('total_return', 0) * 100:.2f}%",
        f"CAGR: {metrics.get('cagr', 0) * 100:.2f}%",
        f"Max Drawdown: {metrics.get('max_drawdown', 0) * 100:.2f}%",
        f"Sharpe Ratio: {metrics.get('sharpe', 0):.2f}",
        f"Trade Count: {metrics.get('trade_count', 0)}",
        f"Win Rate: {metrics.get('win_rate', 0) * 100:.2f}%",
        f"Avg R-Multiple: {metrics.get('avg_r', 0):.2f}",
        f"Expectancy (R): {metrics.get('expectancy_r', 0):.2f}",
    ]
    return "\n".join(lines)
