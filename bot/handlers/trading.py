from __future__ import annotations

from datetime import datetime, timedelta

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.db.database import Database
from bot.db import queries
from bot.db.models import PositionStatus
from bot.exchange.client import MexcClient
from bot.security.crypto import KeyVault
from bot.trading.engine import TradingEngine
from bot.trading.state import EngineState
from bot.utils.formatting import format_status, PAIR_INFO

router = Router()


async def _get_engine(message: Message, engines: dict) -> TradingEngine | None:
    user_id = message.from_user.id  # type: ignore[union-attr]
    return engines.get(user_id)


@router.message(Command("start_trade"))
async def cmd_start_trade(
    message: Message, db: Database, vault: KeyVault, engines: dict, bot: object
) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]

    # Check API keys
    user = await queries.get_user(db, user_id)
    if not user or not user.api_key_enc or not user.api_secret_enc:
        await message.answer(
            "❌ API ключи не настроены.\n"
            "Используйте /set_api для привязки ключей MEXC."
        )
        return

    # Check if already running
    if user_id in engines and engines[user_id].state == EngineState.RUNNING:
        await message.answer("🟢 Торговый алгоритм уже запущен.")
        return

    settings = await queries.get_settings(db, user_id)
    if not settings:
        await message.answer("❌ Настройки не найдены. Используйте /settings.")
        return

    # Decrypt keys
    api_key = vault.decrypt(user.api_key_enc)
    api_secret = vault.decrypt(user.api_secret_enc)

    client = MexcClient(api_key, api_secret)

    async def send_message(text: str) -> None:
        from aiogram import Bot
        b: Bot = message.bot  # type: ignore[assignment]
        await b.send_message(user_id, text)

    engine = TradingEngine(
        user_id=user_id,
        settings=settings,
        client=client,
        db=db,
        send_message=send_message,
    )
    engines[user_id] = engine

    await message.answer("🔄 Запуск торгового алгоритма...")
    await engine.start()


@router.message(Command("stop_trade"))
async def cmd_stop_trade(message: Message, engines: dict) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]
    engine = engines.get(user_id)

    if not engine or engine.state != EngineState.RUNNING:
        await message.answer("🔴 Торговый алгоритм не запущен.")
        return

    await engine.stop()
    del engines[user_id]
    await message.answer("🔴 Торговый алгоритм остановлен")


@router.message(Command("status"))
async def cmd_status(message: Message, db: Database, engines: dict) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]
    engine = engines.get(user_id)

    settings = await queries.get_settings(db, user_id)
    pair = settings.pair if settings else "BTCUSDC"
    quote = PAIR_INFO.get(pair, ("", "USDT"))[1]

    if not engine or engine.state != EngineState.RUNNING:
        await message.answer(
            f"🔴 Торговый алгоритм не запущен\n\n"
            f"• Свободные средства: —\n/balance"
        )
        return

    data = engine.get_status_data()

    # Today's profit
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    today_positions = await queries.get_positions_for_period(db, user_id, today_start, today_end)
    today_profit = sum(p.profit or 0 for p in today_positions)

    # Free balance
    free = await engine.get_quote_balance()

    text = format_status(
        is_running=data["is_running"],
        pair=data["pair"],
        current_price=data["current_price"],
        next_sell_price=data["next_sell_price"],
        next_sell_qty=data["next_sell_qty"],
        next_drop_price=data["next_drop_price"],
        free_funds=free,
        open_count=data["open_count"],
        today_profit=today_profit,
        quote=quote,
    )
    await message.answer(text)
