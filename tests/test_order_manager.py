import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from bot.db.database import Database
from bot.db.models import Position, PositionStatus, TradingSettings
from bot.db import queries
from bot.exchange.client import MexcClient, InsufficientBalance, MexcError
from bot.exchange.models import OrderResult, OrderSide, OrderStatus, OpenOrder
from bot.trading.order_manager import OrderManager


@pytest_asyncio.fixture
async def db(tmp_db: Database):
    await queries.upsert_user(tmp_db, 1, "test")
    await queries.upsert_settings(tmp_db, TradingSettings(user_id=1))
    return tmp_db


@pytest.fixture
def mock_client():
    client = AsyncMock(spec=MexcClient)
    return client


@pytest.fixture
def order_manager(mock_client, db):
    return OrderManager(mock_client, db)


# ─── execute_buy ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_buy_success(order_manager, mock_client, db):
    mock_client.place_market_buy.return_value = OrderResult(
        order_id="buy1", symbol="BTCUSDC", side=OrderSide.BUY,
        status=OrderStatus.FILLED, price=85000.0, qty=0.001, cost=85.0,
    )
    mock_client.place_limit_sell.return_value = OrderResult(
        order_id="sell1", symbol="BTCUSDC", side=OrderSide.SELL,
        status=OrderStatus.NEW, price=85595.0, qty=0.001, cost=0,
    )

    pos = await order_manager.execute_buy(1, "BTCUSDC", 85.0, 0.7)
    assert pos is not None
    assert pos.buy_order_id == "buy1"
    assert pos.sell_order_id == "sell1"
    assert pos.status == PositionStatus.SELLING

    # Check saved in DB
    active = await queries.get_active_positions(db, 1)
    assert len(active) == 1


@pytest.mark.asyncio
async def test_execute_buy_insufficient_balance(order_manager, mock_client):
    mock_client.place_market_buy.side_effect = InsufficientBalance(10101, "insufficient")

    pos = await order_manager.execute_buy(1, "BTCUSDC", 85.0, 0.7)
    assert pos is None


@pytest.mark.asyncio
async def test_execute_buy_sell_placement_fails(order_manager, mock_client, db):
    """If sell order placement fails, position stays OPEN for retry."""
    mock_client.place_market_buy.return_value = OrderResult(
        order_id="buy1", symbol="BTCUSDC", side=OrderSide.BUY,
        status=OrderStatus.FILLED, price=85000.0, qty=0.001, cost=85.0,
    )
    mock_client.place_limit_sell.side_effect = MexcError(0, "network error")

    pos = await order_manager.execute_buy(1, "BTCUSDC", 85.0, 0.7)
    assert pos is not None
    assert pos.status == PositionStatus.OPEN
    assert pos.sell_order_id is None


# ─── check_sell_fills ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_sell_fills_detects_closed(order_manager, mock_client, db):
    # Create a selling position
    pos = Position(
        user_id=1, pair="BTCUSDC", buy_price=85000.0, buy_qty=0.001,
        buy_cost=85.0, buy_order_id="b1", buy_filled_at=datetime.utcnow(),
        sell_order_id="s1", sell_target_price=85595.0,
        status=PositionStatus.SELLING,
    )
    pos.id = await queries.save_position(db, pos)
    await queries.update_position_sell(db, pos.id, "s1")

    # Exchange returns empty open orders → sell was filled
    mock_client.get_open_orders.return_value = []

    closed = await order_manager.check_sell_fills(1, "BTCUSDC", [pos])
    assert len(closed) == 1
    assert closed[0].status == PositionStatus.CLOSED
    assert closed[0].profit is not None


@pytest.mark.asyncio
async def test_check_sell_fills_still_open(order_manager, mock_client, db):
    pos = Position(
        user_id=1, pair="BTCUSDC", buy_price=85000.0, buy_qty=0.001,
        buy_cost=85.0, buy_order_id="b1", buy_filled_at=datetime.utcnow(),
        sell_order_id="s1", sell_target_price=85595.0,
        status=PositionStatus.SELLING,
    )
    pos.id = await queries.save_position(db, pos)

    # Exchange still has the order
    mock_client.get_open_orders.return_value = [
        OpenOrder(order_id="s1", symbol="BTCUSDC", side=OrderSide.SELL,
                  price=85595.0, qty=0.001, status=OrderStatus.NEW)
    ]

    closed = await order_manager.check_sell_fills(1, "BTCUSDC", [pos])
    assert len(closed) == 0
