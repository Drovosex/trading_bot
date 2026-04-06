from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from bot.db.database import Database
from bot.db import queries
from bot.security.crypto import KeyVault

router = Router()


class ApiKeyStates(StatesGroup):
    confirm = State()
    waiting_access_key = State()
    waiting_secret_key = State()


def _confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, изменить", callback_data="api_confirm_yes"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="api_cancel"),
        ],
    ])


def _cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="api_cancel")],
    ])


@router.message(Command("set_api"))
async def cmd_set_api(message: Message, state: FSMContext, db: Database) -> None:
    user_id = message.chat.id
    user = await queries.get_user(db, user_id)

    if user and user.api_key_enc:
        await message.answer(
            "🔑 API ключи уже привязаны.\n\n"
            "Хотите изменить параметры подключения к API?",
            reply_markup=_confirm_kb(),
        )
        await state.set_state(ApiKeyStates.confirm)
    else:
        await message.answer(
            "🔑 Привязка API ключей MEXC\n\n"
            "Вставьте ваш Access Key:",
            reply_markup=_cancel_kb(),
        )
        await state.set_state(ApiKeyStates.waiting_access_key)


@router.callback_query(F.data == "api_confirm_yes")
async def cb_api_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    try:
        await callback.message.edit_text(
            "🔑 Привязка API ключей MEXC\n\n"
            "Вставьте ваш Access Key:",
            reply_markup=_cancel_kb(),
        )
    except Exception:
        await callback.message.answer(
            "Вставьте ваш Access Key:",
            reply_markup=_cancel_kb(),
        )
    await state.set_state(ApiKeyStates.waiting_access_key)


@router.callback_query(F.data == "api_cancel")
async def cb_api_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("Отменено")
    try:
        await callback.message.edit_text("↩️ Привязка API отменена.")
    except Exception:
        pass


@router.message(ApiKeyStates.waiting_access_key)
async def process_access_key(message: Message, state: FSMContext) -> None:
    access_key = message.text.strip() if message.text else ""
    if not access_key or len(access_key) < 10:
        await message.answer(
            "❌ Некорректный Access Key. Попробуйте ещё раз:",
            reply_markup=_cancel_kb(),
        )
        return

    await state.update_data(access_key=access_key)

    # Delete user's message with the key for security
    try:
        await message.delete()
    except Exception:
        pass

    await message.answer(
        "Спасибо!\nТеперь вставьте ваш Secret Key:",
        reply_markup=_cancel_kb(),
    )
    await state.set_state(ApiKeyStates.waiting_secret_key)


@router.message(ApiKeyStates.waiting_secret_key)
async def process_secret_key(
    message: Message, state: FSMContext, db: Database, vault: KeyVault
) -> None:
    secret_key = message.text.strip() if message.text else ""
    if not secret_key or len(secret_key) < 10:
        await message.answer(
            "❌ Некорректный Secret Key. Попробуйте ещё раз:",
            reply_markup=_cancel_kb(),
        )
        return

    # Delete user's message with the key for security
    try:
        await message.delete()
    except Exception:
        pass

    data = await state.get_data()
    access_key = data["access_key"]
    user_id = message.chat.id

    # Encrypt and save
    key_enc = vault.encrypt(access_key)
    secret_enc = vault.encrypt(secret_key)
    await queries.save_api_keys(db, user_id, key_enc, secret_enc)

    await state.clear()
    await message.answer(
        "✅ API ключи успешно привязаны\n\n"
        "📌 Что дальше?\n"
        "1️⃣ Настройте параметры: ⚙️ Настройки\n"
        "2️⃣ Пополните счёт биржи\n"
        "3️⃣ Запустите торговлю: ▶️ Старт"
    )
