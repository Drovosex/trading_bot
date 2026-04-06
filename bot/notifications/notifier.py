from __future__ import annotations

from datetime import datetime, timedelta

import structlog
from aiogram import Bot

from bot.db.database import Database
from bot.db import queries
from bot.utils.formatting import format_daily_summary, _fmt_money

log = structlog.get_logger()


class Notifier:
    """Sends scheduled notifications to users."""

    def __init__(self, bot: Bot, db: Database) -> None:
        self._bot = bot
        self._db = db

    async def send_daily_summary(self, user_id: int) -> None:
        """Send daily trading summary (called at 21:00 UTC = 00:00 Moscow)."""
        today = datetime.utcnow().date()
        start = datetime.combine(today, datetime.min.time())
        end = start + timedelta(days=1)

        positions = await queries.get_positions_for_period(
            self._db, user_id, start, end
        )
        profit = sum(p.profit or 0 for p in positions)

        text = format_daily_summary(
            date_str=today.strftime("%d.%m.%Y"),
            closed_count=len(positions),
            profit=profit,
        )
        try:
            await self._bot.send_message(user_id, text)
        except Exception as e:
            log.warning("daily_summary_send_failed", user_id=user_id, error=str(e))

    async def send_monthly_summary(self, user_id: int) -> None:
        """Send monthly trading summary (called on 1st at 03:00 UTC = 06:00 Moscow)."""
        now = datetime.utcnow()
        # Previous month
        first_of_current = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_month_end = first_of_current
        last_month_start = (first_of_current - timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        positions = await queries.get_positions_for_period(
            self._db, user_id, last_month_start, last_month_end
        )
        profit = sum(p.profit or 0 for p in positions)

        period_str = (
            f"{last_month_start.strftime('%d.%m.%Y')} — "
            f"{(last_month_end - timedelta(days=1)).strftime('%d.%m.%Y')}"
        )

        if positions:
            text = (
                f"📊 Итоги за месяц\n"
                f"{period_str}\n\n"
                f"🔹 Закрытых позиций: {len(positions)}\n"
                f"🔹 Прибыль: {_fmt_money(profit)} USDT"
            )
        else:
            text = (
                f"📊 Итоги за месяц\n"
                f"{period_str}\n\n"
                f"Нет закрытых позиций за период."
            )

        try:
            await self._bot.send_message(user_id, text)
        except Exception as e:
            log.warning("monthly_summary_send_failed", user_id=user_id, error=str(e))

    async def send_to_user(self, user_id: int, text: str) -> None:
        try:
            await self._bot.send_message(user_id, text)
        except Exception as e:
            log.warning("send_failed", user_id=user_id, error=str(e))
