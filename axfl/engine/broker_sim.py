from __future__ import annotations
from typing import List
from .broker_base import Broker, Order, Position, Fill, _order_ids

PIP = 0.0001

class SimBroker(Broker):
    """
    Bar-based simulator with basic microstructure:
      - One active position at a time
      - TP/SL checked vs mid-price high/low of bar
      - Entry/exit prices adjusted by half-spread; exits suffer slippage against trader
    """
    def __init__(self, risk_dollars: float = 2.0, spread_pips: float = 0.2, slippage_pips: float = 0.1):
        self.pos: Position | None = None
        self._fills: list[Fill] = []
        self.risk_dollars = float(risk_dollars)
        self.spread_half = (spread_pips * PIP) / 2.0
        self.slip = slippage_pips * PIP

    def place(self, order: Order) -> Position:
        if self.pos is not None:
            raise RuntimeError("Position already open")
        oid = next(_order_ids)
        # Entry fills at mid +/- half-spread
        adj_entry = order.entry + (self.spread_half if order.side==1 else -self.spread_half)
        self.pos = Position(
            order_id=oid, side=order.side, units=order.units,
            entry=adj_entry, sl=order.sl, tp=order.tp, tag=order.tag
        )
        return self.pos

    def _exit_price(self, mid_target: float, side: int) -> float:
        # Sell long at bid = mid - half-spread; buy-to-cover short at ask = mid + half-spread
        base = mid_target - self.spread_half if side==1 else mid_target + self.spread_half
        # Slippage always moves against trader
        return base - self.slip if side==1 else base + self.slip

    def step_bar(self, high: float, low: float, close: float) -> List[Fill]:
        if self.pos is None:
            return []
        p = self.pos
        exit_mid = None
        tag = None
        if p.side == 1:
            if high >= p.tp: exit_mid, tag = p.tp, "TP"
            elif low <= p.sl: exit_mid, tag = p.sl, "SL"
        else:
            if low <= p.tp: exit_mid, tag = p.tp, "TP"
            elif high >= p.sl: exit_mid, tag = p.sl, "SL"
        if exit_mid is None:
            return []
        ex = self._exit_price(exit_mid, p.side)
        risk_pips = (p.entry - p.sl)/PIP if p.side==1 else (p.sl - p.entry)/PIP
        reward_pips = (ex - p.entry)/PIP if p.side==1 else (p.entry - ex)/PIP
        R = (reward_pips / risk_pips) if risk_pips > 0 else 0.0
        pnl_usd = R * self.risk_dollars
        f = Fill(order_id=p.order_id, side=p.side, entry=p.entry, exit=ex,
                 sl=p.sl, tp=p.tp, r_multiple=R, pnl_usd=pnl_usd, tag=tag)
        self._fills.append(f)
        self.pos = None
        return [f]

    def close_all(self, price: float) -> List[Fill]:
        if self.pos is None:
            return []
        p = self.pos
        ex = self._exit_price(price, p.side)
        risk_pips = (p.entry - p.sl)/PIP if p.side==1 else (p.sl - p.entry)/PIP
        reward_pips = (ex - p.entry)/PIP if p.side==1 else (p.entry - ex)/PIP
        R = (reward_pips / risk_pips) if risk_pips > 0 else 0.0
        pnl_usd = R * self.risk_dollars
        f = Fill(order_id=p.order_id, side=p.side, entry=p.entry, exit=ex,
                 sl=p.sl, tp=p.tp, r_multiple=R, pnl_usd=pnl_usd, tag="MKT")
        self._fills.append(f)
        self.pos = None
        return [f]

    def realized(self) -> List[Fill]:
        return list(self._fills)
