from __future__ import annotations

from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from bot.db.database import Database
from bot.db import queries
from bot.keyboards.inline import results_period_kb
from bot.utils.formatting import format_daily_summary, PAIR_INFO, _fmt_money

router = Router()


@router.message(Command("results"))
async def cmd_results(message: Message) -> None:
    await message.answer(
        "📊 Выберите период:", reply_markup=results_period_kb()
    )


@router.callback_query(F.data == "results_today")
async def cb_results_today(callback: CallbackQuery, db: Database) -> None:
    user_id = callback.from_user.id
    now = datetime.utcnow()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)

    positions = await queries.get_positions_for_period(db, user_id, start, end)
    profit = sum(p.profit or 0 for p in positions)

    text = format_daily_summary(
        date_str=start.strftime("%d.%m.%Y"),
        closed_count=len(positions),
        profit=profit,
    )
    await callback.message.answer(text)  # type: ignore
    await callback.answer()


@router.callback_query(F.data == "results_month")
async def cb_results_month(callback: CallbackQuery, db: Database) -> None:
    user_id = callback.from_user.id
    now = datetime.utcnow()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = (start + timedelta(days=32)).replace(day=1)

    positions = await queries.get_positions_for_period(db, user_id, start, end)
    profit = sum(p.profit or 0 for p in positions)

    text = (
        f"📊 {start.strftime('%d.%m.%Y')} — {now.strftime('%d.%m.%Y')}\n\n"
        f"🔹 Закрытых позиций: {len(positions)}\n"
        f"🔹 Прибыль: {_fmt_money(profit)} USDT"
    )
    if not positions:
        text = f"📊 {start.strftime('%d.%m.%Y')} — {now.strftime('%d.%m.%Y')}\n\nНет закрытых позиций за период."

    await callback.message.answer(text)  # type: ignore
    await callback.answer()


@router.callback_query(F.data == "results_all")
async def cb_results_all(callback: CallbackQuery, db: Database) -> None:
    user_id = callback.from_user.id
    positions = await queries.get_all_closed_positions(db, user_id)
    profit = sum(p.profit or 0 for p in positions)

    text = (
        f"📊 За всё время\n\n"
        f"🔹 Закрытых позиций: {len(positions)}\n"
        f"🔹 Прибыль: {_fmt_money(profit)} USDT"
    )
    if not positions:
        text = "📊 За всё время\n\nНет закрытых позиций."

    await callback.message.answer(text)  # type: ignore
    await callback.answer()
