from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject


class SubscriptionMiddleware(BaseMiddleware):
    """Stub middleware for future subscription checks.

    MVP: passes all users through.
    Future: check data["user"].subscription.is_active
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        return await handler(event, data)
