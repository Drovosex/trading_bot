from __future__ import annotations

from datetime import datetime, timedelta

import structlog
from aiogram import Bot

from bot.db.database import Database
from bot.db import queries
from bot.utils.formatting import format_daily_summary

log = structlog.get_logger()


class Notifier:
    """Sends scheduled notifications to users."""

    def __init__(self, bot: Bot, db: Database) -> None:
        self._bot = bot
        self._db = db

    async def send_daily_summary(self, user_id: int) -> None:
        """Send daily trading summary (called at 02:00)."""
        yesterday = datetime.utcnow().date() - timedelta(days=1)
        start = datetime.combine(yesterday, datetime.min.time())
        end = start + timedelta(days=1)

        positions = await queries.get_positions_for_period(
            self._db, user_id, start, end
        )
        profit = sum(p.profit or 0 for p in positions)

        text = format_daily_summary(
            date_str=yesterday.strftime("%d.%m.%Y"),
            closed_count=len(positions),
            profit=profit,
        )
        try:
            await self._bot.send_message(user_id, text)
        except Exception as e:
            log.warning("daily_summary_send_failed", user_id=user_id, error=str(e))

    async def send_to_user(self, user_id: int, text: str) -> None:
        try:
            await self._bot.send_message(user_id, text)
        except Exception as e:
            log.warning("send_failed", user_id=user_id, error=str(e))
