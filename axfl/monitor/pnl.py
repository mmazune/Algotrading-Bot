"""
AXFL PnL Tracking

Aggregates daily trading performance from live trade logs.
"""

import os
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List
import pandas as pd


def daily_snapshot(trades_dir: str = "data/trades", out_dir: str = "reports") -> dict:
    """
    Generate daily PnL snapshot from live trade logs.
    
    Scans today's trade files (data/trades/live_*_<YYYYMMDD>.csv), aggregates
    performance by symbol and strategy, and writes CSV + Markdown reports.
    
    Args:
        trades_dir: Directory containing trade CSV files
        out_dir: Directory for output reports
        
    Returns:
        Dictionary with daily summary:
        {
            "date": "YYYY-MM-DD",
            "by_strategy": [{"name": str, "r": float, "trades": int, "wr": float, "pnl": float}, ...],
            "by_symbol": [{"symbol": str, "r": float, "trades": int, "wr": float, "pnl": float}, ...],
            "totals": {"r": float, "trades": int, "pnl": float}
        }
    """
    # Get today's date
    today = datetime.now().strftime("%Y%m%d")
    today_formatted = datetime.now().strftime("%Y-%m-%d")
    
    # Find today's trade files
    trades_path = Path(trades_dir)
    trades_path.mkdir(parents=True, exist_ok=True)
    
    pattern = f"live_*_{today}.csv"
    trade_files = list(trades_path.glob(pattern))
    
    # Initialize result
    result = {
        "date": today_formatted,
        "by_strategy": [],
        "by_symbol": [],
        "totals": {"r": 0.0, "trades": 0, "pnl": 0.0}
    }
    
    if not trade_files:
        # No trades today
        _write_reports(result, today, out_dir)
        return result
    
    # Load and aggregate trades
    all_trades = []
    for file in trade_files:
        try:
            df = pd.read_csv(file)
            if not df.empty:
                all_trades.append(df)
        except Exception:
            continue
    
    if not all_trades:
        _write_reports(result, today, out_dir)
        return result
    
    # Combine all trades
    trades_df = pd.concat(all_trades, ignore_index=True)
    
    # Calculate totals
    total_r = trades_df['r'].sum() if 'r' in trades_df.columns else 0.0
    total_trades = len(trades_df)
    total_pnl = trades_df['pnl'].sum() if 'pnl' in trades_df.columns else 0.0
    
    result["totals"] = {
        "r": round(total_r, 2),
        "trades": total_trades,
        "pnl": round(total_pnl, 2)
    }
    
    # Aggregate by strategy
    if 'strategy' in trades_df.columns:
        by_strategy = []
        for strategy in trades_df['strategy'].unique():
            strat_trades = trades_df[trades_df['strategy'] == strategy]
            strat_r = strat_trades['r'].sum() if 'r' in strat_trades.columns else 0.0
            strat_pnl = strat_trades['pnl'].sum() if 'pnl' in strat_trades.columns else 0.0
            
            # Calculate win rate
            wins = len(strat_trades[strat_trades['r'] > 0]) if 'r' in strat_trades.columns else 0
            wr = (wins / len(strat_trades) * 100) if len(strat_trades) > 0 else 0.0
            
            by_strategy.append({
                "name": strategy,
                "r": round(strat_r, 2),
                "trades": len(strat_trades),
                "wr": round(wr, 1),
                "pnl": round(strat_pnl, 2)
            })
        
        result["by_strategy"] = sorted(by_strategy, key=lambda x: x['r'], reverse=True)
    
    # Aggregate by symbol
    if 'symbol' in trades_df.columns:
        by_symbol = []
        for symbol in trades_df['symbol'].unique():
            sym_trades = trades_df[trades_df['symbol'] == symbol]
            sym_r = sym_trades['r'].sum() if 'r' in sym_trades.columns else 0.0
            sym_pnl = sym_trades['pnl'].sum() if 'pnl' in sym_trades.columns else 0.0
            
            # Calculate win rate
            wins = len(sym_trades[sym_trades['r'] > 0]) if 'r' in sym_trades.columns else 0
            wr = (wins / len(sym_trades) * 100) if len(sym_trades) > 0 else 0.0
            
            by_symbol.append({
                "symbol": symbol,
                "r": round(sym_r, 2),
                "trades": len(sym_trades),
                "wr": round(wr, 1),
                "pnl": round(sym_pnl, 2)
            })
        
        result["by_symbol"] = sorted(by_symbol, key=lambda x: x['r'], reverse=True)
    
    # Write reports
    _write_reports(result, today, out_dir)
    
    return result


def _write_reports(data: dict, date_str: str, out_dir: str) -> None:
    """Write CSV and Markdown reports."""
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    
    # Write CSV
    csv_file = out_path / f"pnl_{date_str}.csv"
    with open(csv_file, 'w') as f:
        f.write("type,name,r,trades,win_rate,pnl\n")
        
        # Strategy rows
        for item in data['by_strategy']:
            f.write(f"strategy,{item['name']},{item['r']},{item['trades']},{item['wr']},{item['pnl']}\n")
        
        # Symbol rows
        for item in data['by_symbol']:
            f.write(f"symbol,{item['symbol']},{item['r']},{item['trades']},{item['wr']},{item['pnl']}\n")
        
        # Totals
        totals = data['totals']
        f.write(f"total,ALL,{totals['r']},{totals['trades']},N/A,{totals['pnl']}\n")
    
    # Write Markdown
    md_file = out_path / f"pnl_{date_str}.md"
    with open(md_file, 'w') as f:
        f.write(f"# AXFL Daily PnL Report - {data['date']}\n\n")
        
        # Totals section
        totals = data['totals']
        f.write("## Summary\n\n")
        f.write(f"- **Total R**: {totals['r']}\n")
        f.write(f"- **Total Trades**: {totals['trades']}\n")
        f.write(f"- **Total PnL**: ${totals['pnl']}\n\n")
        
        # By Strategy
        if data['by_strategy']:
            f.write("## By Strategy\n\n")
            f.write("| Strategy | R | Trades | Win Rate | PnL |\n")
            f.write("|----------|---|--------|----------|-----|\n")
            for item in data['by_strategy']:
                f.write(f"| {item['name']} | {item['r']} | {item['trades']} | {item['wr']}% | ${item['pnl']} |\n")
            f.write("\n")
        
        # By Symbol
        if data['by_symbol']:
            f.write("## By Symbol\n\n")
            f.write("| Symbol | R | Trades | Win Rate | PnL |\n")
            f.write("|--------|---|--------|----------|-----|\n")
            for item in data['by_symbol']:
                f.write(f"| {item['symbol']} | {item['r']} | {item['trades']} | {item['wr']}% | ${item['pnl']} |\n")
            f.write("\n")
        
        if totals['trades'] == 0:
            f.write("*No trades recorded for this date.*\n")
