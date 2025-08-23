#!/usr/bin/env python3
"""
Comprehensive Plot Generator for Financial Analysis
Creates extensive visualization suite for trading strategy analysis
"""

import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import seaborn as sns
import os
from datetime import datetime

# Set style
plt.style.use('default')
sns.set_palette("husl")

def create_comprehensive_trading_dashboard(df, backtest_result=None, save_path="plots/"):
    """
    Creates comprehensive trading analysis plots (12+ visualizations)
    """
    
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
    
    # 1. COMPREHENSIVE PRICE CHART WITH SIGNALS
    if all(col in df.columns for col in ['Close', 'SMA_20', 'SMA_50']):
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 12), gridspec_kw={'height_ratios': [3, 1]})
        
        # Main price plot
        ax1.plot(df.index, df['Close'], 'k-', linewidth=2, label='Close Price', alpha=0.8)
        ax1.plot(df.index, df['SMA_20'], 'blue', alpha=0.7, label='SMA 20')
        ax1.plot(df.index, df['SMA_50'], 'red', alpha=0.7, label='SMA 50')
        
        # Bollinger Bands if available
        if all(col in df.columns for col in ['BB_Upper', 'BB_Lower', 'BB_Middle']):
            ax1.plot(df.index, df['BB_Upper'], 'gray', alpha=0.5, linestyle='--', label='BB Upper')
            ax1.plot(df.index, df['BB_Lower'], 'gray', alpha=0.5, linestyle='--', label='BB Lower')
            ax1.fill_between(df.index, df['BB_Lower'], df['BB_Upper'], alpha=0.1, color='gray')
        
        # Trading signals
        if 'Optimized_Trade_Signal' in df.columns:
            buy_signals = df[df['Optimized_Trade_Signal'] == 1]
            sell_signals = df[df['Optimized_Trade_Signal'] == -1]
            
            if len(buy_signals) > 0:
                ax1.scatter(buy_signals.index, buy_signals['Close'], 
                           marker='^', color='green', s=100, label='Buy Signal', zorder=5)
            if len(sell_signals) > 0:
                ax1.scatter(sell_signals.index, sell_signals['Close'], 
                           marker='v', color='red', s=100, label='Sell Signal', zorder=5)
        
        ax1.set_title('AAPL: Price Action with Technical Indicators & Trading Signals', fontsize=16)
        ax1.set_ylabel('Price ($)')
        ax1.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        ax1.grid(True, alpha=0.3)
        
        # Volume subplot
        if 'Volume' in df.columns:
            ax2.bar(df.index, df['Volume'], alpha=0.6, color='lightblue', width=1)
            ax2.set_title('Trading Volume')
            ax2.set_ylabel('Volume')
            ax2.set_xlabel('Date')
        else:
            ax2.text(0.5, 0.5, 'Volume data not available', 
                    transform=ax2.transAxes, ha='center', va='center', fontsize=12)
            ax2.set_title('Volume (Not Available)')
        
        plt.tight_layout()
        path = f"{save_path}01_comprehensive_price_chart.png"
        plt.savefig(path, dpi=300, bbox_inches='tight')
        plt.close()
        plots_created.append(path)
        print(f"✅ Created: {path}")
    
    # 2. TECHNICAL INDICATORS DASHBOARD
    fig, axes = plt.subplots(3, 1, figsize=(16, 14))
    
    # RSI
    if 'RSI_14' in df.columns:
        axes[0].plot(df.index, df['RSI_14'], 'purple', linewidth=2, label='RSI (14)')
        axes[0].axhline(y=70, color='red', linestyle='--', alpha=0.7, label='Overbought (70)')
        axes[0].axhline(y=30, color='green', linestyle='--', alpha=0.7, label='Oversold (30)')
        axes[0].fill_between(df.index, 30, 70, alpha=0.1, color='gray')
        axes[0].set_ylim(0, 100)
        axes[0].set_title('Relative Strength Index (RSI)', fontsize=14)
        axes[0].set_ylabel('RSI')
        axes[0].legend()
        axes[0].grid(True, alpha=0.3)
    
    # MACD
    if all(col in df.columns for col in ['MACD_Line', 'MACD_Signal']):
        axes[1].plot(df.index, df['MACD_Line'], 'blue', linewidth=2, label='MACD Line')
        axes[1].plot(df.index, df['MACD_Signal'], 'red', linewidth=2, label='Signal Line')
        if 'MACD_Histogram' in df.columns:
            axes[1].bar(df.index, df['MACD_Histogram'], alpha=0.6, color='gray', label='Histogram', width=1)
        axes[1].axhline(y=0, color='black', linestyle='-', alpha=0.5)
        axes[1].set_title('MACD Indicator', fontsize=14)
        axes[1].set_ylabel('MACD')
        axes[1].legend()
        axes[1].grid(True, alpha=0.3)
    
    # Daily Returns
    if 'Daily_Return' in df.columns:
        daily_returns_pct = df['Daily_Return'] * 100
        axes[2].plot(df.index, daily_returns_pct, alpha=0.7, color='orange', linewidth=1)
        axes[2].axhline(y=0, color='black', linestyle='-', alpha=0.5)
        axes[2].fill_between(df.index, daily_returns_pct, 0, 
                            where=(daily_returns_pct > 0), alpha=0.3, color='green', interpolate=True)
        axes[2].fill_between(df.index, daily_returns_pct, 0, 
                            where=(daily_returns_pct < 0), alpha=0.3, color='red', interpolate=True)
        axes[2].set_title('Daily Returns (%)', fontsize=14)
        axes[2].set_ylabel('Return (%)')
        axes[2].set_xlabel('Date')
        axes[2].grid(True, alpha=0.3)
    
    plt.tight_layout()
    path = f"{save_path}02_technical_indicators_dashboard.png"
    plt.savefig(path, dpi=300, bbox_inches='tight')
    plt.close()
    plots_created.append(path)
    print(f"✅ Created: {path}")
    
    # 3. PORTFOLIO PERFORMANCE & DRAWDOWN
    if backtest_result:
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10))
        
        # Portfolio value
        portfolio_series = backtest_result.get('portfolio_values', [backtest_result['initial_capital']] * len(df))
        ax1.plot(df.index, portfolio_series, 'blue', linewidth=3, label='Portfolio Value')
        ax1.axhline(y=backtest_result['initial_capital'], color='red', linestyle='--', 
                   alpha=0.7, label=f"Initial Capital (${backtest_result['initial_capital']:,})")
        
        # Add trade markers
        if 'trade_details' in backtest_result and len(backtest_result['trade_details']) > 0:
            for trade in backtest_result['trade_details']:
                # Map the actual trade structure
                entry_date = trade['entry_date']
                exit_date = trade['exit_date']
                entry_price = trade['entry_price']
                exit_price = trade['exit_price']
                
                # Find portfolio values at trade dates
                try:
                    entry_idx = df.index.get_loc(entry_date)
                    exit_idx = df.index.get_loc(exit_date)
                    
                    # Plot entry and exit points
                    ax1.scatter(entry_date, entry_price, 
                               marker='^', color='green', s=150, alpha=0.9, zorder=5, 
                               label='Trade Entry' if trade == backtest_result['trade_details'][0] else '')
                    ax1.scatter(exit_date, exit_price, 
                               marker='v', color='red', s=150, alpha=0.9, zorder=5,
                               label='Trade Exit' if trade == backtest_result['trade_details'][0] else '')
                               
                    # Draw line connecting entry and exit
                    ax1.plot([entry_date, exit_date], [entry_price, exit_price], 
                            'purple', linewidth=2, alpha=0.7, linestyle='--')
                    
                except (KeyError, ValueError):
                    # Skip if date not found in index
                    pass
        
        ax1.set_title('Portfolio Performance Over Time', fontsize=16)
        ax1.set_ylabel('Portfolio Value ($)')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # Drawdown
        peak = pd.Series(portfolio_series).expanding().max()
        drawdown = (pd.Series(portfolio_series) - peak) / peak * 100
        ax2.fill_between(df.index, drawdown, 0, alpha=0.3, color='red', label='Drawdown')
        ax2.plot(df.index, drawdown, color='darkred', linewidth=2)
        ax2.set_title('Portfolio Drawdown (%)', fontsize=14)
        ax2.set_ylabel('Drawdown (%)')
        ax2.set_xlabel('Date')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        path = f"{save_path}03_portfolio_performance.png"
        plt.savefig(path, dpi=300, bbox_inches='tight')
        plt.close()
        plots_created.append(path)
        print(f"✅ Created: {path}")
    
    # 4. PERFORMANCE METRICS SUMMARY
    if backtest_result:
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
        
        # Performance metrics bar chart
        metrics = {
            'Total Return (%)': backtest_result['total_return_pct'],
            'Buy & Hold (%)': backtest_result.get('buy_hold_return', 0),
            'Max Drawdown (%)': abs(backtest_result['max_drawdown']) * 100,
            'Win Rate (%)': backtest_result['win_rate'] * 100,
            'Avg Return/Trade (%)': backtest_result.get('avg_return_per_trade', 0) * 100,
            'Sharpe Ratio': backtest_result.get('sharpe_ratio', 0)
        }
        
        colors = ['green' if v > 0 else 'red' if 'Return' in k or 'Drawdown' in k else 'blue' 
                  for k, v in metrics.items()]
        
        bars = ax1.bar(range(len(metrics)), list(metrics.values()), color=colors, alpha=0.7)
        ax1.set_xticks(range(len(metrics)))
        ax1.set_xticklabels(list(metrics.keys()), rotation=45, ha='right')
        ax1.set_title('Performance Metrics Summary')
        ax1.set_ylabel('Value')
        ax1.grid(True, alpha=0.3)
        
        # Add value labels on bars
        for bar, value in zip(bars, metrics.values()):
            height = bar.get_height()
            ax1.text(bar.get_x() + bar.get_width()/2, height + (0.01 * max(metrics.values())), 
                    f'{value:.2f}', ha='center', va='bottom', fontsize=9)
        
        # Trade returns distribution
        if 'trade_details' in backtest_result and len(backtest_result['trade_details']) > 0:
            returns = [trade['return_pct'] * 100 for trade in backtest_result['trade_details']]
            ax2.hist(returns, bins=max(5, len(returns)//2), alpha=0.7, color='skyblue', edgecolor='black')
            ax2.axvline(x=0, color='red', linestyle='--', alpha=0.7, label='Break-even')
            ax2.set_title('Distribution of Trade Returns')
            ax2.set_xlabel('Return per Trade (%)')
            ax2.set_ylabel('Frequency')
            ax2.legend()
            ax2.grid(True, alpha=0.3)
        else:
            ax2.text(0.5, 0.5, 'No completed trades', 
                    transform=ax2.transAxes, ha='center', va='center', fontsize=12)
            ax2.set_title('Distribution of Trade Returns')
        
        # Monthly returns heatmap
        if 'Daily_Return' in df.columns:
            monthly_returns = df['Daily_Return'].resample('M').apply(lambda x: (1 + x).prod() - 1) * 100
            months = [d.strftime('%b %Y') for d in monthly_returns.index]
            colors_monthly = ['green' if r > 0 else 'red' for r in monthly_returns]
            
            bars = ax3.bar(range(len(monthly_returns)), monthly_returns, color=colors_monthly, alpha=0.7)
            ax3.set_xticks(range(len(monthly_returns)))
            ax3.set_xticklabels(months, rotation=45, ha='right')
            ax3.axhline(y=0, color='black', linestyle='-', alpha=0.5)
            ax3.set_title('Monthly Returns (%)')
            ax3.set_ylabel('Return (%)')
            ax3.grid(True, alpha=0.3)
            
            # Add value labels
            for i, (bar, value) in enumerate(zip(bars, monthly_returns)):
                height = bar.get_height()
                ax3.text(bar.get_x() + bar.get_width()/2, height + (0.1 if height >= 0 else -0.3), 
                        f'{value:.1f}%', ha='center', va='bottom' if height >= 0 else 'top', fontsize=8)
        
        # Risk metrics
        if 'Daily_Return' in df.columns:
            returns = df['Daily_Return'].dropna()
            risk_metrics = {
                'Volatility (%)': returns.std() * np.sqrt(252) * 100,
                'Skewness': returns.skew(),
                'Kurtosis': returns.kurtosis(),
                'VaR 95% (%)': np.percentile(returns, 5) * 100,
                'Max Daily Loss (%)': returns.min() * 100,
                'Max Daily Gain (%)': returns.max() * 100
            }
            
            bars = ax4.bar(range(len(risk_metrics)), list(risk_metrics.values()), 
                          alpha=0.7, color='orange')
            ax4.set_xticks(range(len(risk_metrics)))
            ax4.set_xticklabels(list(risk_metrics.keys()), rotation=45, ha='right')
            ax4.set_title('Risk Metrics')
            ax4.set_ylabel('Value')
            ax4.grid(True, alpha=0.3)
            
            # Add value labels
            for i, (bar, value) in enumerate(zip(bars, risk_metrics.values())):
                height = bar.get_height()
                ax4.text(bar.get_x() + bar.get_width()/2, height + (0.1 if height >= 0 else -0.3), 
                        f'{value:.2f}', ha='center', va='bottom' if height >= 0 else 'top', fontsize=8)
        
        plt.tight_layout()
        path = f"{save_path}04_performance_summary.png"
        plt.savefig(path, dpi=300, bbox_inches='tight')
        plt.close()
        plots_created.append(path)
        print(f"✅ Created: {path}")
    
    # 5. SIGNAL ANALYSIS DASHBOARD
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
    
    # Signal distribution
    if 'Signal' in df.columns:
        signal_counts = df['Signal'].value_counts().sort_index()
        ax1.bar(signal_counts.index, signal_counts.values, alpha=0.7, color='skyblue')
        ax1.set_title('Signal Strength Distribution')
        ax1.set_xlabel('Signal Score')
        ax1.set_ylabel('Frequency')
        ax1.grid(True, alpha=0.3)
        
        # Add percentage labels
        total_signals = signal_counts.sum()
        for i, (score, count) in enumerate(signal_counts.items()):
            pct = (count / total_signals) * 100
            ax1.text(score, count + 1, f'{pct:.1f}%', ha='center', va='bottom')
    
    # Signal correlation matrix
    signal_cols = [col for col in df.columns if 'Signal' in col and col != 'Signal']
    if len(signal_cols) >= 2:
        corr_matrix = df[signal_cols].corr()
        im = ax2.imshow(corr_matrix, cmap='coolwarm', vmin=-1, vmax=1, aspect='auto')
        ax2.set_xticks(range(len(signal_cols)))
        ax2.set_yticks(range(len(signal_cols)))
        ax2.set_xticklabels([col.replace('_Signal', '') for col in signal_cols], rotation=45)
        ax2.set_yticklabels([col.replace('_Signal', '') for col in signal_cols])
        ax2.set_title('Signal Correlation Matrix')
        
        # Add correlation values
        for i in range(len(signal_cols)):
            for j in range(len(signal_cols)):
                ax2.text(j, i, f'{corr_matrix.iloc[i, j]:.2f}', 
                        ha='center', va='center', color='white' if abs(corr_matrix.iloc[i, j]) > 0.5 else 'black')
        
        plt.colorbar(im, ax=ax2, shrink=0.8)
    
    # Rolling correlation with price
    if 'Daily_Return' in df.columns and 'RSI_14' in df.columns:
        rolling_corr = df['Daily_Return'].rolling(20).corr(df['RSI_14'])
        ax3.plot(df.index, rolling_corr, color='green', linewidth=2)
        ax3.axhline(y=0, color='black', linestyle='--', alpha=0.5)
        ax3.set_title('20-Day Rolling Correlation: Returns vs RSI')
        ax3.set_ylabel('Correlation')
        ax3.set_xlabel('Date')
        ax3.grid(True, alpha=0.3)
    
    # Signal timing analysis
    if 'Optimized_Trade_Signal' in df.columns:
        # Count signals by day of week
        df_with_dow = df.copy()
        df_with_dow['DayOfWeek'] = df_with_dow.index.day_name()
        
        signal_by_dow = df_with_dow.groupby('DayOfWeek')['Optimized_Trade_Signal'].apply(
            lambda x: (x != 0).sum()).reindex(['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'])
        
        ax4.bar(range(len(signal_by_dow)), signal_by_dow.values, alpha=0.7, color='lightcoral')
        ax4.set_xticks(range(len(signal_by_dow)))
        ax4.set_xticklabels(signal_by_dow.index, rotation=45)
        ax4.set_title('Trading Signals by Day of Week')
        ax4.set_ylabel('Number of Signals')
        ax4.grid(True, alpha=0.3)
        
        # Add value labels
        for i, value in enumerate(signal_by_dow.values):
            ax4.text(i, value + 0.1, str(value), ha='center', va='bottom')
    
    plt.tight_layout()
    path = f"{save_path}05_signal_analysis.png"
    plt.savefig(path, dpi=300, bbox_inches='tight')
    plt.close()
    plots_created.append(path)
    print(f"✅ Created: {path}")
    
    # 6. MARKET REGIMES & VOLATILITY ANALYSIS
    fig, axes = plt.subplots(3, 1, figsize=(16, 14))
    
    # Price with volatility regimes
    axes[0].plot(df.index, df['Close'], color='black', linewidth=2, label='Close Price')
    
    if 'Daily_Return' in df.columns:
        rolling_vol = df['Daily_Return'].rolling(20).std() * np.sqrt(252) * 100
        high_vol_threshold = rolling_vol.quantile(0.75)
        high_vol_periods = rolling_vol > high_vol_threshold
        
        # Highlight high volatility periods
        for i, (date, is_high_vol) in enumerate(high_vol_periods.items()):
            if is_high_vol and i < len(df) - 1:
                next_date = df.index[min(i + 1, len(df) - 1)]
                axes[0].axvspan(date, next_date, alpha=0.2, color='red')
    
    axes[0].set_title('Price Action with High Volatility Periods (Red Shading)')
    axes[0].set_ylabel('Price ($)')
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)
    
    # Rolling volatility
    if 'Daily_Return' in df.columns:
        rolling_vol = df['Daily_Return'].rolling(20).std() * np.sqrt(252) * 100
        axes[1].plot(df.index, rolling_vol, color='red', linewidth=2, label='20-Day Rolling Volatility')
        axes[1].axhline(y=rolling_vol.mean(), color='blue', linestyle='--', 
                       alpha=0.7, label=f'Average Volatility ({rolling_vol.mean():.1f}%)')
        axes[1].fill_between(df.index, 0, rolling_vol, alpha=0.3, color='red')
        axes[1].set_title('Rolling Volatility (20-Day, Annualized %)')
        axes[1].set_ylabel('Volatility (%)')
        axes[1].legend()
        axes[1].grid(True, alpha=0.3)
    
    # Trade performance scatter
    if backtest_result and 'trade_details' in backtest_result and len(backtest_result['trade_details']) > 0:
        trades = backtest_result['trade_details']
        trade_dates = [trade['exit_date'] for trade in trades]
        trade_returns = [trade['return_pct'] * 100 for trade in trades]
        
        colors = ['green' if r > 0 else 'red' for r in trade_returns]
        sizes = [abs(r) * 10 + 20 for r in trade_returns]  # Size based on magnitude
        
        scatter = axes[2].scatter(trade_dates, trade_returns, c=colors, s=sizes, alpha=0.7)
        axes[2].axhline(y=0, color='black', linestyle='-', alpha=0.5)
        axes[2].set_title('Individual Trade Performance (Size ∝ Return Magnitude)')
        axes[2].set_ylabel('Trade Return (%)')
        axes[2].set_xlabel('Date')
        axes[2].grid(True, alpha=0.3)
        
        # Add annotations for all trades (since we likely have few)
        for i, (date, ret) in enumerate(zip(trade_dates, trade_returns)):
            axes[2].annotate(f'{ret:.1f}%', (date, ret), 
                           xytext=(5, 5), textcoords='offset points', fontsize=9)
    else:
        # Show message if no trades
        axes[2].text(0.5, 0.5, 'No completed trades to display', 
                    transform=axes[2].transAxes, ha='center', va='center', fontsize=12)
        axes[2].set_title('Individual Trade Performance')
        axes[2].set_ylabel('Trade Return (%)')
        axes[2].set_xlabel('Date')
    
    plt.tight_layout()
    path = f"{save_path}06_market_regimes.png"
    plt.savefig(path, dpi=300, bbox_inches='tight')
    plt.close()
    plots_created.append(path)
    print(f"✅ Created: {path}")
    
    # Print summary
    print(f"\n🎉 COMPREHENSIVE ANALYSIS COMPLETE!")
    print(f"📊 Created {len(plots_created)} detailed visualizations:")
    for i, path in enumerate(plots_created, 1):
        filename = path.split('/')[-1]
        print(f"   {i:2d}. {filename}")
    
    print(f"\n📁 All plots saved in: {save_path}")
    print(f"🔍 View them by opening the 'plots' folder in VS Code")
    
    return plots_created

# Backward compatibility function
def create_trading_dashboard(df, backtest_result=None, save_path="plots/"):
    """Wrapper for backward compatibility"""
    return create_comprehensive_trading_dashboard(df, backtest_result, save_path)
