from __future__ import annotations

from datetime import datetime

import structlog

from bot.db.database import Database
from bot.db.models import Position, PositionStatus
from bot.db import queries
from bot.exchange.client import MexcClient, InsufficientBalance, MexcError
from bot.exchange.models import OrderSide, OpenOrder
from bot.trading.calculator import compute_sell_price
from bot.utils.formatting import PAIR_QTY_PRECISION, PAIR_PRICE_PRECISION

log = structlog.get_logger()


class OrderManager:
    """Manages the lifecycle of buy and sell orders on MEXC."""

    def __init__(self, client: MexcClient, db: Database) -> None:
        self._client = client
        self._db = db

    async def execute_buy(
        self,
        user_id: int,
        symbol: str,
        quote_qty: float,
        profit_pct: float,
    ) -> Position | None:
        """Place a market buy, then a limit sell. Returns the new Position or None on failure."""
        try:
            buy_result = await self._client.place_market_buy(symbol, quote_qty)
        except InsufficientBalance:
            log.warning("buy_insufficient_balance", user_id=user_id, qty=quote_qty)
            return None
        except MexcError as e:
            log.error("buy_failed", user_id=user_id, error=str(e))
            return None

        if buy_result.qty <= 0:
            log.error("buy_zero_qty", user_id=user_id, result=buy_result)
            return None

        # Actual fill price
        fill_price = buy_result.cost / buy_result.qty if buy_result.qty else 0
        sell_target = compute_sell_price(fill_price, profit_pct)

        # Round sell price to exchange precision
        price_prec = PAIR_PRICE_PRECISION.get(symbol, 6)
        sell_target = round(sell_target, price_prec)

        # Round qty to exchange precision
        qty_prec = PAIR_QTY_PRECISION.get(symbol, 2)
        sell_qty = round(buy_result.qty, qty_prec)

        # Save position to DB before placing sell (crash safety)
        position = Position(
            user_id=user_id,
            pair=symbol,
            buy_price=fill_price,
            buy_qty=sell_qty,
            buy_cost=buy_result.cost,
            buy_order_id=buy_result.order_id,
            buy_filled_at=datetime.utcnow(),
            sell_target_price=sell_target,
            status=PositionStatus.OPEN,
        )
        position.id = await queries.save_position(self._db, position)

        # Place limit sell
        try:
            sell_result = await self._client.place_limit_sell(
                symbol, sell_qty, sell_target
            )
            position.sell_order_id = sell_result.order_id
            position.status = PositionStatus.SELLING
            await queries.update_position_sell(
                self._db, position.id, sell_result.order_id  # type: ignore[arg-type]
            )
        except MexcError as e:
            log.error(
                "sell_placement_failed",
                user_id=user_id,
                position_id=position.id,
                error=str(e),
            )
            # Position stays OPEN — will retry on next cycle

        return position

    async def check_sell_fills(
        self,
        user_id: int,
        symbol: str,
        positions: list[Position],
    ) -> list[Position]:
        """Poll open orders on exchange and detect filled sells.

        Returns list of positions that were just closed (sell filled).
        """
        if not positions:
            return []

        selling = [p for p in positions if p.status == PositionStatus.SELLING and p.sell_order_id]
        if not selling:
            return []

        try:
            exchange_orders = await self._client.get_open_orders(symbol)
        except MexcError as e:
            log.warning("poll_orders_failed", error=str(e))
            return []

        exchange_order_ids = {o.order_id for o in exchange_orders}
        closed: list[Position] = []

        for pos in selling:
            if pos.sell_order_id not in exchange_order_ids:
                # Sell order no longer on exchange → filled
                revenue = pos.sell_target_price * pos.buy_qty
                profit = revenue - pos.buy_cost
                await queries.close_position(
                    self._db, pos.id, revenue, profit  # type: ignore[arg-type]
                )
                pos.status = PositionStatus.CLOSED
                pos.sell_revenue = revenue
                pos.profit = profit
                closed.append(pos)
                log.info(
                    "position_closed",
                    user_id=user_id,
                    position_id=pos.id,
                    profit=profit,
                )

        return closed

    async def retry_pending_sells(
        self,
        user_id: int,
        symbol: str,
        positions: list[Position],
        profit_pct: float,
    ) -> None:
        """Retry placing sell orders for positions stuck in OPEN status."""
        open_no_sell = [
            p for p in positions
            if p.status == PositionStatus.OPEN and not p.sell_order_id
        ]
        for pos in open_no_sell:
            price_prec = PAIR_PRICE_PRECISION.get(symbol, 6)
            sell_target = round(
                compute_sell_price(pos.buy_price, profit_pct), price_prec
            )
            qty_prec = PAIR_QTY_PRECISION.get(symbol, 2)
            sell_qty = round(pos.buy_qty, qty_prec)

            try:
                sell_result = await self._client.place_limit_sell(
                    symbol, sell_qty, sell_target
                )
                pos.sell_order_id = sell_result.order_id
                pos.status = PositionStatus.SELLING
                await queries.update_position_sell(
                    self._db, pos.id, sell_result.order_id  # type: ignore[arg-type]
                )
                log.info("retry_sell_placed", position_id=pos.id)
            except MexcError as e:
                log.warning("retry_sell_failed", position_id=pos.id, error=str(e))
