from __future__ import annotations

from bot.db.models import Position, PositionStatus, TradingSettings
from bot.trading.calculator import compute_drop_price


class ScalpStrategy:
    """Scalping strategy: buy on drop, sell on profit target.

    Buy triggers:
    1. No open positions → always buy (first position)
    2. Price dropped by drop_pct from the last buy price → buy more

    Sell is handled by limit orders on the exchange (not by strategy).
    """

    def should_buy(
        self,
        current_price: float,
        positions: list[Position],
        settings: TradingSettings,
    ) -> bool:
        """Decide whether to open a new position at current_price."""
        # Filter only active positions
        active = [p for p in positions if p.status != PositionStatus.CLOSED]

        if not active:
            return True

        # Find the most recent buy price among active positions
        last_buy_price = active[-1].buy_price

        # Check if price has dropped enough
        drop_target = compute_drop_price(last_buy_price, settings.drop_pct)
        return current_price <= drop_target

    def get_last_buy_price(self, positions: list[Position]) -> float | None:
        """Get the last buy price from active positions."""
        active = [p for p in positions if p.status != PositionStatus.CLOSED]
        if not active:
            return None
        return active[-1].buy_price
