from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot

from bot.db.database import Database
from bot.db import queries
from bot.notifications.notifier import Notifier

import structlog

log = structlog.get_logger()


def setup_scheduler(bot: Bot, db: Database) -> AsyncIOScheduler:
    """Create and configure APScheduler with daily summary job."""
    scheduler = AsyncIOScheduler()
    notifier = Notifier(bot, db)

    async def daily_summary_job() -> None:
        """Send daily summary to all active users at 02:00 UTC."""
        rows = await db.db.execute_fetchall(
            "SELECT id FROM users WHERE is_active = 1"
        )
        for row in rows:
            user_id = row["id"]
            await notifier.send_daily_summary(user_id)
            log.info("daily_summary_sent", user_id=user_id)

    scheduler.add_job(
        daily_summary_job,
        "cron",
        hour=2,
        minute=0,
        id="daily_summary",
    )

    return scheduler
