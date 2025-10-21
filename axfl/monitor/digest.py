"""
Daily PnL Digest Generator

Generates comprehensive daily trading reports with:
- CSV summary
- Markdown report
- PNG P&L chart
- Optional Discord webhook notification
"""

import os
import json
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
from datetime import datetime, date
from typing import Dict, List, Optional
import requests


def load_trades_from_jsonl(log_file: Path) -> List[Dict]:
    """
    Load trades from portfolio JSONL log file.
    
    Args:
        log_file: Path to portfolio_live_YYYYMMDD.jsonl
    
    Returns:
        List of trade dicts with all fields
    """
    trades = []
    
    if not log_file.exists():
        return trades
    
    with open(log_file, 'r') as f:
        for line in f:
            try:
                status = json.loads(line.strip())
                
                # Extract trades from engines roster
                engines = status.get('engines', [])
                for eng in engines:
                    eng_trades = eng.get('trades', [])
                    for trade in eng_trades:
                        # Add symbol and strategy context
                        trade['symbol'] = eng.get('symbol', 'UNKNOWN')
                        trade['strategy'] = eng.get('strategy', 'UNKNOWN')
                        trades.append(trade)
                        
            except json.JSONDecodeError:
                continue
    
    # Deduplicate trades by unique key (entry_time + symbol + strategy)
    seen = set()
    unique_trades = []
    for trade in trades:
        key = (
            trade.get('entry_time', ''),
            trade.get('symbol', ''),
            trade.get('strategy', '')
        )
        if key not in seen:
            seen.add(key)
            unique_trades.append(trade)
    
    return unique_trades


def compute_daily_stats(trades: List[Dict], target_date: date) -> Dict:
    """
    Compute daily trading statistics.
    
    Args:
        trades: List of trade dicts
        target_date: Date to analyze
    
    Returns:
        Dict with daily stats
    """
    # Filter trades to target date
    daily_trades = []
    for trade in trades:
        exit_time_str = trade.get('exit_time', '')
        if exit_time_str:
            try:
                exit_dt = pd.to_datetime(exit_time_str)
                if exit_dt.date() == target_date:
                    daily_trades.append(trade)
            except:
                continue
    
    if not daily_trades:
        return {
            'date': str(target_date),
            'total_trades': 0,
            'winners': 0,
            'losers': 0,
            'win_rate': 0.0,
            'total_r': 0.0,
            'total_pnl': 0.0,
            'avg_r_per_trade': 0.0,
            'max_r_win': 0.0,
            'max_r_loss': 0.0,
            'by_symbol': {},
            'by_strategy': {},
            'trades': []
        }
    
    # Overall stats
    total_trades = len(daily_trades)
    winners = sum(1 for t in daily_trades if t.get('r', 0) > 0)
    losers = sum(1 for t in daily_trades if t.get('r', 0) < 0)
    win_rate = winners / total_trades if total_trades > 0 else 0.0
    
    total_r = sum(t.get('r', 0) for t in daily_trades)
    total_pnl = sum(t.get('pnl', 0) for t in daily_trades)
    avg_r = total_r / total_trades if total_trades > 0 else 0.0
    
    r_values = [t.get('r', 0) for t in daily_trades]
    max_r_win = max(r_values) if r_values else 0.0
    max_r_loss = min(r_values) if r_values else 0.0
    
    # By symbol breakdown
    by_symbol = {}
    for trade in daily_trades:
        sym = trade.get('symbol', 'UNKNOWN')
        if sym not in by_symbol:
            by_symbol[sym] = {'trades': 0, 'r': 0.0, 'pnl': 0.0}
        by_symbol[sym]['trades'] += 1
        by_symbol[sym]['r'] += trade.get('r', 0)
        by_symbol[sym]['pnl'] += trade.get('pnl', 0)
    
    # By strategy breakdown
    by_strategy = {}
    for trade in daily_trades:
        strat = trade.get('strategy', 'UNKNOWN')
        if strat not in by_strategy:
            by_strategy[strat] = {'trades': 0, 'r': 0.0, 'pnl': 0.0}
        by_strategy[strat]['trades'] += 1
        by_strategy[strat]['r'] += trade.get('r', 0)
        by_strategy[strat]['pnl'] += trade.get('pnl', 0)
    
    return {
        'date': str(target_date),
        'total_trades': total_trades,
        'winners': winners,
        'losers': losers,
        'win_rate': round(win_rate * 100, 1),
        'total_r': round(total_r, 2),
        'total_pnl': round(total_pnl, 2),
        'avg_r_per_trade': round(avg_r, 2),
        'max_r_win': round(max_r_win, 2),
        'max_r_loss': round(max_r_loss, 2),
        'by_symbol': by_symbol,
        'by_strategy': by_strategy,
        'trades': daily_trades
    }


