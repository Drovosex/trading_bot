from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import structlog

from bot.db.database import Database
from bot.db.models import Position, PositionStatus, TradingSettings
from bot.db import queries
from bot.exchange.client import MexcClient, InsufficientBalance, InvalidApiKey, MexcError, NetworkError
from bot.exchange.websocket import MexcWebSocket
from bot.trading.calculator import (
    compute_order_size,
    compute_drop_price,
    compute_expected_income,
    compute_sell_price,
    OrderTooSmall,
)
from bot.trading.order_manager import OrderManager
from bot.trading.state import EngineState
from bot.trading.strategy import ScalpStrategy
from bot.utils.formatting import (
    format_buy,
    format_sell,
    format_price_drop,
    format_insufficient_funds,
    PAIR_INFO,
)

log = structlog.get_logger()

# Adaptive polling intervals (seconds)
POLL_INTERVAL_NO_POSITIONS = 30  # Just check WS is alive
POLL_INTERVAL_FEW = 5            # 1-5 positions
POLL_INTERVAL_MANY = 3           # 6+ positions
WS_FAILURE_NOTIFY_THRESHOLD = 5
API_KEY_ERROR_LIMIT = 5          # Auto-stop after this many consecutive auth failures
NETWORK_ERROR_LIMIT = 10         # Notify user after this many consecutive network errors
NETWORK_BACKOFF_MAX = 60         # Max backoff seconds on network errors


