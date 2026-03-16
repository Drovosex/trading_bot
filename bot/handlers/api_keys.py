from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from bot.db.database import Database
from bot.db import queries
from bot.security.crypto import KeyVault

router = Router()


class ApiKeyStates(StatesGroup):
    waiting_access_key = State()
    waiting_secret_key = State()


@router.message(Command("set_api"))
async def cmd_set_api(message: Message, state: FSMContext) -> None:
    await message.answer("Пожалуйста, вставьте ваш Access Key:")
    await state.set_state(ApiKeyStates.waiting_access_key)


@router.message(ApiKeyStates.waiting_access_key)
async def process_access_key(message: Message, state: FSMContext) -> None:
    access_key = message.text.strip() if message.text else ""
    if not access_key or len(access_key) < 10:
        await message.answer("❌ Некорректный Access Key. Попробуйте ещё раз:")
        return

    await state.update_data(access_key=access_key)

    # Delete user's message with the key for security
    try:
        await message.delete()
    except Exception:
        pass

    await message.answer("Спасибо!\nТеперь вставьте ваш Secret Key:")
    await state.set_state(ApiKeyStates.waiting_secret_key)


@router.message(ApiKeyStates.waiting_secret_key)
async def process_secret_key(
    message: Message, state: FSMContext, db: Database, vault: KeyVault
) -> None:
    secret_key = message.text.strip() if message.text else ""
    if not secret_key or len(secret_key) < 10:
        await message.answer("❌ Некорректный Secret Key. Попробуйте ещё раз:")
        return

    # Delete user's message with the key for security
    try:
        await message.delete()
    except Exception:
        pass

    data = await state.get_data()
    access_key = data["access_key"]
    user_id = message.from_user.id  # type: ignore[union-attr]

    # Encrypt and save
    key_enc = vault.encrypt(access_key)
    secret_enc = vault.encrypt(secret_key)
    await queries.save_api_keys(db, user_id, key_enc, secret_enc)

    await state.clear()
    await message.answer(
        "✅ API ключ успешно привязан к боту\n\n"
        "📌 Какие следующие шаги?\n\n"
        "1️⃣ Настройте параметры стратегии: /settings\n"
        "2️⃣ Пополните счёт биржи\n"
        "3️⃣ Запустите торговлю: /start_trade\n\n"
        "❕ Все команды — /help"
    )
