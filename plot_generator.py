#!/usr/bin/env python3
"""
Simple Plot Generator for Trading Analysis
Generates static PNG images that can be displayed in notebooks
"""

import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import seaborn as sns
import os

# Set style
plt.style.use('default')
sns.set_palette("husl")

def create_trading_dashboard(df, backtest_result=None, save_path="plots/"):
    """Create comprehensive trading analysis plots"""
    
    # Create plots directory
    os.makedirs(save_path, exist_ok=True)
    
    # Configure matplotlib
    plt.rcParams.update({
        'figure.figsize': (12, 8),
        'figure.dpi': 100,
        'font.size': 10,
        'axes.titlesize': 12,
        'lines.linewidth': 2
    })
    
    plots_created = []
    
    # Plot 1: Price Chart with Signals
    if all(col in df.columns for col in ['Close', 'SMA_20', 'SMA_50']):
        fig, ax = plt.subplots(figsize=(14, 8))
        
        # Plot price and moving averages
        ax.plot(df.index, df['Close'], 'k-', linewidth=2, label='Close Price', alpha=0.8)
        ax.plot(df.index, df['SMA_20'], 'blue', alpha=0.7, label='SMA 20')
        ax.plot(df.index, df['SMA_50'], 'red', alpha=0.7, label='SMA 50')
        
        # Add trading signals if available
        if 'Optimized_Trade_Signal' in df.columns:
            buy_signals = df[df['Optimized_Trade_Signal'] == 1]
            sell_signals = df[df['Optimized_Trade_Signal'] == -1]
            
            if len(buy_signals) > 0:
                ax.scatter(buy_signals.index, buy_signals['Close'], 
                          color='green', marker='^', s=100, label=f'Buy ({len(buy_signals)})', zorder=5)
            
            if len(sell_signals) > 0:
                ax.scatter(sell_signals.index, sell_signals['Close'], 
                          color='red', marker='v', s=100, label=f'Sell ({len(sell_signals)})', zorder=5)
        
        ax.set_title('AAPL Trading Strategy - Price Chart with Signals', fontsize=16, fontweight='bold')
        ax.set_xlabel('Date')
        ax.set_ylabel('Price ($)')
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.xticks(rotation=45)
        plt.tight_layout()
        
        plot_path = f"{save_path}price_chart.png"
        plt.savefig(plot_path, dpi=150, bbox_inches='tight')
        plt.close()
        plots_created.append(plot_path)
        print(f"✅ Created: {plot_path}")
    
    # Plot 2: Technical Indicators
    if all(col in df.columns for col in ['RSI_14', 'MACD_Line', 'MACD_Signal']):
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))
        
        # RSI subplot
        ax1.plot(df.index, df['RSI_14'], 'purple', linewidth=2)
        ax1.axhline(y=70, color='r', linestyle='--', alpha=0.7, label='Overbought (70)')
        ax1.axhline(y=30, color='g', linestyle='--', alpha=0.7, label='Oversold (30)')
        ax1.fill_between(df.index, 30, 70, alpha=0.1, color='gray')
        ax1.set_title('RSI (14) Indicator', fontweight='bold')
        ax1.set_ylabel('RSI')
        ax1.set_ylim(0, 100)
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # MACD subplot
        ax2.plot(df.index, df['MACD_Line'], 'b-', label='MACD Line')
        ax2.plot(df.index, df['MACD_Signal'], 'r-', label='Signal Line')
        if 'MACD_Histogram' in df.columns:
            ax2.bar(df.index, df['MACD_Histogram'], alpha=0.3, label='Histogram')
        ax2.axhline(y=0, color='k', linestyle='-', alpha=0.3)
        ax2.set_title('MACD Indicator', fontweight='bold')
        ax2.set_xlabel('Date')
        ax2.set_ylabel('MACD')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        plt.xticks(rotation=45)
        plt.tight_layout()
        
        plot_path = f"{save_path}technical_indicators.png"
        plt.savefig(plot_path, dpi=150, bbox_inches='tight')
        plt.close()
        plots_created.append(plot_path)
        print(f"✅ Created: {plot_path}")
    
    # Plot 3: Portfolio Performance (if backtest results available)
    if backtest_result and 'portfolio_values' in backtest_result:
        fig, ax = plt.subplots(figsize=(14, 6))
        
        portfolio_series = pd.Series(backtest_result['portfolio_values'], index=df.index)
        ax.plot(portfolio_series.index, portfolio_series.values, 'b-', linewidth=3, label='Portfolio Value')
        ax.axhline(y=backtest_result['initial_capital'], color='r', linestyle='--', alpha=0.7, label='Initial Capital')
        
        # Calculate and plot drawdown
        peak = portfolio_series.expanding().max()
        drawdown = (portfolio_series - peak) / peak
        ax2 = ax.twinx()
        ax2.fill_between(drawdown.index, drawdown * 100, 0, color='red', alpha=0.3, label='Drawdown %')
        ax2.set_ylabel('Drawdown (%)', color='red')
        
        ax.set_title(f'Portfolio Performance - Total Return: {backtest_result["total_return_pct"]:.2f}%', 
                    fontsize=16, fontweight='bold')
        ax.set_xlabel('Date')
        ax.set_ylabel('Portfolio Value ($)')
        ax.legend(loc='upper left')
        ax2.legend(loc='upper right')
        ax.grid(True, alpha=0.3)
        plt.xticks(rotation=45)
        plt.tight_layout()
        
        plot_path = f"{save_path}portfolio_performance.png"
        plt.savefig(plot_path, dpi=150, bbox_inches='tight')
        plt.close()
        plots_created.append(plot_path)
        print(f"✅ Created: {plot_path}")
    
    # Plot 4: Performance Metrics Summary
    if backtest_result:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
        
        # Metrics bar chart
        metrics = ['Total Return\n(%)', 'Win Rate\n(%)', 'Sharpe Ratio\n(x100)', 'Max Drawdown\n(%)']
        values = [
            backtest_result['total_return_pct'],
            backtest_result['win_rate'] * 100,
            backtest_result['sharpe_ratio'] * 100,
            abs(backtest_result['max_drawdown']) * 100
        ]
        colors = ['green', 'blue', 'orange', 'red']
        
        bars = ax1.bar(metrics, values, color=colors, alpha=0.7, edgecolor='black')
        ax1.set_title('Strategy Performance Metrics', fontweight='bold')
        ax1.set_ylabel('Value')
        ax1.grid(True, alpha=0.3, axis='y')
        
        # Add value labels
        for bar, value in zip(bars, values):
            height = bar.get_height()
            ax1.text(bar.get_x() + bar.get_width()/2., height + 0.1,
                    f'{value:.2f}', ha='center', va='bottom', fontweight='bold')
        
        # Trade analysis
        if 'trade_details' in backtest_result and backtest_result['trade_details']:
            trade_returns = [trade['return_pct'] * 100 for trade in backtest_result['trade_details']]
            trade_numbers = list(range(1, len(trade_returns) + 1))
            colors = ['green' if r > 0 else 'red' for r in trade_returns]
            
            ax2.bar(trade_numbers, trade_returns, color=colors, alpha=0.7, edgecolor='black')
            ax2.axhline(y=0, color='k', linestyle='-', alpha=0.5)
            ax2.set_title('Individual Trade Returns', fontweight='bold')
            ax2.set_xlabel('Trade Number')
            ax2.set_ylabel('Return (%)')
            ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        plot_path = f"{save_path}performance_summary.png"
        plt.savefig(plot_path, dpi=150, bbox_inches='tight')
        plt.close()
        plots_created.append(plot_path)
        print(f"✅ Created: {plot_path}")
    
    return plots_created

def display_plots_in_notebook(plot_paths):
    """Generate markdown to display plots in notebook"""
    markdown = "# 📊 Trading Analysis Results\n\n"
    
    plot_titles = {
        'price_chart.png': '## 📈 Price Chart with Trading Signals',
        'technical_indicators.png': '## 📊 Technical Indicators (RSI & MACD)',
        'portfolio_performance.png': '## 💰 Portfolio Performance',
        'performance_summary.png': '## 📋 Performance Summary'
    }
    
    for plot_path in plot_paths:
        filename = os.path.basename(plot_path)
        if filename in plot_titles:
            markdown += f"{plot_titles[filename]}\n\n"
            markdown += f"![{filename}]({plot_path})\n\n"
    
    return markdown

if __name__ == "__main__":
    print("📊 Plot Generator - Ready to create trading analysis charts")
    print("Usage: Import this module and call create_trading_dashboard(df, backtest_result)")
