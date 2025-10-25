"""
AXFL Alert System

Provides optional Discord webhook notifications for key events with polished embeds.
Set DISCORD_WEBHOOK_URL environment variable to enable.

Environment Variables:
    DISCORD_WEBHOOK_URL: Discord webhook URL for alerts
    AXFL_ALERTS_ENABLED: Set to 0 to disable alerts (default: 1)
    AXFL_MIN_UNITS: Minimum position size floor (default: 100)
"""

import os
import json
import requests
from typing import Optional, List, Tuple, Dict, Any
from datetime import datetime


# Discord embed colors (RGB integers)
COLOR_BLUE = 3447003      # Order placed
COLOR_GREEN = 3066993     # Order filled / Profit
COLOR_ORANGE = 15105570   # Order canceled
COLOR_RED = 15158332      # Order failed
COLOR_PURPLE = 10181046   # Trade closed (loss)
COLOR_TEAL = 1752220      # Daily summary

_alerts_enabled_logged = False


def _get_webhook_url() -> Optional[str]:
    """Get Discord webhook URL from environment."""
    global _alerts_enabled_logged
    
    if os.getenv('AXFL_ALERTS_ENABLED', '1') == '0':
        return None
    
    url = os.environ.get('DISCORD_WEBHOOK_URL')
    if not url and not _alerts_enabled_logged:
        print("[alerts] INFO: DISCORD_WEBHOOK_URL not set, alerts disabled")
        _alerts_enabled_logged = True
    
    return url


def fmt_money(value: float) -> str:
    """Format money with 2 decimal places and sign."""
    sign = '+' if value >= 0 else ''
    return f"`{sign}${value:.2f}`"


def fmt_r(value: float) -> str:
    """Format R-multiple with 2 decimal places and sign."""
    sign = '+' if value >= 0 else ''
    return f"`{sign}{value:.2f}R`"


def fmt_price(value: float, precision: int = 5) -> str:
    """Format price with specified precision."""
    return f"`{value:.{precision}f}`"


def fmt_timestamp(ts: Optional[datetime] = None) -> str:
    """Format timestamp as UTC ISO8601."""
    if ts is None:
        ts = datetime.utcnow()
    return ts.strftime("%Y-%m-%d %H:%M:%S UTC")


