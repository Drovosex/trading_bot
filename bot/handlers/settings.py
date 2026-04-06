from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from bot.config import settings as app_settings
from bot.db.database import Database
from bot.db import queries
from bot.db.models import OrderType, TradingSettings
from bot.keyboards.inline import settings_main_kb, pair_select_kb, order_type_kb, cancel_input_kb
from bot.trading.calculator import compute_order_size
from bot.utils.formatting import PAIR_INFO

router = Router()


class SettingsStates(StatesGroup):
    waiting_order_size = State()
    waiting_profit_pct = State()
    waiting_drop_pct = State()
    waiting_dynamic_pct = State()


# ─── Helpers ─────────────────────────────────────────────────────────────────

async def _save_prompt_id(state: FSMContext, msg_id: int) -> None:
    """Remember the prompt message id so we can delete it later."""
    await state.update_data(_prompt_msg_id=msg_id)


async def _cleanup(message: Message, state: FSMContext) -> None:
    """Delete the prompt message (with cancel button) and user's input message."""
    data = await state.get_data()
    prompt_id = data.get("_prompt_msg_id")
    # Delete prompt with cancel button
    if prompt_id:
        try:
            await message.bot.delete_message(message.chat.id, prompt_id)
        except Exception:
            pass
    # Delete user's input message
    try:
        await message.delete()
    except Exception:
        pass


# ─── Cancel input (shared for all FSM states in this router) ─────────────────