def generate_csv_report(stats: Dict, output_path: Path):
    """
    Generate CSV summary of daily trades.
    
    Args:
        stats: Daily stats dict from compute_daily_stats()
        output_path: Path to write CSV file
    """
    if not stats['trades']:
        # Empty CSV if no trades
        with open(output_path, 'w') as f:
            f.write("date,symbol,strategy,side,entry,exit,r,pnl,reason\n")
        return
    
    rows = []
    for trade in stats['trades']:
        rows.append({
            'date': stats['date'],
            'symbol': trade.get('symbol', ''),
            'strategy': trade.get('strategy', ''),
            'side': trade.get('side', ''),
            'entry': trade.get('entry', 0),
            'exit': trade.get('exit', 0),
            'r': round(trade.get('r', 0), 2),
            'pnl': round(trade.get('pnl', 0), 2),
            'reason': trade.get('reason', '')
        })
    
    df = pd.DataFrame(rows)
    df.to_csv(output_path, index=False)
    print(f"  ✓ CSV report: {output_path}")


def generate_markdown_report(stats: Dict, output_path: Path):
    """
    Generate Markdown summary report.
    
    Args:
        stats: Daily stats dict from compute_daily_stats()
        output_path: Path to write Markdown file
    """
    lines = []
    lines.append(f"# Daily Trading Report - {stats['date']}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Total Trades**: {stats['total_trades']}")
    lines.append(f"- **Winners**: {stats['winners']} ({stats['win_rate']:.1f}%)")
    lines.append(f"- **Losers**: {stats['losers']}")
    lines.append(f"- **Total R**: {stats['total_r']:+.2f}R")
    lines.append(f"- **Total PnL**: ${stats['total_pnl']:+,.2f}")
    lines.append(f"- **Avg R/Trade**: {stats['avg_r_per_trade']:+.2f}R")
    lines.append(f"- **Best Trade**: {stats['max_r_win']:+.2f}R")
    lines.append(f"- **Worst Trade**: {stats['max_r_loss']:+.2f}R")
    lines.append("")
    
    # By symbol
    if stats['by_symbol']:
        lines.append("## By Symbol")
        lines.append("")
        lines.append("| Symbol | Trades | Total R | PnL |")
        lines.append("|--------|--------|---------|-----|")
        for sym, data in sorted(stats['by_symbol'].items()):
            lines.append(f"| {sym} | {data['trades']} | {data['r']:+.2f}R | ${data['pnl']:+,.2f} |")
        lines.append("")
    
    # By strategy
    if stats['by_strategy']:
        lines.append("## By Strategy")
        lines.append("")
        lines.append("| Strategy | Trades | Total R | PnL |")
        lines.append("|----------|--------|---------|-----|")
        for strat, data in sorted(stats['by_strategy'].items()):
            lines.append(f"| {strat} | {data['trades']} | {data['r']:+.2f}R | ${data['pnl']:+,.2f} |")
        lines.append("")
    
    # Trade log
    if stats['trades']:
        lines.append("## Trade Log")
        lines.append("")
        lines.append("| Symbol | Strategy | Side | Entry | Exit | R | PnL | Reason |")
        lines.append("|--------|----------|------|-------|------|---|-----|--------|")
        for trade in stats['trades']:
            lines.append(
                f"| {trade.get('symbol', '')} "
                f"| {trade.get('strategy', '')} "
                f"| {trade.get('side', '')} "
                f"| {trade.get('entry', 0):.4f} "
                f"| {trade.get('exit', 0):.4f} "
                f"| {trade.get('r', 0):+.2f}R "
                f"| ${trade.get('pnl', 0):+.2f} "
                f"| {trade.get('reason', '')} |"
            )
        lines.append("")
    
    lines.append("---")
    lines.append(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}*")
    
    with open(output_path, 'w') as f:
        f.write('\n'.join(lines))
    
    print(f"  ✓ Markdown report: {output_path}")


