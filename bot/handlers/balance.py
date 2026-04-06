from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.db.database import Database
from bot.db import queries
from bot.db.models import PositionStatus
from bot.exchange.client import MexcClient, MexcError
from bot.security.crypto import KeyVault
from bot.trading.engine import TradingEngine
from bot.utils.formatting import format_balance, PAIR_INFO, _fmt_price, _fmt_qty

router = Router()


@router.message(Command("balance"))
async def cmd_balance(
    message: Message, db: Database, vault: KeyVault, engines: dict
) -> None:
    user_id = message.chat.id

    user = await queries.get_user(db, user_id)
    if not user or not user.api_key_enc:
        await message.answer("❌ API ключи не настроены. Используйте /set_api.")
        return

    settings = await queries.get_settings(db, user_id)
    pair = settings.pair if settings else "BTCUSDC"
    quote = PAIR_INFO.get(pair, ("", "USDT"))[1]

    api_key = vault.decrypt(user.api_key_enc)
    api_secret = vault.decrypt(user.api_secret_enc)  # type: ignore
    client = MexcClient(api_key, api_secret)

    try:
        balance = await client.get_balance(quote)
    except MexcError as e:
        await message.answer(f"❌ Ошибка получения баланса: {e.msg}")
        await client.close()
        return

    positions = await queries.get_active_positions(db, user_id)
    positions_cost = sum(p.buy_cost for p in positions)
    capital = balance.free + balance.locked + positions_cost

    text = format_balance(
        capital=capital,
        free=balance.free,
        positions_count=len(positions),
        positions_cost=positions_cost,
        quote=quote,
    )
    await message.answer(text)
    await client.close()


@router.message(Command("open_orders"))
async def cmd_open_orders(message: Message, db: Database, engines: dict) -> None:
    user_id = message.chat.id
    positions = await queries.get_active_positions(db, user_id)

    if not positions:
        await message.answer("У вас нет открытых позиций")
        return

    settings = await queries.get_settings(db, user_id)
    pair = settings.pair if settings else "BTCUSDC"

    # Get active position ID from engine
    engine = engines.get(user_id)
    active_id = engine._active_position_id if engine else None

    lines = [f"📋 Открытые позиции ({len(positions)} шт.):\n"]
    for i, p in enumerate(positions, 1):
        base, quote = PAIR_INFO.get(p.pair, (p.pair[:3], p.pair[3:]))
        active_mark = " 🔄" if p.id == active_id else ""
        lines.append(
            f"{i}. {_fmt_qty(p.pair, p.buy_qty)} {base}{active_mark}\n"
            f"   Покупка: {_fmt_price(p.pair, p.buy_price)} {quote}\n"
            f"   Цель: {_fmt_price(p.pair, p.sell_target_price)} {quote}\n"
            f"   Стоимость: {p.buy_cost:.2f} {quote}\n"
        )

    await message.answer("\n".join(lines))


@router.message(Command("average"))
async def cmd_average(message: Message, db: Database) -> None:
    user_id = message.chat.id
    positions = await queries.get_active_positions(db, user_id)

    if not positions:
        await message.answer("Нет открытых позиций для расчёта средней цены.")
        return

    settings = await queries.get_settings(db, user_id)
    pair = settings.pair if settings else "BTCUSDC"
    base, quote = PAIR_INFO.get(pair, (pair[:3], pair[3:]))

    total_cost = sum(p.buy_cost for p in positions)
    total_qty = sum(p.buy_qty for p in positions)
    avg_price = total_cost / total_qty if total_qty > 0 else 0

    await message.answer(
        f"📊 Средняя цена\n\n"
        f"• Позиций: {len(positions)} шт.\n"
        f"• Общий объём: {_fmt_qty(pair, total_qty)} {base}\n"
        f"• Общая стоимость: {total_cost:.2f} {quote}\n"
        f"• Средняя цена: {_fmt_price(pair, avg_price)} {quote}"
    )