@router.callback_query(F.data == "cancel_input")
async def cb_cancel_input(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("Отменено")
    try:
        await callback.message.delete()  # type: ignore
    except Exception:
        pass


# ─── Show settings ───────────────────────────────────────────────────────────

@router.message(Command("settings"))
async def cmd_settings(message: Message, db: Database) -> None:
    user_id = message.chat.id
    s = await queries.get_settings(db, user_id)
    if not s:
        await message.answer("❌ Настройки не найдены. Используйте /start сначала.")
        return

    text = _settings_text(s)
    await message.answer(text, reply_markup=settings_main_kb())


def _settings_text(s: TradingSettings) -> str:
    base, quote = PAIR_INFO.get(s.pair, (s.pair[:3], s.pair[3:]))
    order_desc = (
        f"{s.order_param}% от капитала (динамический)"
        if s.order_type == OrderType.DYNAMIC
        else f"{s.order_param} {quote} (фиксированный)"
    )
    return (
        f"⚙️ Выберите параметр для изменения\n\n"
        f"• Пара: {base}/{quote}\n"
        f"• Ордер: {order_desc}\n"
        f"• Прибыль: {s.profit_pct}%\n"
        f"• Снижение: {s.drop_pct}%"
    )


# ─── Pair selection ───────────────────────────────────────────────────────────

@router.callback_query(F.data == "set_pair")
async def cb_set_pair(callback: CallbackQuery) -> None:
    try:
        await callback.message.edit_text(  # type: ignore
            "Выберите торговую пару:", reply_markup=pair_select_kb()
        )
    except Exception:
        await callback.message.answer("Выберите торговую пару:", reply_markup=pair_select_kb())  # type: ignore
    await callback.answer()


@router.callback_query(F.data.startswith("pair_"))
async def cb_pair_selected(callback: CallbackQuery, db: Database) -> None:
    user_id = callback.from_user.id
    new_pair = callback.data.replace("pair_", "")  # type: ignore

    s = await queries.get_settings(db, user_id)
    if not s:
        await callback.answer("Ошибка")
        return

    old_pair = s.pair
    defaults = app_settings.default_params(new_pair)
    s.pair = new_pair
    s.profit_pct = defaults["profit_pct"]
    s.drop_pct = defaults["drop_pct"]
    await queries.upsert_settings(db, s)

    new_base, new_quote = PAIR_INFO.get(new_pair, (new_pair[:3], new_pair[3:]))

    try:
        await callback.message.edit_text(  # type: ignore
            f"✅ Пара изменена на {new_base}/{new_quote}\n"
            f"Параметры установлены по умолчанию.",
            reply_markup=settings_main_kb(),
        )
    except Exception:
        pass
    await callback.answer()


# ─── Order type ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "set_order_type")
async def cb_set_order_type(callback: CallbackQuery) -> None:
    try:
        await callback.message.edit_text(  # type: ignore
            "Выберите тип ордера:", reply_markup=order_type_kb()
        )
    except Exception:
        await callback.message.answer("Выберите тип ордера:", reply_markup=order_type_kb())  # type: ignore
    await callback.answer()


@router.callback_query(F.data.startswith("otype_"))
async def cb_order_type_selected(
    callback: CallbackQuery, db: Database, state: FSMContext
) -> None:
    user_id = callback.from_user.id
    otype = callback.data.replace("otype_", "")  # type: ignore

    s = await queries.get_settings(db, user_id)
    if not s:
        await callback.answer("Ошибка")
        return

    new_type = OrderType.DYNAMIC if otype == "dynamic" else OrderType.FIXED
    s.order_type = new_type
    await queries.upsert_settings(db, s)

    label = "динамический" if new_type == OrderType.DYNAMIC else "фиксированный"
    await callback.answer()

    if new_type == OrderType.DYNAMIC:
        text = f"✅ Стратегия: {label} ордер\n\nВведите процент динамического ордера\n(от 0.1 до 10):"
        await state.set_state(SettingsStates.waiting_dynamic_pct)
    else:
        text = f"✅ Стратегия: {label} ордер\n\nВведите сумму ордера\n(от 2 до 1000):"
        await state.set_state(SettingsStates.waiting_order_size)

    try:
        await callback.message.edit_text(text, reply_markup=cancel_input_kb())  # type: ignore
        await _save_prompt_id(state, callback.message.message_id)
    except Exception:
        sent = await callback.message.answer(text, reply_markup=cancel_input_kb())  # type: ignore
        await _save_prompt_id(state, sent.message_id)


# ─── Order size ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "set_order_size")
async def cb_set_order_size(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    user_id = callback.from_user.id
    s = await queries.get_settings(db, user_id)

    if s and s.order_type == OrderType.DYNAMIC:
        text = "Введите процент динамического ордера\n(от 0.1 до 10):"
        await state.set_state(SettingsStates.waiting_dynamic_pct)
    else:
        text = "Введите сумму ордера\n(от 2 до 1000):"
        await state.set_state(SettingsStates.waiting_order_size)

    try:
        await callback.message.edit_text(text, reply_markup=cancel_input_kb())  # type: ignore
        await _save_prompt_id(state, callback.message.message_id)
    except Exception:
        sent = await callback.message.answer(text, reply_markup=cancel_input_kb())  # type: ignore
        await _save_prompt_id(state, sent.message_id)
    await callback.answer()


@router.message(SettingsStates.waiting_order_size)
async def process_order_size(message: Message, state: FSMContext, db: Database, engines: dict) -> None:
    user_id = message.chat.id
    try:
        value = float(message.text.replace(",", ".").strip())  # type: ignore
    except (ValueError, AttributeError):
        await message.answer("❌ Введите число от 2 до 1000:", reply_markup=cancel_input_kb())
        return

    if value < 2 or value > 1000:
        await message.answer("❌ Значение должно быть от 2 до 1000:", reply_markup=cancel_input_kb())
        return

    await _cleanup(message, state)

    s = await queries.get_settings(db, user_id)
    if s:
        old = s.order_param
        s.order_param = value
        await queries.upsert_settings(db, s)
        await message.answer(f"✅ Сумма ордера изменена\nс {old} на {value}")

        engine = engines.get(user_id) if engines else None
        if engine:
            engine.settings.order_param = value

    await state.clear()


@router.message(SettingsStates.waiting_dynamic_pct)
async def process_dynamic_pct(message: Message, state: FSMContext, db: Database, engines: dict) -> None:
    user_id = message.chat.id
    try:
        value = float(message.text.replace(",", ".").strip())  # type: ignore
    except (ValueError, AttributeError):
        await message.answer("❌ Введите число от 0.1 до 10:", reply_markup=cancel_input_kb())
        return

    if value < 0.1 or value > 10:
        await message.answer("❌ Значение должно быть от 0.1 до 10:", reply_markup=cancel_input_kb())
        return

    await _cleanup(message, state)

    s = await queries.get_settings(db, user_id)
    if s:
        s.order_param = value
        await queries.upsert_settings(db, s)
        await message.answer(f"✅ Процент динамического ордера изменён на {value}%")

        engine = engines.get(user_id) if engines else None
        if engine:
            engine.settings.order_param = value

    await state.clear()


# ─── Profit / Drop percent ────────────────────────────────────────────────────

@router.callback_query(F.data == "set_profit_pct")
async def cb_set_profit(callback: CallbackQuery, state: FSMContext) -> None:
    text = "Введите новый процент прибыли\n(от 0.1 до 50):"
    await state.set_state(SettingsStates.waiting_profit_pct)
    try:
        await callback.message.edit_text(text, reply_markup=cancel_input_kb())  # type: ignore
        await _save_prompt_id(state, callback.message.message_id)
    except Exception:
        sent = await callback.message.answer(text, reply_markup=cancel_input_kb())  # type: ignore
        await _save_prompt_id(state, sent.message_id)
    await callback.answer()


@router.message(SettingsStates.waiting_profit_pct)
async def process_profit_pct(message: Message, state: FSMContext, db: Database, engines: dict) -> None:
    user_id = message.chat.id
    try:
        value = float(message.text.replace(",", ".").strip())  # type: ignore
    except (ValueError, AttributeError):
        await message.answer("❌ Введите число от 0.1 до 50:", reply_markup=cancel_input_kb())
        return

    if value < 0.1 or value > 50:
        await message.answer("❌ Значение должно быть от 0.1 до 50:", reply_markup=cancel_input_kb())
        return

    await _cleanup(message, state)

    s = await queries.get_settings(db, user_id)
    if s:
        s.profit_pct = value
        await queries.upsert_settings(db, s)
        await message.answer(f"✅ Процент прибыли изменён на {value}%")

        engine = engines.get(user_id) if engines else None
        if engine:
            engine.settings.profit_pct = value

    await state.clear()


@router.callback_query(F.data == "set_drop_pct")
async def cb_set_drop(callback: CallbackQuery, state: FSMContext) -> None:
    text = "Введите новый процент снижения цены\n(от 0.2 до 50):"
    await state.set_state(SettingsStates.waiting_drop_pct)
    try:
        await callback.message.edit_text(text, reply_markup=cancel_input_kb())  # type: ignore
        await _save_prompt_id(state, callback.message.message_id)
    except Exception:
        sent = await callback.message.answer(text, reply_markup=cancel_input_kb())  # type: ignore
        await _save_prompt_id(state, sent.message_id)
    await callback.answer()


@router.message(SettingsStates.waiting_drop_pct)
async def process_drop_pct(message: Message, state: FSMContext, db: Database, engines: dict) -> None:
    user_id = message.chat.id
    try:
        value = float(message.text.replace(",", ".").strip())  # type: ignore
    except (ValueError, AttributeError):
        await message.answer("❌ Введите число от 0.2 до 50:", reply_markup=cancel_input_kb())
        return

    if value < 0.2 or value > 50:
        await message.answer("❌ Значение должно быть от 0.2 до 50:", reply_markup=cancel_input_kb())
        return

    await _cleanup(message, state)

    s = await queries.get_settings(db, user_id)
    if s:
        s.drop_pct = value
        await queries.upsert_settings(db, s)
        await message.answer(f"✅ Процент снижения цены изменён на {value}%")

        engine = engines.get(user_id) if engines else None
        if engine:
            engine.settings.drop_pct = value

    await state.clear()
