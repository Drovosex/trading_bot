from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot

from bot.db.database import Database
from bot.db import queries
from bot.notifications.notifier import Notifier

import structlog

log = structlog.get_logger()


def setup_scheduler(bot: Bot, db: Database) -> AsyncIOScheduler:
    """Create and configure APScheduler with daily and monthly summary jobs."""
    scheduler = AsyncIOScheduler()
    notifier = Notifier(bot, db)

    async def _get_active_user_ids() -> list[int]:
        rows = await db.db.execute_fetchall(
            "SELECT id FROM users WHERE is_active = 1"
        )
        return [row["id"] for row in rows]

    async def daily_summary_job() -> None:
        """Send daily summary to all active users at 21:00 UTC (00:00 Moscow)."""
        for user_id in await _get_active_user_ids():
            await notifier.send_daily_summary(user_id)
            log.info("daily_summary_sent", user_id=user_id)

    async def monthly_summary_job() -> None:
        """Send monthly summary to all active users on 1st at 03:00 UTC (06:00 Moscow)."""
        for user_id in await _get_active_user_ids():
            await notifier.send_monthly_summary(user_id)
            log.info("monthly_summary_sent", user_id=user_id)

    # Daily report at 00:00 Moscow time (21:00 UTC)
    scheduler.add_job(
        daily_summary_job,
        "cron",
        hour=21,
        minute=0,
        id="daily_summary",
    )

    # Monthly report on 1st at 06:00 Moscow time (03:00 UTC)
    scheduler.add_job(
        monthly_summary_job,
        "cron",
        day=1,
        hour=3,
        minute=0,
        id="monthly_summary",
    )

    return scheduler
