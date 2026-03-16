from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from bot.db.database import Database
from bot.db import queries
from bot.keyboards.inline import fee_type_kb

router = Router()


class FeeStates(StatesGroup):
    waiting_maker = State()
    waiting_taker = State()


@router.message(Command("fee"))
async def cmd_fee(message: Message, db: Database) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]
    s = await queries.get_settings(db, user_id)
    if not s:
        await message.answer("❌ Настройки не найдены.")
        return

    await message.answer(
        f"Текущая комиссия в боте:\n"
        f"Мейкер - {s.maker_fee}% / Тейкер - {s.taker_fee}%\n\n"
        f"Проверьте свою комиссию на MEXC\n"
        f"После, укажите её:",
        reply_markup=fee_type_kb(),
    )


@router.callback_query(F.data == "fee_maker")
async def cb_fee_maker(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.answer("Введите комиссию мейкера (например, 0.0):")  # type: ignore
    await state.set_state(FeeStates.waiting_maker)
    await callback.answer()


@router.message(FeeStates.waiting_maker)
async def process_maker_fee(message: Message, state: FSMContext, db: Database) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]
    try:
        value = float(message.text.replace(",", ".").strip())  # type: ignore
    except (ValueError, AttributeError):
        await message.answer("❌ Введите число:")
        return

    s = await queries.get_settings(db, user_id)
    if s:
        s.maker_fee = value
        await queries.upsert_settings(db, s)
        await message.answer(f"✅ Комиссия мейкера изменена на {value}%")

    await state.clear()


@router.callback_query(F.data == "fee_taker")
async def cb_fee_taker(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.answer("Введите комиссию тейкера (например, 0.05):")  # type: ignore
    await state.set_state(FeeStates.waiting_taker)
    await callback.answer()


@router.message(FeeStates.waiting_taker)
async def process_taker_fee(message: Message, state: FSMContext, db: Database) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]
    try:
        value = float(message.text.replace(",", ".").strip())  # type: ignore
    except (ValueError, AttributeError):
        await message.answer("❌ Введите число:")
        return

    s = await queries.get_settings(db, user_id)
    if s:
        s.taker_fee = value
        await queries.upsert_settings(db, s)
        await message.answer(f"✅ Комиссия тейкера изменена на {value}%")

    await state.clear()
