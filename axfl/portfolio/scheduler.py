"""Session scheduling for portfolio trading."""

from dataclasses import dataclass
from typing import List, Dict, Any
import pandas as pd
import yaml
from pathlib import Path


@dataclass
class SessionWindow:
    """UTC trading session window."""
    start_h: int
    start_m: int
    end_h: int
    end_m: int
    
    def contains(self, ts_utc: pd.Timestamp) -> bool:
        """Check if UTC timestamp is inside this window."""
        t = ts_utc.to_pydatetime()
        start_min = self.start_h * 60 + self.start_m
        end_min = self.end_h * 60 + self.end_m
        current_min = t.hour * 60 + t.minute
        return start_min <= current_min < end_min
    
    def __repr__(self):
        return f"{self.start_h:02d}:{self.start_m:02d}-{self.end_h:02d}:{self.end_m:02d}"


def now_in_any_window(ts_utc: pd.Timestamp, windows: List[SessionWindow]) -> bool:
    """Check if UTC timestamp is inside any session window."""
    return any(w.contains(ts_utc) for w in windows)


def load_sessions_yaml(path: str) -> Dict[str, Any]:
    """Load sessions YAML config file."""
    cfg_path = Path(path)
    if not cfg_path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    
    with open(cfg_path, 'r') as f:
        return yaml.safe_load(f)


def normalize_schedule(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize loaded YAML into internal schedule structure.
    
    Returns:
        {
            "symbols": [...],
            "interval": "5m",
            "source": "auto",
            "venue": "OANDA",
            "spread_pips": 0.6,
            "warmup_days": 3,
            "status_every_s": 180,
            "risk": {...},
            "strategies": [
                {
                    "name": "lsg",
                    "params": {...},
                    "windows": [SessionWindow(...), ...]
                },
                ...
            ]
        }
    """
    portfolio = cfg.get('portfolio', {})
    strategies_raw = cfg.get('strategies', [])
    
    # Parse session windows for each strategy
    strategies = []
    for strat in strategies_raw:
        windows = []
        for w in strat.get('windows', []):
            start_parts = w['start'].split(':')
            end_parts = w['end'].split(':')
            windows.append(SessionWindow(
                start_h=int(start_parts[0]),
                start_m=int(start_parts[1]),
                end_h=int(end_parts[0]),
                end_m=int(end_parts[1]),
            ))
        
        strategies.append({
            'name': strat['name'],
            'params': strat.get('params', {}),
            'windows': windows,
        })
    
    result = {
        'symbols': portfolio.get('symbols', ['EURUSD']),
        'interval': portfolio.get('interval', '5m'),
        'source': portfolio.get('source', 'auto'),
        'venue': portfolio.get('venue', 'OANDA'),
        'warmup_days': portfolio.get('warmup_days', 3),
        'status_every_s': portfolio.get('status_every_s', 180),
        'risk': portfolio.get('risk', {}),
        'strategies': strategies,
    }
    
    # Handle spreads - can be dict (per-symbol) or single value
    if 'spreads' in portfolio:
        result['spreads'] = portfolio['spreads']
    else:
        result['spread_pips'] = portfolio.get('spread_pips', 0.6)
    
    return result
