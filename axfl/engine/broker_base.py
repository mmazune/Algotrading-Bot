from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List, Dict
import itertools

_order_ids = itertools.count(1)

@dataclass
class Order:
    side: int           # +1 long, -1 short
    units: int
    entry: float
    sl: float
    tp: float
    tag: str = ""

@dataclass
class Fill:
    order_id: int
    side: int
    entry: float
    exit: float
    sl: float
    tp: float
    r_multiple: float
    pnl_usd: float
    tag: str

@dataclass
class Position:
    order_id: int
    side: int
    units: int
    entry: float
    sl: float
    tp: float
    tag: str

class Broker:
    def place(self, order: Order) -> Position: ...
    def step_bar(self, high: float, low: float, close: float) -> List[Fill]: ...
    def close_all(self, price: float) -> List[Fill]: ...
    def realized(self) -> List[Fill]: ...
