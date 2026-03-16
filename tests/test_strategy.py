import pytest
from datetime import datetime

from bot.db.models import Position, PositionStatus, TradingSettings
from bot.trading.strategy import ScalpStrategy


@pytest.fixture
def strategy():
    return ScalpStrategy()


@pytest.fixture
def settings():
    return TradingSettings(user_id=1, profit_pct=0.7, drop_pct=0.6)


def _pos(buy_price: float) -> Position:
    return Position(
        user_id=1, pair="BTCUSDC", buy_price=buy_price, buy_qty=0.001,
        buy_cost=buy_price * 0.001, buy_order_id="o1",
        buy_filled_at=datetime.utcnow(), sell_target_price=buy_price * 1.007,
        status=PositionStatus.SELLING, sell_order_id="s1",
    )


def test_should_buy_no_positions(strategy, settings):
    assert strategy.should_buy(85000.0, [], settings) is True


def test_should_buy_price_dropped_enough(strategy, settings):
    positions = [_pos(85000.0)]
    # drop_pct=0.6 → target = 85000 * 0.994 = 84490
    assert strategy.should_buy(84400.0, positions, settings) is True


def test_should_not_buy_price_not_dropped(strategy, settings):
    positions = [_pos(85000.0)]
    assert strategy.should_buy(84800.0, positions, settings) is False


def test_get_last_buy_price(strategy):
    positions = [_pos(85000.0), _pos(84000.0)]
    assert strategy.get_last_buy_price(positions) == 84000.0


def test_get_last_buy_price_empty(strategy):
    assert strategy.get_last_buy_price([]) is None
