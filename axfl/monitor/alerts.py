"""
AXFL Alert System

Provides optional Discord webhook notifications for key events.
Set DISCORD_WEBHOOK_URL environment variable to enable.
"""

import os
import json
import requests
from typing import Optional


def _get_webhook_url() -> Optional[str]:
    """Get Discord webhook URL from environment."""
    return os.environ.get('DISCORD_WEBHOOK_URL')


def send_event(event: str, payload: dict) -> None:
    """
    Send an event alert to Discord.
    
    Args:
        event: Event name (e.g., "WS_CONNECTED", "TRADE_OPEN")
        payload: Event data dictionary
    """
    webhook_url = _get_webhook_url()
    if not webhook_url:
        return
    
    try:
        # Format payload for Discord embed (max 1800 chars)
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
        # Never raise - alerts should not break the trading system
        pass


def send_info(msg: str, payload: dict = {}) -> None:
    """
    Send an info-level alert to Discord.
    
    Args:
        msg: Message text
        payload: Optional data dictionary
    """
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
                "color": 3447003  # Blue
            }] if payload else []
        }
        
        response = requests.post(webhook_url, json=data, timeout=5)
        response.raise_for_status()
    except Exception:
        pass


def send_warn(msg: str, payload: dict = {}) -> None:
    """
    Send a warning-level alert to Discord.
    
    Args:
        msg: Warning message
        payload: Optional data dictionary
    """
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
    """
    Send an error-level alert to Discord.
    
    Args:
        msg: Error message
        payload: Optional data dictionary
    """
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
                "color": 15158332  # Red
            }] if payload else []
        }
        
        response = requests.post(webhook_url, json=data, timeout=5)
        response.raise_for_status()
    except Exception:
        pass


def send_diag(msg: str, payload: dict = {}) -> None:
    """
    Send a diagnostic alert to Discord.
    
    Args:
        msg: Diagnostic message
        payload: Optional data dictionary
    """
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
