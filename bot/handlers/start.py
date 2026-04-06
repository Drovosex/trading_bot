from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from bot.db.database import Database
from bot.db import queries
from bot.keyboards.reply import main_menu_kb
from bot.services.demo import DemoEngine

router = Router()

# Store demo engines per user
_demo_engines: dict[int, DemoEngine] = {}


class DemoSetup(StatesGroup):
    waiting_dynamic_pct = State()
    waiting_order_size = State()
    waiting_drop_pct = State()


@router.message(CommandStart())
async def cmd_start(message: Message, db: Database) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]
    username = message.from_user.username  # type: ignore[union-attr]

    existing = await queries.get_user(db, user_id)
    if existing:
        await message.answer(
            "Вы уже зарегистрированы в системе.",
            reply_markup=main_menu_kb(),
        )
        return

    await queries.upsert_user(db, user_id, username)

    # Create default trading settings
    from bot.db.models import TradingSettings
    await queries.upsert_settings(db, TradingSettings(user_id=user_id))

    await message.answer(
        "👋 Добро пожаловать!\n\n"
        "Данный бот использует стратегию скальпинга, "
        "фиксируя незначительные изменения цен криптовалют. "
        "Он автоматически покупает выбранный актив — BTC, KAS, XRP или SOL — "
        "и продает только при его росте.\n\n"
        "📌 Что дальше?\n"
        "1️⃣ Привяжите API-ключи MEXC: /set_api\n"
        "2️⃣ Настройте параметры: ⚙️ Настройки\n"
        "3️⃣ Запустите торговлю: ▶️ Старт\n\n"
        "Используйте кнопки внизу экрана для управления.",
        reply_markup=main_menu_kb(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "ℹ️ Управление ботом\n\n"
        "Используйте кнопки внизу экрана или команды:\n\n"
        "▶️ Старт — запустить торговлю — /start_trade\n"
        "⏹ Стоп — остановить торговлю — /stop_trade\n"
        "🛒 Купить — немедленная покупка — /buy\n"
        "📊 Статус — статус алгоритма — /status\n"
        "💰 Баланс — баланс на бирже — /balance\n"
        "💱 Цена — текущая цена пары — /price\n"
        "📋 Позиции — открытые позиции — /open_orders\n"
        "📈 Результаты — результаты торговли — /results\n"
        "📐 Средняя — средняя цена покупки — /average\n"
        "⚙️ Настройки — параметры торговли — /settings\n"
        "🏷 Комиссия — настройка комиссии — /fee\n"
        "🔑 API-ключи — привязать ключи MEXC — /set_api\n"
        "💼 Демо-счёт — торговля на демо — /demo\n"
        "ℹ️ Помощь — эта справка — /help",
        reply_markup=main_menu_kb(),
    )


@router.message(Command("demo"))
async def cmd_demo(message: Message, db: Database, state: FSMContext) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]

    # If demo already running — show stats or delete
    if user_id in _demo_engines:
        engine = _demo_engines[user_id]
        await engine.delete()
        del _demo_engines[user_id]
        await message.answer("💼 [Демо-счёт]\n\n🗑 Демо-счёт удалён")
        return

    # Start demo setup — ask for dynamic order %
    await message.answer(
        "💼 [Демо-счёт]\n\n"
        "Введите новый процент динамического ордера\n(от 0.1 до 10):"
    )
    await state.set_state(DemoSetup.waiting_dynamic_pct)


@router.message(DemoSetup.waiting_dynamic_pct)
async def demo_dynamic_pct(message: Message, state: FSMContext) -> None:
    try:
        value = float(message.text.replace(",", ".").strip())  # type: ignore
    except (ValueError, AttributeError):
        await message.answer("❌ Введите число от 0.1 до 10:")
        return
    if value < 0.1 or value > 10:
        await message.answer("❌ Значение должно быть от 0.1 до 10:")
        return
    await state.update_data(dynamic_pct=value)
    await message.answer(
        "💼 [Демо-счёт]\n\n"
        "Введите новую сумму ордера\n(от 2 до 1000):"
    )
    await state.set_state(DemoSetup.waiting_order_size)


@router.message(DemoSetup.waiting_order_size)
async def demo_order_size(message: Message, state: FSMContext) -> None:
    try:
        value = float(message.text.replace(",", ".").strip())  # type: ignore
    except (ValueError, AttributeError):
        await message.answer("❌ Введите число от 2 до 1000:")
        return
    if value < 2 or value > 1000:
        await message.answer("❌ Значение должно быть от 2 до 1000:")
        return
    await state.update_data(order_size=value)
    await message.answer(
        "💼 [Демо-счёт]\n\n"
        "Введите новый процент снижения цены\n(от 0.2 до 50):"
    )
    await state.set_state(DemoSetup.waiting_drop_pct)


@router.message(DemoSetup.waiting_drop_pct)
async def demo_drop_pct(message: Message, state: FSMContext, db: Database) -> None:
    try:
        value = float(message.text.replace(",", ".").strip())  # type: ignore
    except (ValueError, AttributeError):
        await message.answer("❌ Введите число от 0.2 до 50:")
        return
    if value < 0.2 or value > 50:
        await message.answer("❌ Значение должно быть от 0.2 до 50:")
        return

    data = await state.get_data()
    await state.clear()

    user_id = message.from_user.id  # type: ignore[union-attr]

    from bot.db.models import TradingSettings, OrderType
    demo_settings = TradingSettings(
        user_id=user_id,
        pair="KASUSDT",
        order_type=OrderType.DYNAMIC,
        order_param=data["dynamic_pct"],
        profit_pct=0.5,
        drop_pct=value,
    )

    async def send_msg(text: str) -> None:
        from aiogram import Bot
        b: Bot = message.bot  # type: ignore[assignment]
        await b.send_message(user_id, text)

    engine = DemoEngine(
        user_id=user_id,
        settings=demo_settings,
        db=db,
        send_message=send_msg,
    )
    _demo_engines[user_id] = engine

    await message.answer("💼 [Демо-счёт]\n\n🔄 Запуск торгового алгоритма...")
    await engine.start()