def build_embed(
    title: str,
    description: str = "",
    color: int = COLOR_BLUE,
    fields: Optional[List[Tuple[str, str, bool]]] = None,
    footer: Optional[str] = None,
    url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Build a Discord embed dictionary.
    
    Args:
        title: Embed title
        description: Embed description (optional)
        color: RGB color integer
        fields: List of (name, value, inline) tuples
        footer: Footer text (optional)
        url: URL to link title (optional)
    
    Returns:
        Discord embed dictionary
    """
    embed = {
        "title": title,
        "color": color,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    if description:
        embed["description"] = description
    
    if fields:
        embed["fields"] = [
            {"name": name, "value": value, "inline": inline}
            for name, value, inline in fields
        ]
    
    if footer:
        embed["footer"] = {"text": footer}
    
    if url:
        embed["url"] = url
    
    return embed


def post_webhook(webhook_url: str, embed: Dict[str, Any]) -> bool:
    """
    Post embed to Discord webhook.
    
    Args:
        webhook_url: Discord webhook URL
        embed: Embed dictionary
    
    Returns:
        True if successful, False otherwise
    """
    try:
        payload = {"embeds": [embed]}
        response = requests.post(webhook_url, json=payload, timeout=5)
        response.raise_for_status()
        return True
    except Exception as e:
        # Never raise - alerts should not break the trading system
        print(f"[alerts] Warning: Failed to send webhook: {e}")
        return False


def alert_order_placed(ctx: Dict[str, Any]) -> None:
    """
    Send alert for order placed.
    
    Args:
        ctx: Order context with keys:
            - symbol: Trading symbol
            - strategy: Strategy name (optional)
            - side: 'long' or 'short'
            - units: Position size
            - entry: Entry price (optional)
            - sl: Stop loss price/distance (optional)
            - tp: Take profit price (optional)
            - tag: Client tag (optional)
            - timestamp: Order timestamp (optional)
    """
    webhook_url = _get_webhook_url()
    if not webhook_url:
        return
    
    symbol = ctx.get('symbol', 'UNKNOWN')
    strategy = ctx.get('strategy', 'manual')
    side = ctx.get('side', 'unknown').upper()
    units = ctx.get('units', 0)
    entry = ctx.get('entry')
    sl = ctx.get('sl')
    tp = ctx.get('tp')
    tag = ctx.get('tag', '')
    
    title = f"📤 Order Placed: {symbol} {side}"
    
    fields = [
        ("Symbol", f"`{symbol}`", True),
        ("Strategy", f"`{strategy}`", True),
        ("Side", f"`{side}`", True),
        ("Units", f"`{units:,}`", True),
    ]
    
    if entry is not None:
        fields.append(("Entry", fmt_price(entry), True))
    
    if sl is not None:
        fields.append(("Stop Loss", fmt_price(sl), True))
    
    if tp is not None:
        fields.append(("Take Profit", fmt_price(tp), True))
    
    if tag:
        fields.append(("Tag", f"`{tag[:50]}`", False))
    
    fields.append(("Time", f"`{fmt_timestamp(ctx.get('timestamp'))}`", False))
    
    embed = build_embed(
        title=title,
        color=COLOR_BLUE,
        fields=fields,
        footer="AXFL Live Trading"
    )
    
    post_webhook(webhook_url, embed)


def alert_order_filled(ctx: Dict[str, Any]) -> None:
    """
    Send alert for order filled.
    
    Args:
        ctx: Fill context with keys:
            - symbol: Trading symbol
            - side: 'long' or 'short'
            - units: Position size
            - fill_price: Actual fill price
            - entry: Expected entry price (optional)
            - slippage: Slippage in pips (optional)
            - timestamp: Fill timestamp (optional)
    """
    webhook_url = _get_webhook_url()
    if not webhook_url:
        return
    
    symbol = ctx.get('symbol', 'UNKNOWN')
    side = ctx.get('side', 'unknown').upper()
    units = ctx.get('units', 0)
    fill_price = ctx.get('fill_price', 0)
    entry = ctx.get('entry')
    slippage = ctx.get('slippage')
    
    title = f"✅ Order Filled: {symbol} {side}"
    
    fields = [
        ("Symbol", f"`{symbol}`", True),
        ("Side", f"`{side}`", True),
        ("Units", f"`{units:,}`", True),
        ("Fill Price", fmt_price(fill_price), True),
    ]
    
    if entry is not None and slippage is not None:
        fields.append(("Slippage", f"`{slippage:.1f} pips`", True))
    
    fields.append(("Time", f"`{fmt_timestamp(ctx.get('timestamp'))}`", False))
    
    embed = build_embed(
        title=title,
        color=COLOR_GREEN,
        fields=fields,
        footer="AXFL Live Trading"
    )
    
    post_webhook(webhook_url, embed)


def alert_order_canceled(ctx: Dict[str, Any], reason: str = "UNKNOWN") -> None:
    """
    Send alert for order canceled.
    
    Args:
        ctx: Order context
        reason: Cancellation reason (e.g., MARKET_HALTED, CLIENT_CANCEL, RISK_REJECT)
    """
    webhook_url = _get_webhook_url()
    if not webhook_url:
        return
    
    symbol = ctx.get('symbol', 'UNKNOWN')
    side = ctx.get('side', 'unknown').upper()
    
    title = f"⚠️ Order Canceled: {symbol}"
    
    fields = [
        ("Symbol", f"`{symbol}`", True),
        ("Side", f"`{side}`", True),
        ("Reason", f"`{reason}`", False),
        ("Time", f"`{fmt_timestamp(ctx.get('timestamp'))}`", False),
    ]
    
    embed = build_embed(
        title=title,
        color=COLOR_ORANGE,
        fields=fields,
        footer="AXFL Live Trading"
    )
    
    post_webhook(webhook_url, embed)


def alert_order_failed(ctx: Dict[str, Any], error: str = "UNKNOWN") -> None:
    """
    Send alert for order failed.
    
    Args:
        ctx: Order context
        error: Error message (sanitized)
    """
    webhook_url = _get_webhook_url()
    if not webhook_url:
        return
    
    symbol = ctx.get('symbol', 'UNKNOWN')
    side = ctx.get('side', 'unknown').upper()
    
    # Sanitize error (limit length)
    error = str(error)[:200]
    
    title = f"❌ Order Failed: {symbol}"
    
    fields = [
        ("Symbol", f"`{symbol}`", True),
        ("Side", f"`{side}`", True),
        ("Error", f"```{error}```", False),
        ("Time", f"`{fmt_timestamp(ctx.get('timestamp'))}`", False),
    ]
    
    embed = build_embed(
        title=title,
        color=COLOR_RED,
        fields=fields,
        footer="AXFL Live Trading"
    )
    
    post_webhook(webhook_url, embed)


def alert_trade_closed(ctx: Dict[str, Any]) -> None:
    """
    Send alert for trade closed.
    
    Args:
        ctx: Trade context with keys:
            - symbol: Trading symbol
            - strategy: Strategy name (optional)
            - side: 'long' or 'short'
            - entry: Entry price
            - exit: Exit price
            - pnl: Realized P&L in dollars
            - r: R-multiple
            - holding_time: Holding time string (optional)
            - fees: Fees estimate (optional)
            - daily_pnl: Daily P&L total (optional)
            - daily_r: Daily R total (optional)
            - timestamp: Close timestamp (optional)
    """
    webhook_url = _get_webhook_url()
    if not webhook_url:
        return
    
    symbol = ctx.get('symbol', 'UNKNOWN')
    strategy = ctx.get('strategy', 'manual')
    side = ctx.get('side', 'unknown').upper()
    entry = ctx.get('entry', 0)
    exit_price = ctx.get('exit', 0)
    pnl = ctx.get('pnl', 0)
    r = ctx.get('r', 0)
    holding_time = ctx.get('holding_time', 'N/A')
    fees = ctx.get('fees')
    daily_pnl = ctx.get('daily_pnl')
    daily_r = ctx.get('daily_r')
    
    # Choose color based on P&L
    color = COLOR_GREEN if pnl >= 0 else COLOR_PURPLE
    
    title = f"🔒 Trade Closed: {symbol} {side}"
    
    fields = [
        ("Symbol", f"`{symbol}`", True),
        ("Strategy", f"`{strategy}`", True),
        ("Side", f"`{side}`", True),
        ("Entry", fmt_price(entry), True),
        ("Exit", fmt_price(exit_price), True),
        ("Holding Time", f"`{holding_time}`", True),
        ("P&L", fmt_money(pnl), True),
        ("R-Multiple", fmt_r(r), True),
    ]
    
    if fees is not None:
        fields.append(("Fees (est)", fmt_money(fees), True))
    
    if daily_pnl is not None and daily_r is not None:
        fields.append(("Daily P&L", fmt_money(daily_pnl), True))
        fields.append(("Daily R", fmt_r(daily_r), True))
    
    fields.append(("Time", f"`{fmt_timestamp(ctx.get('timestamp'))}`", False))
    
    embed = build_embed(
        title=title,
        color=color,
        fields=fields,
        footer="AXFL Live Trading"
    )
    
    post_webhook(webhook_url, embed)


def alert_daily_summary(summary: Dict[str, Any]) -> None:
    """
    Send daily summary alert.
    
    Args:
        summary: Summary dict with keys:
            - date: Trading date (YYYY-MM-DD)
            - total_pnl: Total P&L in dollars
            - total_r: Total R-multiple
            - win_rate: Win rate percentage
            - trades: Number of trades
            - best_r: Best trade R-multiple
            - worst_r: Worst trade R-multiple
            - per_symbol_r: Dict of symbol -> R
            - per_strategy_r: Dict of strategy -> R
    """
    webhook_url = _get_webhook_url()
    if not webhook_url:
        return
    
    date = summary.get('date', datetime.utcnow().strftime('%Y-%m-%d'))
    total_pnl = summary.get('total_pnl', 0)
    total_r = summary.get('total_r', 0)
    win_rate = summary.get('win_rate', 0)
    trades = summary.get('trades', 0)
    best_r = summary.get('best_r', 0)
    worst_r = summary.get('worst_r', 0)
    per_symbol_r = summary.get('per_symbol_r', {})
    per_strategy_r = summary.get('per_strategy_r', {})
    
    title = f"📊 AXFL Daily Summary - {date}"
    
    fields = [
        ("Date", f"`{date}`", True),
        ("Trades", f"`{trades}`", True),
        ("Win Rate", f"`{win_rate:.1f}%`", True),
        ("Total P&L", fmt_money(total_pnl), True),
        ("Total R", fmt_r(total_r), True),
        ("Best Trade", fmt_r(best_r), True),
        ("Worst Trade", fmt_r(worst_r), True),
    ]
    
    # Per-symbol R (compact line)
    if per_symbol_r:
        symbol_r_str = ", ".join([f"{sym} {r:+.2f}R" for sym, r in per_symbol_r.items()])
        fields.append(("Per-Symbol R", f"`{symbol_r_str}`", False))
    
    # Per-strategy R
    if per_strategy_r:
        strategy_r_str = ", ".join([f"{strat} {r:+.2f}R" for strat, r in per_strategy_r.items()])
        fields.append(("Per-Strategy R", f"`{strategy_r_str}`", False))
    
    embed = build_embed(
        title=title,
        color=COLOR_TEAL,
        fields=fields,
        footer="AXFL Daily Trading Summary"
    )
    
    post_webhook(webhook_url, embed)


# Legacy compatibility - keep existing functions
def send_event(event: str, payload: dict) -> None:
    """Send an event alert (legacy compatibility)."""
    webhook_url = _get_webhook_url()
    if not webhook_url:
        return
    
    try:
        payload_json = json.dumps(payload, separators=(',', ':'))
        if len(payload_json) > 1800:
            payload_json = payload_json[:1797] + "..."
        
        data = {
            "content": f"[AXFL] {event}",
            "embeds": [{
                "description": f"```json\n{payload_json}\n```"
            }]
        }
        
        response = requests.post(webhook_url, json=data, timeout=5)
        response.raise_for_status()
    except Exception:
        pass


def send_info(msg: str, payload: dict = {}) -> None:
    """Send an info-level alert (legacy compatibility)."""
    webhook_url = _get_webhook_url()
    if not webhook_url:
        return
    
    try:
        payload_json = json.dumps(payload, separators=(',', ':'))
        if len(payload_json) > 1800:
            payload_json = payload_json[:1797] + "..."
        
        data = {
            "content": f"[AXFL] ℹ️ {msg}",
            "embeds": [{
                "description": f"```json\n{payload_json}\n```",
                "color": COLOR_BLUE
            }] if payload else []
        }
        
        response = requests.post(webhook_url, json=data, timeout=5)
        response.raise_for_status()
    except Exception:
        pass


def send_warn(msg: str, payload: dict = {}) -> None:
    """Send a warning-level alert (legacy compatibility)."""
    webhook_url = _get_webhook_url()
    if not webhook_url:
        return
    
    try:
        payload_json = json.dumps(payload, separators=(',', ':'))
        if len(payload_json) > 1800:
            payload_json = payload_json[:1797] + "..."
        
        data = {
            "content": f"[AXFL] ⚠️ {msg}",
            "embeds": [{
                "description": f"```json\n{payload_json}\n```",
                "color": 16776960  # Yellow
            }] if payload else []
        }
        
        response = requests.post(webhook_url, json=data, timeout=5)
        response.raise_for_status()
    except Exception:
        pass


def send_error(msg: str, payload: dict = {}) -> None:
    """Send an error-level alert (legacy compatibility)."""
    webhook_url = _get_webhook_url()
    if not webhook_url:
        return
    
    try:
        payload_json = json.dumps(payload, separators=(',', ':'))
        if len(payload_json) > 1800:
            payload_json = payload_json[:1797] + "..."
        
        data = {
            "content": f"[AXFL] 🚨 {msg}",
            "embeds": [{
                "description": f"```json\n{payload_json}\n```",
                "color": COLOR_RED
            }] if payload else []
        }
        
        response = requests.post(webhook_url, json=data, timeout=5)
        response.raise_for_status()
    except Exception:
        pass


def send_diag(msg: str, payload: dict = {}) -> None:
    """Send a diagnostic alert (legacy compatibility)."""
    webhook_url = _get_webhook_url()
    if not webhook_url:
        return
    
    try:
        payload_json = json.dumps(payload, separators=(',', ':'))
        if len(payload_json) > 1800:
            payload_json = payload_json[:1797] + "..."
        
        data = {
            "content": f"[AXFL] 🔍 DIAG: {msg}",
            "embeds": [{
                "description": f"```json\n{payload_json}\n```",
                "color": 9807270  # Gray
            }] if payload else []
        }
        
        response = requests.post(webhook_url, json=data, timeout=5)
        response.raise_for_status()
    except Exception:
        pass


# Import daily_snapshot if available
try:
    from .pnl import daily_snapshot
except ImportError:
    def daily_snapshot():
        """Placeholder for daily snapshot."""
        pass
