from __future__ import annotations

from bot.db.models import OrderType, TradingSettings

# Minimum order size in quote currency (MEXC minimum is ~1 USDT, we use 2 for safety)
MIN_ORDER_USDT = 2.0


def compute_order_size(
    settings: TradingSettings,
    free_balance: float,
    total_capital: float,
) -> float | None:
    """Compute order size in quote currency (USDT/USDC).

    Returns None if the computed size is below minimum or balance is insufficient.
    """
    if free_balance < MIN_ORDER_USDT:
        return None

    if settings.order_type == OrderType.DYNAMIC:
        base_size = total_capital * (settings.order_param / 100)
        if total_capital > 0:
            free_ratio = free_balance / total_capital
            if free_ratio < 0.5:
                # Proportional shrink when free balance < 50% of capital
                base_size = base_size * (free_ratio / 0.5)
        size = min(base_size, free_balance)
    else:
        # Fixed order
        size = min(settings.order_param, free_balance)

    if size < MIN_ORDER_USDT:
        return None

    return round(size, 2)


def compute_sell_price(buy_price: float, profit_pct: float) -> float:
    """Compute limit sell target price."""
    return buy_price * (1 + profit_pct / 100)


def compute_drop_price(last_buy_price: float, drop_pct: float) -> float:
    """Compute price at which a new buy should trigger."""
    return last_buy_price * (1 - drop_pct / 100)


def compute_expected_income(buy_cost: float, profit_pct: float, taker_fee: float) -> float:
    """Compute expected income from a position after fees."""
    gross = buy_cost * (profit_pct / 100)
    fee = buy_cost * (taker_fee / 100) * 2  # fee on buy + sell
    return round(gross - fee, 2)
