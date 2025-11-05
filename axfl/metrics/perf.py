"""Performance computation and SQLite persistence."""
import os, sqlite3, datetime as dt
from pathlib import Path

DB_PATH = Path(os.getenv("AXFL_DB", "/opt/axfl/app/data/axfl.db"))

def _ensure() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id TEXT,
            order_id TEXT,
            instrument TEXT,
            strategy TEXT,
            side TEXT,
            units INTEGER,
            entry REAL,
            exit REAL,
            pips REAL,
            money REAL,
            opened_at TEXT,
            closed_at TEXT
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_trades_time ON trades(opened_at, closed_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades(strategy)")
        c.commit()

def record_open(*, trade_id, order_id, instrument, strategy, side, units, entry, opened_at_iso) -> None:
    _ensure()
    with sqlite3.connect(DB_PATH) as c:
        c.execute("""INSERT INTO trades(trade_id,order_id,instrument,strategy,side,units,entry,opened_at)
                     VALUES(?,?,?,?,?,?,?,?)""",
                  (str(trade_id), str(order_id), instrument, strategy, side, int(units), float(entry), opened_at_iso))
        c.commit()

def record_close(*, trade_id, exit_price, closed_at_iso) -> None:
    _ensure()
    with sqlite3.connect(DB_PATH) as c:
        r = c.execute(
            "SELECT id,instrument,side,units,entry FROM trades WHERE trade_id=? ORDER BY id DESC LIMIT 1",
            (str(trade_id),)
        ).fetchone()
        if not r:
            return
        _id, instr, side, units, entry = r
        pip = 0.01 if instr.endswith("JPY") else 0.0001
        raw = (float(exit_price) - float(entry)) / pip
        pips = raw if side.lower() in ("buy","long") else -raw
        money = (float(exit_price) - float(entry)) * (int(units) if side.lower() in ("buy","long") else -int(units))
        c.execute("""UPDATE trades SET exit=?, pips=?, money=?, closed_at=? WHERE id=?""",
                  (float(exit_price), float(pips), float(money), closed_at_iso, _id))
        c.commit()

def _range(label: str) -> tuple[dt.datetime, dt.datetime]:
    now = dt.datetime.utcnow()
    if label == "daily":
        start = dt.datetime(now.year, now.month, now.day)
    elif label == "weekly":
        start = (now - dt.timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    elif label == "monthly":
        start = dt.datetime(now.year, now.month, 1)
    else:
        raise ValueError("bad label")
    return start, now

def compute(label: str) -> tuple[dict, list[dict]]:
    _ensure()
    start, end = _range(label)
    with sqlite3.connect(DB_PATH) as c:
        rows = c.execute("""
            SELECT strategy, instrument, pips, money, opened_at, closed_at
            FROM trades
            WHERE closed_at IS NOT NULL AND closed_at >= ? AND closed_at < ?
        """, (start.isoformat(), end.isoformat())).fetchall()

    total_trades = len(rows)
    wins = sum(1 for r in rows if (r[3] or 0.0) > 0)
    pips = sum((r[2] or 0.0) for r in rows)
    money = sum((r[3] or 0.0) for r in rows)
    best = max((r[3] or 0.0) for r in rows) if rows else 0.0
    worst = min((r[3] or 0.0) for r in rows) if rows else 0.0
    avg = (money / total_trades) if total_trades else 0.0
    win_rate = round(100.0*wins/total_trades, 1) if total_trades else 0.0

    totals = {
        "period": label, "trades": total_trades, "win_rate": win_rate,
        "pips": round(pips,1), "money": round(money,2),
        "best": round(best,2), "worst": round(worst,2), "avg": round(avg,2)
    }

    strat = {}
    for s, instr, spips, smoney, *_ in rows:
        key = s or "UNKNOWN"
        d = strat.setdefault(key, {"trades":0,"pips":0.0,"money":0.0})
        d["trades"] += 1
        d["pips"] += (spips or 0.0)
        d["money"] += (smoney or 0.0)

    strat_rows: list[dict] = []
    for s, d in strat.items():
        w = sum(1 for r in rows if (r[0] or "UNKNOWN")==s and (r[3] or 0.0) > 0)
        wr = round(100.0*w/d["trades"], 1) if d["trades"] else 0.0
        strat_rows.append({
            "strategy": s,
            "trades": d["trades"],
            "pips": round(d["pips"],1),
            "money": round(d["money"],2),
            "win_rate": wr,
            "avg": round(d["money"]/d["trades"],2) if d["trades"] else 0.0
        })
    strat_rows.sort(key=lambda x: (x["money"], x["pips"]), reverse=True)
    for i, r in enumerate(strat_rows, 1):
        r["rank"] = i
    return totals, strat_rows
