from __future__ import annotations

import asyncio
import json
from typing import Callable, Awaitable

import structlog
import websockets
from websockets.exceptions import ConnectionClosed

log = structlog.get_logger()

WS_URL = "wss://wbs.mexc.com/ws"
PING_INTERVAL = 20  # seconds
MAX_RECONNECT_DELAY = 60


class MexcWebSocket:
    """Async WebSocket client for MEXC price monitoring.

    Subscribes to miniTicker for given symbols, calls on_price_update
    callback with (symbol, price) on each tick.
    """

    def __init__(
        self,
        symbols: list[str],
        on_price_update: Callable[[str, float], Awaitable[None]],
    ) -> None:
        self._symbols = symbols
        self._on_price_update = on_price_update
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._running = False
        self._task: asyncio.Task | None = None
        self._reconnect_delay = 2
        self._consecutive_failures = 0

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._running = False
        if self._ws:
            await self._ws.close()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run_loop(self) -> None:
        while self._running:
            try:
                async with websockets.connect(WS_URL) as ws:
                    self._ws = ws
                    self._reconnect_delay = 2
                    self._consecutive_failures = 0
                    log.info("ws_connected", symbols=self._symbols)

                    await self._subscribe(ws)
                    await self._listen(ws)

            except (ConnectionClosed, ConnectionError, OSError) as e:
                if not self._running:
                    break
                self._consecutive_failures += 1
                log.warning(
                    "ws_disconnected",
                    error=str(e),
                    reconnect_in=self._reconnect_delay,
                    failures=self._consecutive_failures,
                )
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(
                    self._reconnect_delay * 2, MAX_RECONNECT_DELAY
                )
            except asyncio.CancelledError:
                break
            except Exception as e:
                if not self._running:
                    break
                log.error("ws_unexpected_error", error=str(e))
                await asyncio.sleep(5)

    async def _subscribe(self, ws: websockets.WebSocketClientProtocol) -> None:
        params = [
            f"spot@public.miniTicker.v3.api@{s}@UTC+0"
            for s in self._symbols
        ]
        msg = json.dumps({"method": "SUBSCRIPTION", "params": params})
        await ws.send(msg)
        log.info("ws_subscribed", channels=params)

        # Start ping task
        asyncio.create_task(self._ping_loop(ws))

    async def _ping_loop(self, ws: websockets.WebSocketClientProtocol) -> None:
        try:
            while self._running and not ws.closed:
                await ws.send(json.dumps({"method": "PING"}))
                await asyncio.sleep(PING_INTERVAL)
        except (ConnectionClosed, asyncio.CancelledError):
            pass

    async def _listen(self, ws: websockets.WebSocketClientProtocol) -> None:
        async for raw in ws:
            if not self._running:
                break
            try:
                data = json.loads(raw)

                # PONG response — skip
                if data.get("msg") == "PONG" or data.get("code") == 0:
                    continue

                # miniTicker update
                if "d" in data and "s" in data:
                    symbol = data["s"]
                    ticker = data["d"]
                    # miniTicker has 'c' for last price
                    price_str = ticker.get("c") or ticker.get("p")
                    if price_str:
                        price = float(price_str)
                        await self._on_price_update(symbol, price)

            except (json.JSONDecodeError, KeyError, ValueError) as e:
                log.debug("ws_parse_error", error=str(e), raw=str(raw)[:200])

    @property
    def is_connected(self) -> bool:
        return self._ws is not None and not self._ws.closed

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures
