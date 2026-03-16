import pytest

from bot.db.models import OrderType, TradingSettings
from bot.trading.calculator import (
    compute_drop_price,
    compute_expected_income,
    compute_order_size,
    compute_sell_price,
    MIN_ORDER_USDT,
)


# ─── compute_order_size ──────────────────────────────────────────────────────


class TestComputeOrderSize:
    def _settings(self, order_type=OrderType.DYNAMIC, order_param=2.0):
        return TradingSettings(
            user_id=1, order_type=order_type, order_param=order_param
        )

    def test_dynamic_normal(self):
        """2% of 1000 capital = 20 USDT."""
        size = compute_order_size(self._settings(), free_balance=1000, total_capital=1000)
        assert size == 20.0

    def test_dynamic_shrink_when_low_free(self):
        """When free < 50% of capital, proportional shrink."""
        # free=200, capital=1000 → ratio=0.2, shrink=0.2/0.5=0.4
        # base_size=20, shrunk=20*0.4=8
        size = compute_order_size(self._settings(), free_balance=200, total_capital=1000)
        assert size == 8.0

    def test_dynamic_capped_by_free(self):
        """Size capped by free balance when smaller than base_size."""
        # 10% of 100 = 10, free=60 → ratio=0.6 > 0.5 (no shrink) → min(10, 60)=10
        s = self._settings(order_param=10.0)
        size = compute_order_size(s, free_balance=60.0, total_capital=100)
        assert size == 10.0

        # free < base_size → capped: 10% of 100 = 10, free=5 → ratio=0.05 < 0.5
        # shrink = 0.05/0.5 = 0.1, shrunk = 10*0.1 = 1.0 < MIN → returns None
        size2 = compute_order_size(s, free_balance=5.0, total_capital=100)
        assert size2 is None  # shrunk below minimum

    def test_fixed_normal(self):
        size = compute_order_size(
            self._settings(OrderType.FIXED, 50.0), free_balance=100, total_capital=200
        )
        assert size == 50.0

    def test_fixed_capped_by_free(self):
        size = compute_order_size(
            self._settings(OrderType.FIXED, 50.0), free_balance=30, total_capital=100
        )
        assert size == 30.0

    def test_returns_none_below_minimum(self):
        size = compute_order_size(self._settings(), free_balance=1.0, total_capital=50)
        assert size is None

    def test_returns_none_when_zero_balance(self):
        size = compute_order_size(self._settings(), free_balance=0, total_capital=0)
        assert size is None


# ─── compute_sell_price ──────────────────────────────────────────────────────


class TestComputeSellPrice:
    def test_basic(self):
        assert compute_sell_price(100.0, 0.7) == pytest.approx(100.7)

    def test_btc_typical(self):
        price = compute_sell_price(85000.0, 0.7)
        assert price == pytest.approx(85595.0)


# ─── compute_drop_price ──────────────────────────────────────────────────────


class TestComputeDropPrice:
    def test_basic(self):
        assert compute_drop_price(100.0, 0.6) == pytest.approx(99.4)

    def test_large_drop(self):
        assert compute_drop_price(100.0, 10.0) == pytest.approx(90.0)


# ─── compute_expected_income ─────────────────────────────────────────────────


class TestComputeExpectedIncome:
    def test_no_fee(self):
        income = compute_expected_income(100.0, 0.7, taker_fee=0.0)
        assert income == pytest.approx(0.7)

    def test_with_taker_fee(self):
        # gross = 100 * 0.007 = 0.7
        # fee = 100 * 0.0005 * 2 = 0.1
        # net = 0.6
        income = compute_expected_income(100.0, 0.7, taker_fee=0.05)
        assert income == pytest.approx(0.6)