def generate_pnl_chart(stats: Dict, output_path: Path):
    """
    Generate PNG chart of cumulative P&L.
    
    Args:
        stats: Daily stats dict from compute_daily_stats()
        output_path: Path to write PNG file
    """
    if not stats['trades']:
        # Empty chart
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.text(0.5, 0.5, 'No trades today', ha='center', va='center', fontsize=16)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  ✓ Chart: {output_path}")
        return
    
    # Build cumulative R series
    trades_sorted = sorted(stats['trades'], key=lambda t: t.get('exit_time', ''))
    
    cumulative_r = []
    cum = 0.0
    for trade in trades_sorted:
        cum += trade.get('r', 0)
        cumulative_r.append(cum)
    
    # Plot
    fig, ax = plt.subplots(figsize=(12, 6))
    
    x = range(len(cumulative_r))
    ax.plot(x, cumulative_r, marker='o', linewidth=2, markersize=6, color='#2563eb')
    ax.axhline(0, color='gray', linestyle='--', linewidth=1, alpha=0.5)
    ax.grid(True, alpha=0.3)
    
    # Color fill
    ax.fill_between(x, 0, cumulative_r, alpha=0.2, 
                     color='green' if cumulative_r[-1] >= 0 else 'red')
    
    ax.set_xlabel('Trade Number', fontsize=12)
    ax.set_ylabel('Cumulative R', fontsize=12)
    ax.set_title(f'Cumulative P&L - {stats["date"]}', fontsize=14, fontweight='bold')
    
    # Summary text
    summary_text = (
        f"Total: {stats['total_r']:+.2f}R  |  "
        f"Trades: {stats['total_trades']}  |  "
        f"Win Rate: {stats['win_rate']:.1f}%"
    )
    ax.text(0.5, 1.05, summary_text, 
            transform=ax.transAxes, ha='center', fontsize=11, 
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.3))
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    
    print(f"  ✓ Chart: {output_path}")


def send_discord_webhook(stats: Dict, webhook_url: str, chart_path: Optional[Path] = None):
    """
    Send digest summary to Discord webhook.
    
    Args:
        stats: Daily stats dict
        webhook_url: Discord webhook URL
        chart_path: Optional path to PNG chart to attach
    """
    # Build embed
    color = 0x10b981 if stats['total_r'] >= 0 else 0xef4444  # Green or red
    
    embed = {
        "title": f"📊 Daily Trading Report - {stats['date']}",
        "color": color,
        "fields": [
            {"name": "Total Trades", "value": str(stats['total_trades']), "inline": True},
            {"name": "Win Rate", "value": f"{stats['win_rate']:.1f}%", "inline": True},
            {"name": "Total R", "value": f"{stats['total_r']:+.2f}R", "inline": True},
            {"name": "Total PnL", "value": f"${stats['total_pnl']:+,.2f}", "inline": True},
            {"name": "Avg R/Trade", "value": f"{stats['avg_r_per_trade']:+.2f}R", "inline": True},
            {"name": "Best Trade", "value": f"{stats['max_r_win']:+.2f}R", "inline": True},
        ],
        "footer": {"text": "AXFL Portfolio Digest"},
        "timestamp": datetime.utcnow().isoformat()
    }
    
    # Add breakdown
    if stats['by_symbol']:
        symbol_summary = "\n".join([
            f"**{sym}**: {data['trades']} trades, {data['r']:+.2f}R"
            for sym, data in sorted(stats['by_symbol'].items())
        ])
        embed['fields'].append({"name": "By Symbol", "value": symbol_summary, "inline": False})
    
    if stats['by_strategy']:
        strategy_summary = "\n".join([
            f"**{strat}**: {data['trades']} trades, {data['r']:+.2f}R"
            for strat, data in sorted(stats['by_strategy'].items())
        ])
        embed['fields'].append({"name": "By Strategy", "value": strategy_summary, "inline": False})
    
    payload = {"embeds": [embed]}
    
    try:
        # Send webhook
        if chart_path and chart_path.exists():
            # Send with file attachment
            with open(chart_path, 'rb') as f:
                files = {'file': (chart_path.name, f, 'image/png')}
                response = requests.post(
                    webhook_url,
                    data={'payload_json': json.dumps(payload)},
                    files=files
                )
        else:
            # Send without attachment
            response = requests.post(webhook_url, json=payload)
        
        if response.status_code == 204:
            print(f"  ✓ Discord webhook sent successfully")
        else:
            print(f"  ⚠️  Discord webhook failed: {response.status_code}")
            
    except Exception as e:
        print(f"  ⚠️  Discord webhook error: {e}")


