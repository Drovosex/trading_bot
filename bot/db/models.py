from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class OrderType(str, Enum):
    DYNAMIC = "dynamic"
    FIXED = "fixed"


class PositionStatus(str, Enum):
    OPEN = "open"        # bought, sell order placed
    SELLING = "selling"  # sell order on exchange
    CLOSED = "closed"    # sell filled, profit recorded


@dataclass
class User:
    id: int                    # Telegram user_id
    username: str | None = None
    api_key_enc: bytes | None = None
    api_secret_enc: bytes | None = None
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class TradingSettings:
    user_id: int
    pair: str = "BTCUSDC"
    order_type: OrderType = OrderType.DYNAMIC
    order_param: float = 2.0       # % of capital (dynamic) or USDT amount (fixed)
    profit_pct: float = 0.3
    drop_pct: float = 1.0
    maker_fee: float = 0.0
    taker_fee: float = 0.05
    auto_buy_interval: int = 30    # Seconds between sell of active order and next buy (1-60)
    drop_buy_enabled: bool = True  # Enable drop-based additional buys


@dataclass
class Position:
    id: int | None = None
    user_id: int = 0
    pair: str = ""
    buy_price: float = 0.0
    buy_qty: float = 0.0
    buy_cost: float = 0.0
    buy_order_id: str = ""
    buy_filled_at: datetime = field(default_factory=datetime.utcnow)
    sell_order_id: str | None = None
    sell_target_price: float = 0.0
    status: PositionStatus = PositionStatus.OPEN
    sell_filled_at: datetime | None = None
    sell_revenue: float | None = None
    profit: float | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Subscription:
    """Stub for future subscription system."""
    id: int | None = None
    user_id: int = 0
    tier: str = "free"
    position_limit: float | None = None
    started_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime = field(default_factory=datetime.utcnow)
    is_active: bool = True


@dataclass
class DemoAccount:
    user_id: int = 0
    balance: float = 5000.0
    initial_balance: float = 5000.0
