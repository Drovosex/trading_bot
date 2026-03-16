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
from bot.keyboards.inline import settings_main_kb, pair_select_kb, order_type_kb
from bot.trading.calculator import compute_order_size
from bot.utils.formatting import PAIR_INFO

router = Router()


class SettingsStates(StatesGroup):
    waiting_order_size = State()
    waiting_profit_pct = State()
    waiting_drop_pct = State()
    waiting_dynamic_pct = State()


@router.message(Command("settings"))
async def cmd_settings(message: Message, db: Database) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]
    s = await queries.get_settings(db, user_id)
    if not s:
        await message.answer("❌ Настройки не найдены. Используйте /start сначала.")
        return

    base, quote = PAIR_INFO.get(s.pair, (s.pair[:3], s.pair[3:]))
    order_desc = (
        f"{s.order_param}% от капитала (динамический)"
        if s.order_type == OrderType.DYNAMIC
        else f"{s.order_param} {quote} (фиксированный)"
    )

    text = (
        f"⚙️ Выберите параметр для изменения\n\n"
        f"• Пара: {base}/{quote}\n"
        f"• Ордер: {order_desc}\n"
        f"• Прибыль: {s.profit_pct}%\n"
        f"• Снижение: {s.drop_pct}%"
    )
    await message.answer(text, reply_markup=settings_main_kb())


# ─── Pair selection ───────────────────────────────────────────────────────────

@router.callback_query(F.data == "set_pair")
async def cb_set_pair(callback: CallbackQuery) -> None:
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

    old_base = PAIR_INFO.get(old_pair, (old_pair,))[0]
    new_base, new_quote = PAIR_INFO.get(new_pair, (new_pair[:3], new_pair[3:]))

    await callback.message.answer(  # type: ignore
        f"✅ Торговая пара успешно изменена с {old_pair} на {new_pair}.\n\n"
        f"• Ранее открытые позиции более не контролируются.\n\n"
        f"• Торговые параметры установлены по умолчанию."
    )
    await callback.answer()


# ─── Order type ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "set_order_type")
async def cb_set_order_type(callback: CallbackQuery) -> None:
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
    await callback.message.answer(  # type: ignore
        f"✅ Стратегия успешно изменена на {label} ордер.\n\n"
        f"• Торговые параметры установлены по умолчанию."
    )
    await callback.answer()

    # Ask for size
    if new_type == OrderType.DYNAMIC:
        await callback.message.answer(  # type: ignore
            "Введите новый процент динамического ордера\n(от 0.1 до 10):"
        )
        await state.set_state(SettingsStates.waiting_dynamic_pct)
    else:
        await callback.message.answer(  # type: ignore
            "Введите новую сумму ордера\n(от 2 до 1000):"
        )
        await state.set_state(SettingsStates.waiting_order_size)


# ─── Order size ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "set_order_size")
async def cb_set_order_size(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    user_id = callback.from_user.id
    s = await queries.get_settings(db, user_id)

    if s and s.order_type == OrderType.DYNAMIC:
        await callback.message.answer(  # type: ignore
            "Введите новый процент динамического ордера\n(от 0.1 до 10):"
        )
        await state.set_state(SettingsStates.waiting_dynamic_pct)
    else:
        await callback.message.answer(  # type: ignore
            "Введите новую сумму ордера\n(от 2 до 1000):"
        )
        await state.set_state(SettingsStates.waiting_order_size)
    await callback.answer()


@router.message(SettingsStates.waiting_order_size)
async def process_order_size(message: Message, state: FSMContext, db: Database) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]
    try:
        value = float(message.text.replace(",", ".").strip())  # type: ignore
    except (ValueError, AttributeError):
        await message.answer("❌ Введите число от 2 до 1000:")
        return

    if value < 2 or value > 1000:
        await message.answer("❌ Значение должно быть от 2 до 1000:")
        return

    s = await queries.get_settings(db, user_id)
    if s:
        old = s.order_param
        s.order_param = value
        await queries.upsert_settings(db, s)
        await message.answer(f"✅ Сумма ордера изменена\nс {old} на {value}")

    await state.clear()


@router.message(SettingsStates.waiting_dynamic_pct)
async def process_dynamic_pct(message: Message, state: FSMContext, db: Database) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]
    try:
        value = float(message.text.replace(",", ".").strip())  # type: ignore
    except (ValueError, AttributeError):
        await message.answer("❌ Введите число от 0.1 до 10:")
        return

    if value < 0.1 or value > 10:
        await message.answer("❌ Значение должно быть от 0.1 до 10:")
        return

    s = await queries.get_settings(db, user_id)
    if s:
        s.order_param = value
        await queries.upsert_settings(db, s)
        await message.answer(f"✅ Процент динамического ордера изменён на {value}%")

    await state.clear()


# ─── Profit / Drop percent ────────────────────────────────────────────────────

@router.callback_query(F.data == "set_profit_pct")
async def cb_set_profit(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.answer(  # type: ignore
        "Введите новый процент прибыли\n(от 0.1 до 50):"
    )
    await state.set_state(SettingsStates.waiting_profit_pct)
    await callback.answer()


@router.message(SettingsStates.waiting_profit_pct)
async def process_profit_pct(message: Message, state: FSMContext, db: Database) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]
    try:
        value = float(message.text.replace(",", ".").strip())  # type: ignore
    except (ValueError, AttributeError):
        await message.answer("❌ Введите число от 0.1 до 50:")
        return

    if value < 0.1 or value > 50:
        await message.answer("❌ Значение должно быть от 0.1 до 50:")
        return

    s = await queries.get_settings(db, user_id)
    if s:
        s.profit_pct = value
        await queries.upsert_settings(db, s)
        await message.answer(f"✅ Процент прибыли изменён на {value}%")

    await state.clear()


@router.callback_query(F.data == "set_drop_pct")
async def cb_set_drop(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.answer(  # type: ignore
        "Введите новый процент снижения цены\n(от 0.2 до 50):"
    )
    await state.set_state(SettingsStates.waiting_drop_pct)
    await callback.answer()


@router.message(SettingsStates.waiting_drop_pct)
async def process_drop_pct(message: Message, state: FSMContext, db: Database) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]
    try:
        value = float(message.text.replace(",", ".").strip())  # type: ignore
    except (ValueError, AttributeError):
        await message.answer("❌ Введите число от 0.2 до 50:")
        return

    if value < 0.2 or value > 50:
        await message.answer("❌ Значение должно быть от 0.2 до 50:")
        return

    s = await queries.get_settings(db, user_id)
    if s:
        s.drop_pct = value
        await queries.upsert_settings(db, s)
        await message.answer(f"✅ Процент снижения цены изменён на {value}%")

    await state.clear()


# ─── Close settings ───────────────────────────────────────────────────────────

@router.callback_query(F.data == "set_close")
async def cb_close_settings(callback: CallbackQuery) -> None:
    await callback.message.answer("Меню настроек закрыто")  # type: ignore
    await callback.answer()
