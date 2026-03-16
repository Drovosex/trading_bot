from __future__ import annotations

import asyncio
import logging

import structlog
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import settings
from bot.db.database import Database
from bot.security.crypto import KeyVault


async def main() -> None:
    # Logging
    logging.basicConfig(level=getattr(logging, settings.log_level))
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level)
        ),
    )
    log = structlog.get_logger()

    # Database
    db = Database(settings.db_path)
    await db.connect()
    log.info("database_connected", path=settings.db_path)

    # Security
    vault = KeyVault(settings.encryption_key)

    # Bot
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    # Store shared objects in dispatcher workflow data
    dp["db"] = db
    dp["vault"] = vault
    dp["bot"] = bot
    dp["engines"] = {}  # dict[int, TradingEngine] — active engines per user_id
    dp["log"] = log

    # Middlewares
    from bot.middlewares.auth import AdminMiddleware
    dp.message.middleware(AdminMiddleware())
    dp.callback_query.middleware(AdminMiddleware())

    # Register handlers
    from bot.handlers import register_all_handlers
    register_all_handlers(dp)

    # Scheduler
    from bot.utils.scheduler import setup_scheduler
    scheduler = setup_scheduler(bot, db)
    scheduler.start()
    log.info("scheduler_started")

    # Startup/shutdown
    async def on_shutdown(*args: object) -> None:
        log.info("shutting_down")
        scheduler.shutdown(wait=False)
        # Stop all active trading engines
        engines: dict = dp["engines"]
        for uid, engine in list(engines.items()):
            await engine.stop()
        await db.close()

    dp.shutdown.register(on_shutdown)

    log.info("bot_starting")
    await dp.start_polling(bot)
