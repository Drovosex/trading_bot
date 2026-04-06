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
    user_id = message.chat.id
    return engines.get(user_id)


@router.message(Command("start_trade"))
async def cmd_start_trade(
    message: Message, db: Database, vault: KeyVault, engines: dict, bot: object
) -> None:
    user_id = message.chat.id

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
    user_id = message.chat.id
    engine = engines.get(user_id)

    if not engine or engine.state != EngineState.RUNNING:
        await message.answer("🔴 Торговый алгоритм не запущен.")
        return

    await engine.stop()
    del engines[user_id]
    await message.answer("🔴 Торговый алгоритм остановлен")


@router.message(Command("price"))
async def cmd_price(
    message: Message, db: Database, vault: KeyVault, engines: dict
) -> None:
    """Show current price for the selected trading pair."""
    user_id = message.chat.id

    user = await queries.get_user(db, user_id)
    if not user or not user.api_key_enc or not user.api_secret_enc:
        await message.answer(
            "❌ API ключи не настроены.\n"
            "Используйте /set_api для привязки ключей MEXC."
        )
        return

    settings = await queries.get_settings(db, user_id)
    pair = settings.pair if settings else "BTCUSDC"
    base, quote = PAIR_INFO.get(pair, (pair[:3], pair[3:]))

    api_key = vault.decrypt(user.api_key_enc)
    api_secret = vault.decrypt(user.api_secret_enc)
    client = MexcClient(api_key, api_secret)

    try:
        price = await client.get_ticker_price(pair)
    except Exception as e:
        await message.answer(f"❌ Ошибка получения цены: {e}")
        await client.close()
        return

    from bot.utils.formatting import _fmt_price
    await message.answer(
        f"💱 {base}/{quote}\n\n"
        f"Текущая цена: **{_fmt_price(pair, price)}** {quote}"
    , parse_mode="Markdown")
    await client.close()


@router.message(Command("buy"))
async def cmd_buy(
    message: Message, db: Database, vault: KeyVault, engines: dict
) -> None:
    """Immediate market buy at current price, regardless of strategy conditions."""
    user_id = message.chat.id

    # Check API keys
    user = await queries.get_user(db, user_id)
    if not user or not user.api_key_enc or not user.api_secret_enc:
        await message.answer(
            "❌ API ключи не настроены.\n"
            "Используйте /set_api для привязки ключей MEXC."
        )
        return

    engine = engines.get(user_id)
    if not engine or engine.state != EngineState.RUNNING:
        await message.answer(
            "❌ Торговый алгоритм не запущен.\n"
            "Сначала запустите: /start_trade"
        )
        return

    await message.answer("🔄 Выполняю покупку по рыночной цене...")
    await engine.force_buy()


@router.message(Command("status"))
async def cmd_status(
    message: Message, db: Database, engines: dict, vault: KeyVault
) -> None:
    user_id = message.chat.id
    engine = engines.get(user_id)

    settings = await queries.get_settings(db, user_id)
    pair = settings.pair if settings else "BTCUSDC"
    quote = PAIR_INFO.get(pair, ("", "USDT"))[1]

    # Today's profit
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    today_positions = await queries.get_positions_for_period(db, user_id, today_start, today_end)
    today_profit = sum(p.profit or 0 for p in today_positions)

    positions = await queries.get_active_positions(db, user_id)

    if engine and engine.state == EngineState.RUNNING:
        data = engine.get_status_data()
        free = await engine.get_quote_balance()

        text = format_status(
            is_running=True,
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
    else:
        # Get balance via REST even when engine is stopped
        free = 0.0
        user = await queries.get_user(db, user_id)
        if user and user.api_key_enc and user.api_secret_enc:
            from bot.exchange.client import MexcClient
            client = MexcClient(vault.decrypt(user.api_key_enc), vault.decrypt(user.api_secret_enc))
            try:
                bal = await client.get_balance(quote)
                free = bal.free
            except Exception:
                pass
            await client.close()

        text = format_status(
            is_running=False,
            pair=pair,
            current_price=0,
            next_sell_price=0,
            next_sell_qty=0,
            next_drop_price=0,
            free_funds=free,
            open_count=len(positions),
            today_profit=today_profit,
            quote=quote,
        )

    await message.answer(text)