def generate_digest(
    date_str: str,
    logs_dir: Path = Path('logs'),
    reports_dir: Path = Path('reports'),
    discord_webhook: Optional[str] = None
):
    """
    Generate complete daily PnL digest.
    
    Args:
        date_str: Date in YYYYMMDD format (e.g., "20251020")
        logs_dir: Directory containing JSONL logs
        reports_dir: Directory to write reports
        discord_webhook: Optional Discord webhook URL
    """
    print(f"\n=== Generating Daily Digest for {date_str} ===\n")
    
    # Parse date
    try:
        target_date = datetime.strptime(date_str, '%Y%m%d').date()
    except ValueError:
        print(f"❌ Invalid date format: {date_str} (expected YYYYMMDD)")
        return
    
    # Load trades from log
    log_file = logs_dir / f"portfolio_live_{date_str}.jsonl"
    if not log_file.exists():
        print(f"⚠️  Log file not found: {log_file}")
        print("  No trades to report")
        return
    
    print(f"Loading trades from: {log_file}")
    trades = load_trades_from_jsonl(log_file)
    print(f"  Found {len(trades)} unique trades")
    
    # Compute stats
    stats = compute_daily_stats(trades, target_date)
    
    # Create reports directory
    reports_dir.mkdir(exist_ok=True)
    
    # Generate reports
    csv_path = reports_dir / f"pnl_{date_str}.csv"
    md_path = reports_dir / f"pnl_{date_str}.md"
    chart_path = reports_dir / f"pnl_{date_str}.png"
    
    generate_csv_report(stats, csv_path)
    generate_markdown_report(stats, md_path)
    generate_pnl_chart(stats, chart_path)
    
    # Send to Discord if webhook provided
    if discord_webhook:
        send_discord_webhook(stats, discord_webhook, chart_path)
    
    print(f"\n✓ Digest complete for {date_str}")
    print(f"  Total R: {stats['total_r']:+.2f}R")
    print(f"  Total PnL: ${stats['total_pnl']:+,.2f}")
    print(f"  Reports: {reports_dir}/pnl_{date_str}.*")


def intraday_digest(
    out_dir: str = "reports",
    since_hours: int = 6
) -> Dict:
    """
    Generate intraday PnL digest (lighter version for on-demand use).
    
    Args:
        out_dir: Output directory for reports
        since_hours: Look back N hours from now
    
    Returns:
        Dict with 'ok', 'date', 'png', 'totals'
    """
    from datetime import timedelta
    
    reports_dir = Path(out_dir)
    reports_dir.mkdir(exist_ok=True)
    
    today_str = datetime.now().strftime('%Y%m%d')
    now = datetime.now()
    since = now - timedelta(hours=since_hours)
    
    print(f"\n=== Intraday Digest (last {since_hours}h) ===\n")
    
    # Load trades from today's log
    logs_dir = Path('logs')
    log_file = logs_dir / f"portfolio_live_{today_str}.jsonl"
    
    if not log_file.exists():
        print(f"⚠️  No trades yet today: {log_file}")
        return {
            'ok': True,
            'date': today_str,
            'png': None,
            'totals': {'trades': 0, 'r': 0.0, 'pnl': 0.0}
        }
    
    # Load all trades
    all_trades = load_trades_from_jsonl(log_file)
    
    # Filter to since_hours window
    trades = []
    for trade in all_trades:
        time_closed = trade.get('time_closed')
        if time_closed:
            try:
                trade_time = pd.to_datetime(time_closed)
                if trade_time >= since:
                    trades.append(trade)
            except:
                pass
    
    print(f"Found {len(trades)} trades in last {since_hours}h")
    
    if not trades:
        print("  No trades to report")
        return {
            'ok': True,
            'date': today_str,
            'png': None,
            'totals': {'trades': 0, 'r': 0.0, 'pnl': 0.0}
        }
    
    # Compute stats
    stats = compute_daily_stats(trades, datetime.now().date())
    
    # Generate PNG chart only (lightweight)
    chart_path = reports_dir / f"intraday_pnl_{today_str}.png"
    generate_pnl_chart(stats, chart_path)
    
    # Send to Discord if webhook configured
    discord_webhook = os.getenv('DISCORD_WEBHOOK_URL')
    if discord_webhook:
        try:
            send_discord_webhook(stats, discord_webhook, chart_path)
            print(f"  ✓ Discord notification sent")
        except Exception as e:
            print(f"  ⚠️  Discord send failed: {e}")
    
    totals = {
        'trades': len(trades),
        'r': stats['total_r'],
        'pnl': stats['total_pnl']
    }
    
    print(f"\n✓ Intraday digest complete")
    print(f"  Trades: {totals['trades']}")
    print(f"  Total R: {totals['r']:+.2f}R")
    print(f"  Total PnL: ${totals['pnl']:+,.2f}")
    print(f"  Chart: {chart_path}")
    
    return {
        'ok': True,
        'date': today_str,
        'png': str(chart_path),
        'totals': totals
    }


if __name__ == "__main__":
    # Test with today's date
    today_str = datetime.now().strftime('%Y%m%d')
    generate_digest(today_str)
