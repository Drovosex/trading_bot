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


def _ws_is_open(ws) -> bool:
    """Check if WebSocket connection is open (compatible with websockets 13+ and 14+)."""
    if hasattr(ws, "closed"):
        return not ws.closed
    # websockets 14+: check close_code
    if hasattr(ws, "close_code"):
        return ws.close_code is None
    return True


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
        self._ws = None
        self._running = False
        self._task: asyncio.Task | None = None
        self._reconnect_delay = 2
        self._consecutive_failures = 0
        # Set to True when MEXC explicitly rejects our subscription
        # ("Blocked!" — IP-level public WS block). Reconnect loop stops;
        # engine should fall back to REST-only price polling.
        self._subscription_blocked: bool = False

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
            if self._subscription_blocked:
                # MEXC has blocked our IP from public WS — stop churning.
                # Engine will rely on REST price polling.
                break
            try:
                # Disable built-in ping — MEXC uses application-level pings
                async with websockets.connect(
                    WS_URL,
                    ping_interval=None,
                    ping_timeout=None,
                    close_timeout=5,
                ) as ws:
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

    async def _subscribe(self, ws) -> None:
        params = [
            f"spot@public.miniTicker.v3.api@{s}@UTC+0"
            for s in self._symbols
        ]
        msg = json.dumps({"method": "SUBSCRIPTION", "params": params})
        await ws.send(msg)
        log.info("ws_subscribed", channels=params)

        # Start application-level ping task
        asyncio.create_task(self._ping_loop(ws))

    async def _ping_loop(self, ws) -> None:
        try:
            while self._running and _ws_is_open(ws):
                await ws.send(json.dumps({"method": "PING"}))
                await asyncio.sleep(PING_INTERVAL)
        except (ConnectionClosed, asyncio.CancelledError):
            pass

    async def _listen(self, ws) -> None:
        async for raw in ws:
            if not self._running:
                break
            try:
                data = json.loads(raw)

                # Server-initiated PING — MUST respond with PONG, otherwise
                # MEXC closes the connection within ~60 seconds.
                if data.get("method") == "PING" or data.get("msg") == "PING":
                    pong = {"method": "PONG"}
                    if "id" in data:
                        pong["id"] = data["id"]
                    await ws.send(json.dumps(pong))
                    continue

                # Subscription was rejected — MEXC has blocked the IP
                # from public WS data. No point retrying.
                msg = data.get("msg") or ""
                if "Not Subscribed" in msg or "Blocked" in msg:
                    log.error(
                        "ws_subscription_blocked",
                        symbols=self._symbols,
                        reason=msg.strip(),
                    )
                    self._subscription_blocked = True
                    return  # exit _listen → exit async with → _run_loop breaks

                # Our own PONG echo from server — skip
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
        return self._ws is not None and _ws_is_open(self._ws)

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures
