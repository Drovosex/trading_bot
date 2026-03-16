from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    NEW = "NEW"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELED = "CANCELED"


@dataclass
class OrderResult:
    order_id: str
    symbol: str
    side: OrderSide
    status: OrderStatus
    price: float
    qty: float
    cost: float  # price * qty (for filled orders)

    @classmethod
    def from_dict(cls, d: dict, side: OrderSide) -> OrderResult:
        price = float(d.get("price", 0))
        qty = float(d.get("origQty", 0) or d.get("executedQty", 0))
        cost = float(d.get("cummulativeQuoteQty", 0))
        if cost == 0 and price and qty:
            cost = price * qty
        return cls(
            order_id=str(d.get("orderId", "")),
            symbol=d.get("symbol", ""),
            side=side,
            status=OrderStatus(d.get("status", "NEW")),
            price=price,
            qty=qty,
            cost=cost,
        )


@dataclass
class AccountBalance:
    asset: str
    free: float
    locked: float

    @classmethod
    def from_dict(cls, d: dict) -> AccountBalance:
        return cls(
            asset=d["asset"],
            free=float(d["free"]),
            locked=float(d["locked"]),
        )


@dataclass
class OpenOrder:
    order_id: str
    symbol: str
    side: OrderSide
    price: float
    qty: float
    status: OrderStatus

    @classmethod
    def from_dict(cls, d: dict) -> OpenOrder:
        return cls(
            order_id=str(d["orderId"]),
            symbol=d["symbol"],
            side=OrderSide(d["side"]),
            price=float(d["price"]),
            qty=float(d["origQty"]),
            status=OrderStatus(d["status"]),
        )
