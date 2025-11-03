from __future__ import annotations
from dataclasses import dataclass

PIP = 0.0001

@dataclass
class TradeSnapshot:
    side: int            # +1 long, -1 short
    entry: float
    sl: float
    tp: float | None = None

def r_size(entry: float, sl: float, side: int) -> float:
    # price distance per 1R in price units
    return (entry - sl) if side == 1 else (sl - entry)

def r_multiple(entry: float, price: float, snap: TradeSnapshot) -> float:
    rr = (price - entry) if snap.side == 1 else (entry - price)
    denom = r_size(snap.entry, snap.sl, snap.side)
    return (rr / denom) if denom > 0 else 0.0

def mfe_r(entry: float, hi: float, lo: float, snap: TradeSnapshot) -> float:
    # approximate bar-based MFE: favorable extreme vs entry
    fav = (hi - entry) if snap.side == 1 else (entry - lo)
    denom = r_size(snap.entry, snap.sl, snap.side)
    return (fav / denom) if denom > 0 else 0.0

def should_close(entry: float, last_close: float, bar_high: float, bar_low: float, snap: TradeSnapshot) -> tuple[bool, str, float, float]:
    """
    Returns (close_now, reason, mfeR, lastR). reason in {"breakeven","trail0.5","trail1.0","none"}
    """
    mfeR = mfe_r(entry, bar_high, bar_low, snap)
    lastR = r_multiple(entry, last_close, snap)

    if mfeR >= 1.0:
        # Breakeven tier: if price back to entry, exit
        if (snap.side == 1 and last_close <= entry) or (snap.side == -1 and last_close >= entry):
            return True, "breakeven", mfeR, lastR
    if mfeR >= 1.5:
        # Trail 0.5R
        trail_price = entry + (0.5 * r_size(entry, snap.sl, snap.side)) * (1 if snap.side==1 else -1)
        if (snap.side == 1 and last_close <= trail_price) or (snap.side == -1 and last_close >= trail_price):
            return True, "trail0.5", mfeR, lastR
    if mfeR >= 2.0:
        # Trail 1.0R
        trail_price = entry + (1.0 * r_size(entry, snap.sl, snap.side)) * (1 if snap.side==1 else -1)
        if (snap.side == 1 and last_close <= trail_price) or (snap.side == -1 and last_close >= trail_price):
            return True, "trail1.0", mfeR, lastR
    return False, "none", mfeR, lastR
