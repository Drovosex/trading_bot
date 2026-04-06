from __future__ import annotations

import asyncio
import hashlib
import hmac
import time
from typing import Any

import structlog
from aiohttp import ClientSession

from bot.exchange.models import (
    AccountBalance,
    OpenOrder,
    OrderResult,
    OrderSide,
    OrderStatus,
)

log = structlog.get_logger()

BASE_URL = "https://api.mexc.com"


# ─── Typed Exceptions ────────────────────────────────────────────────────────

class MexcError(Exception):
    def __init__(self, code: int, msg: str) -> None:
        self.code = code
        self.msg = msg
        super().__init__(f"MEXC error {code}: {msg}")


class InsufficientBalance(MexcError):
    pass


class RateLimited(MexcError):
    pass


class InvalidSignature(MexcError):
    pass


class InvalidApiKey(MexcError):
    pass


class MinNotional(MexcError):
    pass


_ERROR_MAP: dict[int, type[MexcError]] = {
    10072: InvalidApiKey,      # Api key info invalid
    10101: InsufficientBalance,
    30002: MinNotional,        # Below minimum trade amount
    429: RateLimited,
    602: InvalidSignature,
    700003: InvalidSignature,  # Timestamp outside recvWindow
}


def _map_error(code: int, msg: str) -> MexcError:
    cls = _ERROR_MAP.get(code, MexcError)
    return cls(code, msg)


# ─── Client ──────────────────────────────────────────────────────────────────

