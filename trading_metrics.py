"""
Trading Metrics Calculator
Provides comprehensive trading performance metrics for algorithmic trading strategies.
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional


def calculate_metrics(strategy_returns: pd.Series, prices: pd.Series, positions: pd.Series) -> Dict:
    """
    Calculate comprehensive trading performance metrics.
    
    Parameters:
    -----------
    strategy_returns : pd.Series
        Daily strategy returns
    prices : pd.Series  
        Price series
    positions : pd.Series
        Position sizes over time
        
    Returns:
    --------
    Dict: Dictionary containing various performance metrics
    """
    
    metrics = {}
    
    # Basic return metrics
    total_return = (strategy_returns + 1).cumprod().iloc[-1] - 1
    annualized_return = (1 + total_return) ** (252 / len(strategy_returns)) - 1
    
    # Risk metrics
    volatility = strategy_returns.std() * np.sqrt(252)
    sharpe_ratio = annualized_return / volatility if volatility > 0 else 0
    
    # Drawdown analysis
    cumulative_returns = (strategy_returns + 1).cumprod()
    running_max = cumulative_returns.expanding().max()
    drawdowns = (cumulative_returns - running_max) / running_max
    max_drawdown = drawdowns.min()
    
    # Win/Loss analysis
    positive_returns = strategy_returns[strategy_returns > 0]
    negative_returns = strategy_returns[strategy_returns < 0]
    
    win_rate = len(positive_returns) / len(strategy_returns) if len(strategy_returns) > 0 else 0
    avg_win = positive_returns.mean() if len(positive_returns) > 0 else 0
    avg_loss = negative_returns.mean() if len(negative_returns) > 0 else 0
    profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else 0
    
    # Position analysis
    avg_position_size = positions.abs().mean()
    max_position_size = positions.abs().max()
    
    # Trading frequency
    position_changes = positions.diff().abs()
    trading_frequency = (position_changes > 0).sum()
    
    # Sortino ratio (downside deviation)
    downside_returns = strategy_returns[strategy_returns < 0]
    downside_volatility = downside_returns.std() * np.sqrt(252) if len(downside_returns) > 0 else 0
    sortino_ratio = annualized_return / downside_volatility if downside_volatility > 0 else 0
    
    # Calmar ratio
    calmar_ratio = annualized_return / abs(max_drawdown) if max_drawdown != 0 else 0
    
    # Information ratio
    excess_returns = strategy_returns - strategy_returns.mean()
    tracking_error = excess_returns.std() * np.sqrt(252)
    information_ratio = (annualized_return) / tracking_error if tracking_error > 0 else 0
    
    # Compile all metrics
    metrics = {
        'Total Return': total_return,
        'Annualized Return': annualized_return,
        'Volatility': volatility,
        'Sharpe Ratio': sharpe_ratio,
        'Sortino Ratio': sortino_ratio,
        'Calmar Ratio': calmar_ratio,
        'Information Ratio': information_ratio,
        'Max Drawdown': max_drawdown,
        'Win Rate': win_rate,
        'Average Win': avg_win,
        'Average Loss': avg_loss,
        'Profit Factor': profit_factor,
        'Average Position Size': avg_position_size,
        'Max Position Size': max_position_size,
        'Trading Frequency': trading_frequency,
        'Total Trades': trading_frequency,
        'Downside Volatility': downside_volatility
    }
    
    return metrics


def calculate_portfolio_metrics(portfolio_value: pd.Series, benchmark_returns: Optional[pd.Series] = None) -> Dict:
    """
    Calculate portfolio-level performance metrics.
    
    Parameters:
    -----------
    portfolio_value : pd.Series
        Portfolio value over time
    benchmark_returns : pd.Series, optional
        Benchmark returns for comparison
        
    Returns:
    --------
    Dict: Portfolio performance metrics
    """
    
    # Calculate returns from portfolio values
    returns = portfolio_value.pct_change().dropna()
    
    if len(returns) == 0:
        return {}
    
    # Basic metrics
    total_return = (portfolio_value.iloc[-1] / portfolio_value.iloc[0]) - 1
    annualized_return = (1 + total_return) ** (252 / len(returns)) - 1
    volatility = returns.std() * np.sqrt(252)
    
    # Risk-adjusted metrics
    sharpe_ratio = annualized_return / volatility if volatility > 0 else 0
    
    # Drawdown
    cumulative = portfolio_value / portfolio_value.iloc[0]
    running_max = cumulative.expanding().max()
    drawdowns = (cumulative - running_max) / running_max
    max_drawdown = drawdowns.min()
    
    metrics = {
        'Portfolio Total Return': total_return,
        'Portfolio Annualized Return': annualized_return,
        'Portfolio Volatility': volatility,
        'Portfolio Sharpe Ratio': sharpe_ratio,
        'Portfolio Max Drawdown': max_drawdown,
        'Final Portfolio Value': portfolio_value.iloc[-1],
        'Initial Portfolio Value': portfolio_value.iloc[0]
    }
    
    # Add benchmark comparison if provided
    if benchmark_returns is not None and len(benchmark_returns) > 0:
        benchmark_total = (benchmark_returns + 1).cumprod().iloc[-1] - 1
        benchmark_annualized = (1 + benchmark_total) ** (252 / len(benchmark_returns)) - 1
        excess_return = annualized_return - benchmark_annualized
        
        metrics.update({
            'Benchmark Total Return': benchmark_total,
            'Benchmark Annualized Return': benchmark_annualized,
            'Excess Return': excess_return,
            'Alpha': excess_return  # Simplified alpha
        })
    
    return metrics


def calculate_risk_metrics(returns: pd.Series, confidence_level: float = 0.05) -> Dict:
    """
    Calculate risk-specific metrics including VaR and CVaR.
    
    Parameters:
    -----------
    returns : pd.Series
        Return series
    confidence_level : float
        Confidence level for VaR calculation (default 5%)
        
    Returns:
    --------
    Dict: Risk metrics
    """
    
    if len(returns) == 0:
        return {}
    
    # Value at Risk (VaR)
    var = np.percentile(returns, confidence_level * 100)
    
    # Conditional Value at Risk (CVaR)
    cvar = returns[returns <= var].mean()
    
    # Skewness and Kurtosis
    skewness = returns.skew()
    kurtosis = returns.kurtosis()
    
    # Maximum consecutive losses
    consecutive_losses = 0
    max_consecutive_losses = 0
    
    for ret in returns:
        if ret < 0:
            consecutive_losses += 1
            max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
        else:
            consecutive_losses = 0
    
    metrics = {
        f'VaR ({confidence_level*100}%)': var,
        f'CVaR ({confidence_level*100}%)': cvar,
        'Skewness': skewness,
        'Kurtosis': kurtosis,
        'Max Consecutive Losses': max_consecutive_losses
    }
    
    return metrics


def format_metrics_report(metrics: Dict) -> str:
    """
    Format metrics dictionary into a readable report.
    
    Parameters:
    -----------
    metrics : Dict
        Metrics dictionary
        
    Returns:
    --------
    str: Formatted report string
    """
    
    report = "TRADING PERFORMANCE METRICS\n"
    report += "=" * 50 + "\n\n"
    
    # Return metrics
    if 'Total Return' in metrics:
        report += f"Total Return: {metrics['Total Return']:.2%}\n"
    if 'Annualized Return' in metrics:
        report += f"Annualized Return: {metrics['Annualized Return']:.2%}\n"
    
    # Risk metrics
    if 'Volatility' in metrics:
        report += f"Volatility: {metrics['Volatility']:.2%}\n"
    if 'Max Drawdown' in metrics:
        report += f"Max Drawdown: {metrics['Max Drawdown']:.2%}\n"
    
    # Risk-adjusted metrics
    report += "\nRisk-Adjusted Metrics:\n"
    report += "-" * 25 + "\n"
    if 'Sharpe Ratio' in metrics:
        report += f"Sharpe Ratio: {metrics['Sharpe Ratio']:.3f}\n"
    if 'Sortino Ratio' in metrics:
        report += f"Sortino Ratio: {metrics['Sortino Ratio']:.3f}\n"
    if 'Calmar Ratio' in metrics:
        report += f"Calmar Ratio: {metrics['Calmar Ratio']:.3f}\n"
    
    # Trading metrics
    if 'Win Rate' in metrics:
        report += "\nTrading Metrics:\n"
        report += "-" * 20 + "\n"
        report += f"Win Rate: {metrics['Win Rate']:.2%}\n"
        if 'Total Trades' in metrics:
            report += f"Total Trades: {metrics['Total Trades']}\n"
        if 'Profit Factor' in metrics:
            report += f"Profit Factor: {metrics['Profit Factor']:.2f}\n"
    
    return report