class TradingEngine:
    """Orchestrates trading for a single user.

    Runs as an asyncio.Task: monitors price via WebSocket,
    triggers buys via ScalpStrategy, polls sell fills via OrderManager.
    """

    def __init__(
        self,
        user_id: int,
        settings: TradingSettings,
        client: MexcClient,
        db: Database,
        send_message,  # Callable[[str], Awaitable[None]]
    ) -> None:
        self.user_id = user_id
        self.settings = settings
        self._client = client
        self._db = db
        self._send = send_message

        self._strategy = ScalpStrategy()
        self._order_manager = OrderManager(client, db)

        self.state = EngineState.IDLE
        self.positions: list[Position] = []
        self.current_price: float = 0.0
        self._ws: MexcWebSocket | None = None
        self._task: asyncio.Task | None = None
        self._last_buy_check_price: float = 0.0
        # Active position: only this one triggers a new buy when its sell fills.
        # Drop-buy also replaces the active position.
        self._active_position_id: int | None = None
        self._consecutive_auth_errors: int = 0
        self._consecutive_network_errors: int = 0

    # ─── Public API ──────────────────────────────────────────────────

    async def start(self) -> None:
        if self.state == EngineState.RUNNING:
            return

        self.state = EngineState.STARTING
        log.info("engine_starting", user_id=self.user_id, pair=self.settings.pair)

        # Load active positions from DB (crash recovery)
        self.positions = await queries.get_active_positions(self._db, self.user_id)

        # The last position is the active one (most recent buy)
        if self.positions:
            self._active_position_id = self.positions[-1].id
            log.info("active_position_restored", position_id=self._active_position_id)

        # Reconcile with exchange
        await self._reconcile()

        # Retry any stuck sells
        await self._order_manager.retry_pending_sells(
            self.user_id, self.settings.pair, self.positions, self.settings.profit_pct
        )

        # Fetch initial price via REST (WS may be slow for low-volume pairs)
        try:
            self.current_price = await self._client.get_ticker_price(self.settings.pair)
            log.info("initial_price_fetched", pair=self.settings.pair, price=self.current_price)
        except MexcError as e:
            log.warning("initial_price_failed", error=str(e))

        # Start WebSocket price monitor
        self._ws = MexcWebSocket(
            symbols=[self.settings.pair],
            on_price_update=self._on_price_update,
        )
        await self._ws.start()

        # Start main trading loop + REST price fallback
        self.state = EngineState.RUNNING
        self._task = asyncio.create_task(self._main_loop())
        self._rest_price_task = asyncio.create_task(self._rest_price_loop())

    async def stop(self) -> None:
        if self.state not in (EngineState.RUNNING, EngineState.STARTING):
            return

        self.state = EngineState.STOPPING
        log.info("engine_stopping", user_id=self.user_id)

        if self._ws:
            await self._ws.stop()
        for task in (self._task, getattr(self, "_rest_price_task", None)):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._task = None

        await self._client.close()
        self.state = EngineState.IDLE

    # ─── Price callback ──────────────────────────────────────────────

    async def _on_price_update(self, symbol: str, price: float) -> None:
        self.current_price = price

    # ─── Main loop ───────────────────────────────────────────────────

    async def _main_loop(self) -> None:
        try:
            # Initial buy on start — becomes the active position
            await self._try_buy()

            while self.state == EngineState.RUNNING:
                poll_interval = self._get_poll_interval()
                await asyncio.sleep(poll_interval)

                if self.state != EngineState.RUNNING:
                    break

                # Check WS health
                if self._ws and self._ws.consecutive_failures >= WS_FAILURE_NOTIFY_THRESHOLD:
                    await self._send("⚠️ Проблемы с подключением к бирже. Проверяю...")

                # Check sell fills
                try:
                    closed = await self._order_manager.check_sell_fills(
                        self.user_id, self.settings.pair, self.positions
                    )
                    self._consecutive_auth_errors = 0
                    self._consecutive_network_errors = 0
                except InvalidApiKey:
                    self._consecutive_auth_errors += 1
                    if self._consecutive_auth_errors >= API_KEY_ERROR_LIMIT:
                        log.error("api_key_invalid_auto_stop", user_id=self.user_id,
                                  errors=self._consecutive_auth_errors)
                        await self._send(
                            "🔴 Алгоритм остановлен\n\n"
                            "API ключи недействительны.\n"
                            "Обновите ключи: /set_api\n"
                            "Затем запустите торговлю заново."
                        )
                        break
                    continue
                except NetworkError as e:
                    self._consecutive_network_errors += 1
                    backoff = min(
                        self._consecutive_network_errors * 5,
                        NETWORK_BACKOFF_MAX,
                    )
                    log.warning("network_error",
                                error=str(e),
                                consecutive=self._consecutive_network_errors,
                                backoff=backoff)
                    if self._consecutive_network_errors == NETWORK_ERROR_LIMIT:
                        await self._send(
                            "⚠️ Проблемы с сетью, алгоритм продолжает работу...\n"
                            "Попытка переподключения."
                        )
                        # Recreate HTTP session to clear stale connections
                        await self._client.close()
                    await asyncio.sleep(backoff)
                    continue
                except MexcError:
                    continue
                else:
                    for pos in closed:
                        self.positions.remove(pos)
                        await self._notify_sell(pos)

                        # Only the ACTIVE position triggers a new buy
                        if pos.id == self._active_position_id:
                            log.info("active_sell_filled", position_id=pos.id)
                            self._active_position_id = None
                            await self._try_buy()

                # Check for price-drop buy trigger (replaces active position)
                if self.current_price > 0:
                    await self._check_drop_buy()

        except asyncio.CancelledError:
            return
        except Exception as e:
            log.error("engine_error", user_id=self.user_id, error=str(e))
            await self._send(f"⚠️ Ошибка торгового алгоритма: {e}\nАлгоритм остановлен.")

        # Auto-cleanup when loop exits (auth error, unexpected error)
        await self._auto_cleanup()

    async def force_buy(self) -> None:
        """Force an immediate market buy, ignoring strategy conditions.
        Falls back to REST API price if WebSocket price is unavailable.
        """
        log.info("force_buy_triggered", user_id=self.user_id)

        # If WS hasn't provided a price yet, fetch via REST
        if self.current_price <= 0:
            try:
                self.current_price = await self._client.get_ticker_price(self.settings.pair)
                log.info("force_buy_rest_price", price=self.current_price)
            except MexcError as e:
                await self._send(f"❌ Не удалось получить цену: {e}")
                return

        await self._try_buy()

    # ─── Buy logic ───────────────────────────────────────────────────

    async def _try_buy(self) -> None:
        """Attempt to open a new position."""
        if self.current_price <= 0:
            # Wait for first price tick
            for _ in range(30):
                await asyncio.sleep(1)
                if self.current_price > 0:
                    break
            if self.current_price <= 0:
                log.warning("buy_no_price", user_id=self.user_id, pair=self.settings.pair)
                await self._send(
                    "⚠️ Не удалось получить текущую цену.\n"
                    "Попробуйте /buy для немедленной покупки."
                )
                return

        # Get balance
        quote_asset = PAIR_INFO.get(self.settings.pair, ("", "USDT"))[1]
        try:
            balance = await self._client.get_balance(quote_asset)
        except MexcError:
            return

        free = balance.free
        capital = free + sum(p.buy_cost for p in self.positions if p.status != PositionStatus.CLOSED)

        try:
            size = compute_order_size(self.settings, free, capital)
        except OrderTooSmall as e:
            order_type_label = "динамический" if self.settings.order_type.value == "dynamic" else "фиксированный"
            await self._send(
                f"⚠️ Размер ордера слишком мал\n\n"
                f"Тип: {order_type_label}, параметр: {self.settings.order_param}\n"
                f"Рассчитанный размер: {e.computed:.2f} {quote_asset}\n"
                f"Минимум биржи: {e.minimum:.2f} {quote_asset}\n\n"
                f"💡 Увеличьте размер ордера через /settings\n"
                f"или переключитесь на фиксированный ордер."
            )
            return
        if size is None:
            await self._send(
                format_insufficient_funds(free, self.settings.order_param, quote_asset)
            )
            return

        position = await self._order_manager.execute_buy(
            self.user_id, self.settings.pair, size, self.settings.profit_pct,
        )
        if position:
            self.positions.append(position)
            self._last_buy_check_price = position.buy_price
            # This position becomes the active one
            self._active_position_id = position.id
            log.info("active_position_set", position_id=position.id)
            await self._notify_buy(position)
        else:
            await self._send(
                "❌ Покупка не выполнена.\n"
                "Проверьте логи или попробуйте ещё раз: /buy"
            )

    async def _check_drop_buy(self) -> None:
        """Check if price has dropped enough to trigger a new buy."""
        if not self._strategy.should_buy(
            self.current_price, self.positions, self.settings
        ):
            return

        # Notify price drop
        last_price = self._strategy.get_last_buy_price(self.positions)
        if last_price:
            await self._send(
                format_price_drop(
                    self.settings.pair, self.settings.drop_pct, last_price
                )
            )

        await self._try_buy()

    # ─── Reconciliation ──────────────────────────────────────────────

    async def _reconcile(self) -> None:
        """Reconcile DB positions with exchange state on startup."""
        if not self.positions:
            return

        try:
            exchange_orders = await self._client.get_open_orders(self.settings.pair)
        except MexcError as e:
            log.warning("reconcile_failed", error=str(e))
            return

        exchange_ids = {o.order_id for o in exchange_orders}

        for pos in list(self.positions):
            if pos.status == PositionStatus.SELLING and pos.sell_order_id:
                if pos.sell_order_id not in exchange_ids:
                    # Sell was filled while we were offline
                    revenue = pos.sell_target_price * pos.buy_qty
                    profit = revenue - pos.buy_cost
                    await queries.close_position(self._db, pos.id, revenue, profit)  # type: ignore
                    pos.status = PositionStatus.CLOSED
                    self.positions.remove(pos)
                    log.info("reconciled_closed", position_id=pos.id)

    # ─── Notifications ───────────────────────────────────────────────

    async def _notify_buy(self, pos: Position) -> None:
        expected = compute_expected_income(
            pos.buy_cost, self.settings.profit_pct, self.settings.taker_fee
        )
        is_active = (pos.id == self._active_position_id)
        msg = format_buy(
            pair=pos.pair,
            qty=pos.buy_qty,
            cost=pos.buy_cost,
            price=pos.buy_price,
            sell_price=pos.sell_target_price,
            expected_income=expected,
        )
        if is_active:
            msg += "\n\n🔄 Активный ордер"
        await self._send(msg)

    async def _notify_sell(self, pos: Position) -> None:
        msg = format_sell(
            pair=pos.pair,
            qty=pos.buy_qty,
            revenue=pos.sell_revenue or 0,
            price=pos.sell_target_price,
            profit=pos.profit or 0,
        )
        await self._send(msg)

    # ─── Auto-cleanup ───────────────────────────────────────────────

    async def _auto_cleanup(self) -> None:
        """Clean up resources when main loop exits abnormally."""
        self.state = EngineState.ERROR
        if self._ws:
            await self._ws.stop()
        rest_task = getattr(self, "_rest_price_task", None)
        if rest_task:
            rest_task.cancel()
            try:
                await rest_task
            except asyncio.CancelledError:
                pass
        await self._client.close()
        log.info("engine_auto_cleanup", user_id=self.user_id)

    # ─── REST price fallback ────────────────────────────────────────

    async def _rest_price_loop(self) -> None:
        """Periodically fetch price via REST for low-volume pairs where WS may not send updates."""
        try:
            while self.state == EngineState.RUNNING:
                await asyncio.sleep(15)
                try:
                    price = await self._client.get_ticker_price(self.settings.pair)
                    if price > 0:
                        self.current_price = price
                except MexcError:
                    pass
                except Exception:
                    pass  # Network errors — WS is primary, REST is just fallback
        except asyncio.CancelledError:
            pass

    # ─── Helpers ─────────────────────────────────────────────────────

    def _get_poll_interval(self) -> float:
        active = len([p for p in self.positions if p.status != PositionStatus.CLOSED])
        if active == 0:
            return POLL_INTERVAL_NO_POSITIONS
        if active <= 5:
            return POLL_INTERVAL_FEW
        return POLL_INTERVAL_MANY

    async def get_quote_balance(self) -> float:
        """Get free balance of the quote asset."""
        quote_asset = PAIR_INFO.get(self.settings.pair, ("", "USDT"))[1]
        try:
            balance = await self._client.get_balance(quote_asset)
            return balance.free
        except MexcError:
            return 0.0

    def get_status_data(self) -> dict:
        """Get data for /status command."""
        active = [p for p in self.positions if p.status != PositionStatus.CLOSED]
        last_sell_price = None
        last_sell_qty = None
        next_drop_price = None

        if active:
            last = active[-1]
            last_sell_price = last.sell_target_price
            last_sell_qty = last.buy_qty
            next_drop_price = compute_drop_price(last.buy_price, self.settings.drop_pct)

        return {
            "is_running": self.state == EngineState.RUNNING,
            "pair": self.settings.pair,
            "current_price": self.current_price,
            "next_sell_price": last_sell_price,
            "next_sell_qty": last_sell_qty,
            "next_drop_price": next_drop_price,
            "open_count": len(active),
        }