class MexcClient:
    """Async MEXC Spot API v3 client with typed error handling."""

    def __init__(self, api_key: str, api_secret: str) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._session: ClientSession | None = None

    async def _get_session(self) -> ClientSession:
        if self._session is None or self._session.closed:
            self._session = ClientSession(
                headers={"X-MEXC-APIKEY": self._api_key}
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    def _sign(self, params: dict[str, Any]) -> dict[str, Any]:
        params["timestamp"] = str(int(time.time() * 1000))
        params["recvWindow"] = "5000"
        query = "&".join(f"{k}={v}" for k, v in params.items())
        signature = hmac.new(
            self._api_secret.encode(), query.encode(), hashlib.sha256
        ).hexdigest()
        params["signature"] = signature
        return params

    async def _request(
        self, method: str, path: str, params: dict[str, Any] | None = None,
        signed: bool = False,
    ) -> dict[str, Any]:
        session = await self._get_session()
        params = dict(params or {})
        if signed:
            params = self._sign(params)

        url = f"{BASE_URL}{path}"

        # MEXC requires all params in query string, even for POST/DELETE
        # aiohttp sends "Content-Type: application/octet-stream" for empty POST
        # which MEXC rejects with 700013 "Invalid content Type"
        extra_kwargs: dict[str, Any] = {}
        if method in ("POST", "DELETE"):
            sep = "&" if "?" in url else "?"
            query = "&".join(f"{k}={v}" for k, v in params.items())
            url = f"{url}{sep}{query}"
            params = None
            extra_kwargs["headers"] = {"Content-Type": "application/json"}

        for attempt in range(3):
            try:
                async with session.request(method, url, params=params, **extra_kwargs) as resp:
                    data = await resp.json()

                    if resp.status == 429:
                        wait = min(2 ** attempt * 2, 30)
                        log.warning("rate_limited", wait=wait, attempt=attempt)
                        await asyncio.sleep(wait)
                        continue

                    if isinstance(data, dict) and "code" in data and data["code"] != 0:
                        raise _map_error(data["code"], data.get("msg", ""))

                    return data
            except MexcError:
                raise
            except Exception as e:
                if attempt < 2:
                    log.warning("request_retry", error=str(e), attempt=attempt)
                    await asyncio.sleep(2)
                    continue
                raise

        raise MexcError(0, "Max retries exceeded")

    # ─── Market Data (public) ─────────────────────────────────────────

    async def get_ticker_price(self, symbol: str) -> float:
        data = await self._request("GET", "/api/v3/ticker/price", {"symbol": symbol})
        return float(data["price"])

    async def get_exchange_info(self, symbol: str) -> dict[str, Any]:
        data = await self._request("GET", "/api/v3/exchangeInfo", {"symbol": symbol})
        for s in data.get("symbols", []):
            if s["symbol"] == symbol:
                return s
        raise MexcError(0, f"Symbol {symbol} not found")

    # ─── Account (signed) ────────────────────────────────────────────

    async def get_account(self) -> list[AccountBalance]:
        data = await self._request("GET", "/api/v3/account", signed=True)
        return [
            AccountBalance.from_dict(b)
            for b in data.get("balances", [])
            if float(b.get("free", 0)) > 0 or float(b.get("locked", 0)) > 0
        ]

    async def get_balance(self, asset: str) -> AccountBalance:
        balances = await self.get_account()
        for b in balances:
            if b.asset == asset:
                return b
        return AccountBalance(asset=asset, free=0.0, locked=0.0)

    # ─── Orders (signed) ─────────────────────────────────────────────

    async def place_market_buy(self, symbol: str, quote_qty: float) -> OrderResult:
        data = await self._request("POST", "/api/v3/order", {
            "symbol": symbol,
            "side": "BUY",
            "type": "MARKET",
            "quoteOrderQty": str(quote_qty),
        }, signed=True)
        result = OrderResult.from_dict(data, OrderSide.BUY)

        # MEXC returns origQty=0 for market orders with quoteOrderQty.
        # Get actual fill data from /myTrades endpoint.
        if result.qty <= 0 and result.order_id:
            for attempt in range(6):
                await asyncio.sleep(0.5 * (attempt + 1))
                try:
                    trades = await self.get_my_trades(symbol, limit=5)
                    # Find trades matching our order
                    order_trades = [
                        t for t in trades
                        if str(t.get("orderId", "")) == result.order_id
                        or str(t.get("id", "")).replace("X1", "").replace("X2", "") == result.order_id.replace("C02__", "")
                    ]
                    if order_trades:
                        total_qty = sum(float(t["qty"]) for t in order_trades)
                        total_cost = sum(float(t["quoteQty"]) for t in order_trades)
                        avg_price = total_cost / total_qty if total_qty > 0 else 0
                        result.qty = total_qty
                        result.cost = total_cost
                        result.price = avg_price
                        result.status = OrderStatus.FILLED
                        log.info("market_buy_filled_from_trades",
                                 order_id=result.order_id, qty=total_qty, cost=total_cost)
                        return result
                except MexcError:
                    pass
            log.warning("market_buy_no_fill", order_id=result.order_id, raw=data)

        return result

    async def place_limit_sell(
        self, symbol: str, qty: float, price: float
    ) -> OrderResult:
        data = await self._request("POST", "/api/v3/order", {
            "symbol": symbol,
            "side": "SELL",
            "type": "LIMIT",
            "quantity": str(qty),
            "price": str(price),
        }, signed=True)
        return OrderResult.from_dict(data, OrderSide.SELL)

    async def cancel_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        return await self._request("DELETE", "/api/v3/order", {
            "symbol": symbol,
            "orderId": order_id,
        }, signed=True)

    async def get_open_orders(self, symbol: str) -> list[OpenOrder]:
        data = await self._request("GET", "/api/v3/openOrders", {
            "symbol": symbol,
        }, signed=True)
        return [OpenOrder.from_dict(o) for o in data]

    async def get_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        return await self._request("GET", "/api/v3/order", {
            "symbol": symbol,
            "orderId": order_id,
        }, signed=True)

    async def get_my_trades(
        self, symbol: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        return await self._request("GET", "/api/v3/myTrades", {
            "symbol": symbol,
            "limit": str(limit),
        }, signed=True)
