from __future__ import annotations

import asyncio
from datetime import datetime

import structlog

from bot.db.database import Database
from bot.db.models import DemoAccount, Position, PositionStatus, TradingSettings
from bot.db import queries
from bot.exchange.websocket import MexcWebSocket
from bot.trading.calculator import (
    compute_order_size,
    compute_sell_price,
    compute_drop_price,
    compute_expected_income,
    MIN_ORDER_USDT,
)
from bot.trading.strategy import ScalpStrategy
from bot.utils.formatting import format_buy, format_sell, format_price_drop

log = structlog.get_logger()


class DemoEngine:
    """Virtual trading engine for demo mode.

    Simulates trades on real market prices but with a virtual $5000 balance.
    No actual orders are placed on the exchange.
    """

    def __init__(
        self,
        user_id: int,
        settings: TradingSettings,
        db: Database,
        send_message,  # Callable[[str], Awaitable[None]]
    ) -> None:
        self.user_id = user_id
        self.settings = settings
        self._db = db
        self._send = send_message

        self._strategy = ScalpStrategy()
        self._demo: DemoAccount | None = None
        self._positions: list[_DemoPosition] = []
        self._ws: MexcWebSocket | None = None
        self._task: asyncio.Task | None = None
        self._running = False
        self._current_price: float = 0.0

    async def start(self) -> None:
        # Init or load demo account
        self._demo = await queries.get_demo(self._db, self.user_id)
        if not self._demo:
            self._demo = DemoAccount(user_id=self.user_id)
            await queries.upsert_demo(self._db, self._demo)

        self._running = True
        self._ws = MexcWebSocket(
            symbols=[self.settings.pair],
            on_price_update=self._on_price,
        )
        await self._ws.start()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._ws:
            await self._ws.stop()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def delete(self) -> None:
        await self.stop()
        await queries.delete_demo(self._db, self.user_id)

    async def _on_price(self, symbol: str, price: float) -> None:
        self._current_price = price

    async def _loop(self) -> None:
        try:
            # Wait for first price
            for _ in range(30):
                await asyncio.sleep(1)
                if self._current_price > 0:
                    break

            if self._current_price <= 0:
                return

            # Initial buy
            await self._try_buy()

            while self._running:
                await asyncio.sleep(5)
                if not self._running:
                    break

                # Check sells
                for pos in list(self._positions):
                    if self._current_price >= pos.sell_target:
                        revenue = pos.qty * pos.sell_target
                        profit = revenue - pos.cost
                        self._demo.balance += revenue  # type: ignore
                        self._positions.remove(pos)

                        await self._send(format_sell(
                            pair=self.settings.pair,
                            qty=pos.qty,
                            revenue=revenue,
                            price=pos.sell_target,
                            profit=profit,
                            is_demo=True,
                        ))
                        await self._try_buy()

                # Check drop buy
                if self._positions:
                    last = self._positions[-1]
                    drop_target = compute_drop_price(last.buy_price, self.settings.drop_pct)
                    if self._current_price <= drop_target:
                        await self._send(format_price_drop(
                            pair=self.settings.pair,
                            drop_pct=self.settings.drop_pct,
                            from_price=last.buy_price,
                            is_demo=True,
                        ))
                        await self._try_buy()

        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error("demo_error", user_id=self.user_id, error=str(e))

    async def _try_buy(self) -> None:
        if not self._demo or self._current_price <= 0:
            return

        free = self._demo.balance
        capital = free + sum(p.cost for p in self._positions)

        size = compute_order_size(self.settings, free, capital)
        if size is None or size < MIN_ORDER_USDT:
            return

        qty = size / self._current_price
        sell_target = compute_sell_price(self._current_price, self.settings.profit_pct)
        expected = compute_expected_income(size, self.settings.profit_pct, self.settings.taker_fee)

        self._demo.balance -= size
        pos = _DemoPosition(
            buy_price=self._current_price,
            qty=qty,
            cost=size,
            sell_target=sell_target,
        )
        self._positions.append(pos)

        await queries.upsert_demo(self._db, self._demo)

        await self._send(format_buy(
            pair=self.settings.pair,
            qty=qty,
            cost=size,
            price=self._current_price,
            sell_price=sell_target,
            expected_income=expected,
            is_demo=True,
        ))


class _DemoPosition:
    __slots__ = ("buy_price", "qty", "cost", "sell_target")

    def __init__(self, buy_price: float, qty: float, cost: float, sell_target: float):
        self.buy_price = buy_price
        self.qty = qty
        self.cost = cost
        self.sell_target = sell_target
