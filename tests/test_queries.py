import pytest
import pytest_asyncio
from datetime import datetime, timedelta

from bot.db.database import Database
from bot.db.models import (
    DemoAccount,
    OrderType,
    Position,
    PositionStatus,
    TradingSettings,
)
from bot.db import queries


# ─── Users ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upsert_and_get_user(tmp_db: Database):
    await queries.upsert_user(tmp_db, 123, "alice")
    user = await queries.get_user(tmp_db, 123)
    assert user is not None
    assert user.id == 123
    assert user.username == "alice"


@pytest.mark.asyncio
async def test_get_nonexistent_user(tmp_db: Database):
    user = await queries.get_user(tmp_db, 999)
    assert user is None


@pytest.mark.asyncio
async def test_save_api_keys(tmp_db: Database):
    await queries.upsert_user(tmp_db, 1, "bob")
    await queries.save_api_keys(tmp_db, 1, b"enc_key", b"enc_secret")
    user = await queries.get_user(tmp_db, 1)
    assert user is not None
    assert user.api_key_enc == b"enc_key"
    assert user.api_secret_enc == b"enc_secret"


# ─── Settings ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upsert_and_get_settings(tmp_db: Database):
    await queries.upsert_user(tmp_db, 1, "test")
    s = TradingSettings(user_id=1, pair="KASUSDT", profit_pct=0.6, drop_pct=0.9)
    await queries.upsert_settings(tmp_db, s)

    result = await queries.get_settings(tmp_db, 1)
    assert result is not None
    assert result.pair == "KASUSDT"
    assert result.profit_pct == 0.6
    assert result.drop_pct == 0.9


@pytest.mark.asyncio
async def test_settings_update(tmp_db: Database):
    await queries.upsert_user(tmp_db, 1, "test")
    s = TradingSettings(user_id=1, pair="BTCUSDC")
    await queries.upsert_settings(tmp_db, s)

    s.pair = "SOLUSDT"
    s.profit_pct = 1.5
    await queries.upsert_settings(tmp_db, s)

    result = await queries.get_settings(tmp_db, 1)
    assert result is not None
    assert result.pair == "SOLUSDT"
    assert result.profit_pct == 1.5


# ─── Positions ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_and_get_positions(tmp_db: Database):
    await queries.upsert_user(tmp_db, 1, "test")
    pos = Position(
        user_id=1,
        pair="BTCUSDC",
        buy_price=85000.0,
        buy_qty=0.001,
        buy_cost=85.0,
        buy_order_id="o1",
        buy_filled_at=datetime.utcnow(),
        sell_target_price=85595.0,
        status=PositionStatus.OPEN,
    )
    pid = await queries.save_position(tmp_db, pos)
    assert pid is not None

    active = await queries.get_active_positions(tmp_db, 1)
    assert len(active) == 1
    assert active[0].buy_price == 85000.0


@pytest.mark.asyncio
async def test_close_position(tmp_db: Database):
    await queries.upsert_user(tmp_db, 1, "test")
    pos = Position(
        user_id=1, pair="BTCUSDC", buy_price=100.0, buy_qty=1.0,
        buy_cost=100.0, buy_order_id="o1", buy_filled_at=datetime.utcnow(),
        sell_target_price=100.7, status=PositionStatus.SELLING,
        sell_order_id="s1",
    )
    pid = await queries.save_position(tmp_db, pos)
    await queries.close_position(tmp_db, pid, sell_revenue=100.7, profit=0.7)

    active = await queries.get_active_positions(tmp_db, 1)
    assert len(active) == 0

    closed = await queries.get_all_closed_positions(tmp_db, 1)
    assert len(closed) == 1
    assert closed[0].profit == pytest.approx(0.7)


@pytest.mark.asyncio
async def test_positions_for_period(tmp_db: Database):
    await queries.upsert_user(tmp_db, 1, "test")
    now = datetime.utcnow()

    pos = Position(
        user_id=1, pair="BTCUSDC", buy_price=100.0, buy_qty=1.0,
        buy_cost=100.0, buy_order_id="o1", buy_filled_at=now,
        sell_target_price=100.7, status=PositionStatus.SELLING,
        sell_order_id="s1",
    )
    pid = await queries.save_position(tmp_db, pos)
    await queries.close_position(tmp_db, pid, sell_revenue=100.7, profit=0.7)

    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    period = await queries.get_positions_for_period(tmp_db, 1, start, end)
    assert len(period) == 1


# ─── Demo ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_demo_crud(tmp_db: Database):
    await queries.upsert_user(tmp_db, 1, "test")
    demo = DemoAccount(user_id=1, balance=5000.0)
    await queries.upsert_demo(tmp_db, demo)

    result = await queries.get_demo(tmp_db, 1)
    assert result is not None
    assert result.balance == 5000.0

    await queries.delete_demo(tmp_db, 1)
    result = await queries.get_demo(tmp_db, 1)
    assert result is None
