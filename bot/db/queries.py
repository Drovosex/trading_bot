from __future__ import annotations

from datetime import datetime
from typing import Any

from bot.db.database import Database
from bot.db.models import (
    DemoAccount,
    OrderType,
    Position,
    PositionStatus,
    TradingSettings,
    User,
)


# ─── Users ────────────────────────────────────────────────────────────────────

async def get_user(db: Database, user_id: int) -> User | None:
    row = await db.db.execute_fetchall(
        "SELECT * FROM users WHERE id = ?", (user_id,)
    )
    if not row:
        return None
    r = row[0]
    return User(
        id=r["id"],
        username=r["username"],
        api_key_enc=r["api_key_enc"],
        api_secret_enc=r["api_secret_enc"],
        is_active=bool(r["is_active"]),
        created_at=r["created_at"],
    )


async def upsert_user(
    db: Database, user_id: int, username: str | None = None
) -> None:
    await db.db.execute(
        """INSERT INTO users (id, username) VALUES (?, ?)
           ON CONFLICT(id) DO UPDATE SET username = excluded.username""",
        (user_id, username),
    )
    await db.db.commit()


async def save_api_keys(
    db: Database, user_id: int, key_enc: bytes, secret_enc: bytes
) -> None:
    await db.db.execute(
        "UPDATE users SET api_key_enc = ?, api_secret_enc = ? WHERE id = ?",
        (key_enc, secret_enc, user_id),
    )
    await db.db.commit()


# ─── Trading Settings ─────────────────────────────────────────────────────────

async def get_settings(db: Database, user_id: int) -> TradingSettings | None:
    rows = await db.db.execute_fetchall(
        "SELECT * FROM trading_settings WHERE user_id = ?", (user_id,)
    )
    if not rows:
        return None
    r = rows[0]
    return TradingSettings(
        user_id=r["user_id"],
        pair=r["pair"],
        order_type=OrderType(r["order_type"]),
        order_param=r["order_param"],
        profit_pct=r["profit_pct"],
        drop_pct=r["drop_pct"],
        maker_fee=r["maker_fee"],
        taker_fee=r["taker_fee"],
    )


async def upsert_settings(db: Database, s: TradingSettings) -> None:
    await db.db.execute(
        """INSERT INTO trading_settings
           (user_id, pair, order_type, order_param, profit_pct, drop_pct, maker_fee, taker_fee)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET
               pair=excluded.pair, order_type=excluded.order_type,
               order_param=excluded.order_param, profit_pct=excluded.profit_pct,
               drop_pct=excluded.drop_pct, maker_fee=excluded.maker_fee,
               taker_fee=excluded.taker_fee""",
        (
            s.user_id, s.pair, s.order_type.value, s.order_param,
            s.profit_pct, s.drop_pct, s.maker_fee, s.taker_fee,
        ),
    )
    await db.db.commit()


# ─── Positions ────────────────────────────────────────────────────────────────

async def save_position(db: Database, p: Position) -> int:
    cursor = await db.db.execute(
        """INSERT INTO positions
           (user_id, pair, buy_price, buy_qty, buy_cost, buy_order_id,
            buy_filled_at, sell_order_id, sell_target_price, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            p.user_id, p.pair, p.buy_price, p.buy_qty, p.buy_cost,
            p.buy_order_id, p.buy_filled_at.isoformat(),
            p.sell_order_id, p.sell_target_price, p.status.value,
        ),
    )
    await db.db.commit()
    return cursor.lastrowid  # type: ignore[return-value]


async def update_position_sell(
    db: Database, position_id: int, sell_order_id: str
) -> None:
    await db.db.execute(
        "UPDATE positions SET sell_order_id = ?, status = 'selling' WHERE id = ?",
        (sell_order_id, position_id),
    )
    await db.db.commit()


async def close_position(
    db: Database, position_id: int, sell_revenue: float, profit: float
) -> None:
    await db.db.execute(
        """UPDATE positions SET status = 'closed', sell_filled_at = ?,
           sell_revenue = ?, profit = ? WHERE id = ?""",
        (datetime.utcnow().isoformat(), sell_revenue, profit, position_id),
    )
    await db.db.commit()


async def get_active_positions(db: Database, user_id: int) -> list[Position]:
    rows = await db.db.execute_fetchall(
        "SELECT * FROM positions WHERE user_id = ? AND status != 'closed' ORDER BY created_at",
        (user_id,),
    )
    return [_row_to_position(r) for r in rows]


async def get_positions_for_period(
    db: Database, user_id: int, start: datetime, end: datetime
) -> list[Position]:
    rows = await db.db.execute_fetchall(
        """SELECT * FROM positions WHERE user_id = ? AND status = 'closed'
           AND sell_filled_at >= ? AND sell_filled_at < ?
           ORDER BY sell_filled_at""",
        (user_id, start.isoformat(), end.isoformat()),
    )
    return [_row_to_position(r) for r in rows]


async def get_all_closed_positions(db: Database, user_id: int) -> list[Position]:
    rows = await db.db.execute_fetchall(
        "SELECT * FROM positions WHERE user_id = ? AND status = 'closed' ORDER BY sell_filled_at",
        (user_id,),
    )
    return [_row_to_position(r) for r in rows]


def _row_to_position(r: Any) -> Position:
    return Position(
        id=r["id"],
        user_id=r["user_id"],
        pair=r["pair"],
        buy_price=r["buy_price"],
        buy_qty=r["buy_qty"],
        buy_cost=r["buy_cost"],
        buy_order_id=r["buy_order_id"],
        buy_filled_at=datetime.fromisoformat(r["buy_filled_at"]) if r["buy_filled_at"] else datetime.utcnow(),
        sell_order_id=r["sell_order_id"],
        sell_target_price=r["sell_target_price"],
        status=PositionStatus(r["status"]),
        sell_filled_at=datetime.fromisoformat(r["sell_filled_at"]) if r["sell_filled_at"] else None,
        sell_revenue=r["sell_revenue"],
        profit=r["profit"],
    )


# ─── Demo ─────────────────────────────────────────────────────────────────────

async def get_demo(db: Database, user_id: int) -> DemoAccount | None:
    rows = await db.db.execute_fetchall(
        "SELECT * FROM demo_accounts WHERE user_id = ?", (user_id,)
    )
    if not rows:
        return None
    r = rows[0]
    return DemoAccount(
        user_id=r["user_id"],
        balance=r["balance"],
        initial_balance=r["initial_balance"],
    )


async def upsert_demo(db: Database, demo: DemoAccount) -> None:
    await db.db.execute(
        """INSERT INTO demo_accounts (user_id, balance, initial_balance)
           VALUES (?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET
               balance=excluded.balance, initial_balance=excluded.initial_balance""",
        (demo.user_id, demo.balance, demo.initial_balance),
    )
    await db.db.commit()


async def delete_demo(db: Database, user_id: int) -> None:
    await db.db.execute("DELETE FROM demo_accounts WHERE user_id = ?", (user_id,))
    await db.db.commit()
