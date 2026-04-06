from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from bot.db.database import Database
from bot.db import queries
from bot.keyboards.inline import fee_type_kb, cancel_input_kb

router = Router()


class FeeStates(StatesGroup):
    waiting_maker = State()
    waiting_taker = State()


async def _save_prompt_id(state: FSMContext, msg_id: int) -> None:
    await state.update_data(_prompt_msg_id=msg_id)


async def _cleanup(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    prompt_id = data.get("_prompt_msg_id")
    if prompt_id:
        try:
            await message.bot.delete_message(message.chat.id, prompt_id)
        except Exception:
            pass
    try:
        await message.delete()
    except Exception:
        pass


@router.message(Command("fee"))
async def cmd_fee(message: Message, db: Database) -> None:
    user_id = message.chat.id
    s = await queries.get_settings(db, user_id)
    if not s:
        await message.answer("❌ Настройки не найдены.")
        return

    await message.answer(
        f"🏷 Комиссия биржи\n\n"
        f"• Мейкер: {s.maker_fee}%\n"
        f"• Тейкер: {s.taker_fee}%\n\n"
        f"Выберите для изменения:",
        reply_markup=fee_type_kb(),
    )


@router.callback_query(F.data == "fee_maker")
async def cb_fee_maker(callback: CallbackQuery, state: FSMContext) -> None:
    text = "Введите комиссию мейкера (например, 0.0):"
    await state.set_state(FeeStates.waiting_maker)
    try:
        await callback.message.edit_text(text, reply_markup=cancel_input_kb())  # type: ignore
        await _save_prompt_id(state, callback.message.message_id)
    except Exception:
        sent = await callback.message.answer(text, reply_markup=cancel_input_kb())  # type: ignore
        await _save_prompt_id(state, sent.message_id)
    await callback.answer()


@router.message(FeeStates.waiting_maker)
async def process_maker_fee(message: Message, state: FSMContext, db: Database) -> None:
    user_id = message.chat.id
    try:
        value = float(message.text.replace(",", ".").strip())  # type: ignore
    except (ValueError, AttributeError):
        await message.answer("❌ Введите число:", reply_markup=cancel_input_kb())
        return

    await _cleanup(message, state)

    s = await queries.get_settings(db, user_id)
    if s:
        s.maker_fee = value
        await queries.upsert_settings(db, s)
        await message.answer(f"✅ Комиссия мейкера изменена на {value}%")

    await state.clear()


@router.callback_query(F.data == "fee_taker")
async def cb_fee_taker(callback: CallbackQuery, state: FSMContext) -> None:
    text = "Введите комиссию тейкера (например, 0.05):"
    await state.set_state(FeeStates.waiting_taker)
    try:
        await callback.message.edit_text(text, reply_markup=cancel_input_kb())  # type: ignore
        await _save_prompt_id(state, callback.message.message_id)
    except Exception:
        sent = await callback.message.answer(text, reply_markup=cancel_input_kb())  # type: ignore
        await _save_prompt_id(state, sent.message_id)
    await callback.answer()


@router.message(FeeStates.waiting_taker)
async def process_taker_fee(message: Message, state: FSMContext, db: Database) -> None:
    user_id = message.chat.id
    try:
        value = float(message.text.replace(",", ".").strip())  # type: ignore
    except (ValueError, AttributeError):
        await message.answer("❌ Введите число:", reply_markup=cancel_input_kb())
        return

    await _cleanup(message, state)

    s = await queries.get_settings(db, user_id)
    if s:
        s.taker_fee = value
        await queries.upsert_settings(db, s)
        await message.answer(f"✅ Комиссия тейкера изменена на {value}%")

    await state.clear()
