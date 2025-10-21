"""
AXFL Journal Store - SQLite persistence for orders, trades, and reconciliation.

Schema:
- broker_orders: broker-side orders with client tags
- axfl_trades: AXFL portfolio trades
- map: links axfl_id <-> order_id
- events: diagnostic events (reconciliation, conflicts, etc.)
"""

import sqlite3
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime


DB_PATH = Path(__file__).parent.parent.parent / "data" / "journal.db"


def init_db() -> None:
    """Initialize journal database with all tables."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    
    # broker_orders: broker-side orders with client tags
    cur.execute("""
        CREATE TABLE IF NOT EXISTS broker_orders (
            order_id TEXT PRIMARY KEY,
            client_tag TEXT UNIQUE,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            units INTEGER NOT NULL,
            entry REAL,
            sl REAL,
            tp REAL,
            status TEXT NOT NULL,
            opened_at TEXT,
            closed_at TEXT,
            extra TEXT
        )
    """)
    
    # axfl_trades: AXFL portfolio trades
    cur.execute("""
        CREATE TABLE IF NOT EXISTS axfl_trades (
            axfl_id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            strategy TEXT NOT NULL,
            side TEXT NOT NULL,
            entry REAL NOT NULL,
            sl REAL,
            tp REAL,
            r REAL,
            pnl REAL,
            opened_at TEXT NOT NULL,
            closed_at TEXT,
            extra TEXT
        )
    """)
    
    # map: links axfl_id <-> order_id
    cur.execute("""
        CREATE TABLE IF NOT EXISTS map (
            axfl_id TEXT NOT NULL,
            order_id TEXT NOT NULL,
            PRIMARY KEY (axfl_id, order_id)
        )
    """)
    
    # events: diagnostic events
    cur.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            level TEXT NOT NULL,
            kind TEXT NOT NULL,
            payload TEXT
        )
    """)
    
    # Indexes for performance
    cur.execute("CREATE INDEX IF NOT EXISTS idx_broker_orders_client_tag ON broker_orders(client_tag)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_broker_orders_status ON broker_orders(status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_axfl_trades_closed_at ON axfl_trades(closed_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_map_axfl_id ON map(axfl_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_map_order_id ON map(order_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts)")
    
    conn.commit()
    conn.close()


def upsert_broker_order(
    order_id: str,
    client_tag: str,
    symbol: str,
    side: str,
    units: int,
    entry: Optional[float] = None,
    sl: Optional[float] = None,
    tp: Optional[float] = None,
    status: str = "open",
    opened_at: Optional[str] = None,
    closed_at: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Insert or update broker order."""
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    
    extra_json = json.dumps(extra) if extra else None
    opened_at = opened_at or datetime.utcnow().isoformat()
    
    cur.execute("""
        INSERT INTO broker_orders 
        (order_id, client_tag, symbol, side, units, entry, sl, tp, status, opened_at, closed_at, extra)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(order_id) DO UPDATE SET
            status=excluded.status,
            closed_at=excluded.closed_at,
            extra=excluded.extra
    """, (order_id, client_tag, symbol, side, units, entry, sl, tp, status, opened_at, closed_at, extra_json))
    
    conn.commit()
    conn.close()


def upsert_axfl_trade(
    axfl_id: str,
    symbol: str,
    strategy: str,
    side: str,
    entry: float,
    sl: Optional[float] = None,
    tp: Optional[float] = None,
    r: Optional[float] = None,
    pnl: Optional[float] = None,
    opened_at: Optional[str] = None,
    closed_at: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Insert or update AXFL trade."""
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    
    extra_json = json.dumps(extra) if extra else None
    opened_at = opened_at or datetime.utcnow().isoformat()
    
    cur.execute("""
        INSERT INTO axfl_trades 
        (axfl_id, symbol, strategy, side, entry, sl, tp, r, pnl, opened_at, closed_at, extra)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(axfl_id) DO UPDATE SET
            r=excluded.r,
            pnl=excluded.pnl,
            closed_at=excluded.closed_at,
            extra=excluded.extra
    """, (axfl_id, symbol, strategy, side, entry, sl, tp, r, pnl, opened_at, closed_at, extra_json))
    
    conn.commit()
    conn.close()


def link(axfl_id: str, order_id: str) -> None:
    """Link AXFL trade to broker order."""
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    
    cur.execute("""
        INSERT OR IGNORE INTO map (axfl_id, order_id)
        VALUES (?, ?)
    """, (axfl_id, order_id))
    
    conn.commit()
    conn.close()


def log_event(level: str, kind: str, payload: Optional[Dict[str, Any]] = None) -> None:
    """Log diagnostic event."""
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    
    ts = datetime.utcnow().isoformat()
    payload_json = json.dumps(payload) if payload else None
    
    cur.execute("""
        INSERT INTO events (ts, level, kind, payload)
        VALUES (?, ?, ?, ?)
    """, (ts, level, kind, payload_json))
    
    conn.commit()
    conn.close()


def open_positions() -> List[Dict[str, Any]]:
    """Get all open positions from journal (broker + axfl)."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Get open broker orders
    cur.execute("""
        SELECT * FROM broker_orders 
        WHERE status = 'open' AND closed_at IS NULL
    """)
    broker_rows = [dict(row) for row in cur.fetchall()]
    
    # Get open AXFL trades
    cur.execute("""
        SELECT * FROM axfl_trades 
        WHERE closed_at IS NULL
    """)
    axfl_rows = [dict(row) for row in cur.fetchall()]
    
    # Get mappings
    cur.execute("SELECT * FROM map")
    mappings = [dict(row) for row in cur.fetchall()]
    
    conn.close()
    
    # Parse JSON fields
    for row in broker_rows:
        if row.get("extra"):
            row["extra"] = json.loads(row["extra"])
    
    for row in axfl_rows:
        if row.get("extra"):
            row["extra"] = json.loads(row["extra"])
    
    return {
        "broker_orders": broker_rows,
        "axfl_trades": axfl_rows,
        "mappings": mappings,
    }


def last_n_events(n: int = 50) -> List[Dict[str, Any]]:
    """Get last N events."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    cur.execute("""
        SELECT * FROM events 
        ORDER BY id DESC 
        LIMIT ?
    """, (n,))
    
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    
    # Parse JSON payloads
    for row in rows:
        if row.get("payload"):
            row["payload"] = json.loads(row["payload"])
    
    return rows


def pending_mappings() -> List[Dict[str, Any]]:
    """Get AXFL trades without broker mapping."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    cur.execute("""
        SELECT a.* FROM axfl_trades a
        LEFT JOIN map m ON a.axfl_id = m.axfl_id
        WHERE m.order_id IS NULL AND a.closed_at IS NULL
    """)
    
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    
    # Parse JSON fields
    for row in rows:
        if row.get("extra"):
            row["extra"] = json.loads(row["extra"])
    
    return rows


# Initialize on import
init_db()
