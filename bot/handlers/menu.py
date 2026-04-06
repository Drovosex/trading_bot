"""Handler for menu button presses.

Reply keyboard buttons open inline submenus.
Inline submenu buttons delegate to existing command handlers.
Old menu messages are deleted when new ones appear.
Back buttons navigate between menu levels.
"""
from __future__ import annotations

import math
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery

from bot.db.database import Database
from bot.db import queries
from bot.db.models import OrderType
from bot.keyboards.reply import BTN_TRADING, BTN_INFO, BTN_SETTINGS, BTN_HELP
from bot.keyboards.inline import (
    trading_menu_kb, info_menu_kb, settings_main_kb, fee_type_kb,
    positions_page_kb, results_period_kb, POSITIONS_PER_PAGE,
)
from bot.security.crypto import KeyVault
from bot.utils.formatting import PAIR_INFO, _fmt_price, _fmt_qty

import structlog
log = structlog.get_logger()

router = Router()

# Track last menu message per user so we can delete it
_last_menu: dict[int, int] = {}


async def _try_delete(message: Message) -> None:
    """Silently delete user's message (reply-button press)."""
    try:
        await message.delete()
    except Exception:
        pass


async def _delete_old_menu(chat_id: int, bot) -> None:
    """Delete previous menu message if exists."""
    old_id = _last_menu.pop(chat_id, None)
    if old_id:
        try:
            await bot.delete_message(chat_id, old_id)
        except Exception:
            pass


async def _send_menu(message: Message, text: str, reply_markup, bot=None) -> None:
    """Send a new menu message, deleting the old one first."""
    chat_id = message.chat.id
    _bot = bot or message.bot
    await _delete_old_menu(chat_id, _bot)
    sent = await message.answer(text, reply_markup=reply_markup)
    _last_menu[chat_id] = sent.message_id


async def _edit_to_menu(callback: CallbackQuery, text: str, reply_markup) -> None:
    """Edit current message to show a menu."""
    chat_id = callback.message.chat.id
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
        _last_menu[chat_id] = callback.message.message_id
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════════
#  Reply keyboard → open inline submenus
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(F.text == BTN_TRADING)
async def menu_trading(message: Message, engines: dict) -> None:
    await _try_delete(message)
    user_id = message.chat.id
    engine = engines.get(user_id)
    from bot.trading.state import EngineState
    is_running = engine and engine.state == EngineState.RUNNING
    status = "🟢 Алгоритм запущен" if is_running else "🔴 Алгоритм остановлен"
    await _send_menu(message, f"📊 Торговля\n{status}", trading_menu_kb())


@router.message(F.text == BTN_INFO)
async def menu_info(message: Message) -> None:
    await _try_delete(message)
    await _send_menu(message, "💰 Информация — выберите раздел:", info_menu_kb())


@router.message(F.text == BTN_SETTINGS)
async def menu_settings(message: Message, db: Database) -> None:
    await _try_delete(message)
    user_id = message.chat.id
    s = await queries.get_settings(db, user_id)
    if not s:
        await message.answer("❌ Настройки не найдены. Используйте /start сначала.")
        return

    from bot.handlers.settings import _settings_text
    await _send_menu(message, _settings_text(s), settings_main_kb())


@router.message(F.text == BTN_HELP)
async def menu_help(message: Message) -> None:
    await _try_delete(message)
    chat_id = message.chat.id
    await _delete_old_menu(chat_id, message.bot)
    from bot.handlers.start import cmd_help
    await cmd_help(message)


# ═══════════════════════════════════════════════════════════════════════════════
#  Back buttons — navigate between menu levels
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "menu_back")
async def cb_back(callback: CallbackQuery) -> None:
    """Delete the menu message — user returns to main reply keyboard."""
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass
    _last_menu.pop(callback.message.chat.id, None)


@router.callback_query(F.data == "back_to_info")
async def cb_back_to_info(callback: CallbackQuery) -> None:
    """Return to Info submenu."""
    await callback.answer()
    await _edit_to_menu(callback, "💰 Информация — выберите раздел:", info_menu_kb())


@router.callback_query(F.data == "back_to_trading")
async def cb_back_to_trading(callback: CallbackQuery, engines: dict) -> None:
    """Return to Trading submenu."""
    await callback.answer()
    user_id = callback.from_user.id
    engine = engines.get(user_id)
    from bot.trading.state import EngineState
    is_running = engine and engine.state == EngineState.RUNNING
    status = "🟢 Алгоритм запущен" if is_running else "🔴 Алгоритм остановлен"
    await _edit_to_menu(callback, f"📊 Торговля\n{status}", trading_menu_kb())


@router.callback_query(F.data == "back_to_settings")
async def cb_back_to_settings(callback: CallbackQuery, db: Database) -> None:
    """Return to Settings submenu with fresh data."""
    user_id = callback.from_user.id
    s = await queries.get_settings(db, user_id)
    if not s:
        await callback.answer("Ошибка")
        return

    from bot.handlers.settings import _settings_text
    await callback.answer()
    await _edit_to_menu(callback, _settings_text(s), settings_main_kb())


# ═══════════════════════════════════════════════════════════════════════════════
#  Inline callbacks — Trading submenu
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "menu_start_trade")
async def cb_start_trade(
    callback: CallbackQuery, db: Database, vault: KeyVault, engines: dict, bot: object
) -> None:
    from bot.handlers.trading import cmd_start_trade
    await callback.answer()
    await cmd_start_trade(callback.message, db, vault, engines, bot)


@router.callback_query(F.data == "menu_stop_trade")
async def cb_stop_trade(callback: CallbackQuery, engines: dict) -> None:
    from bot.handlers.trading import cmd_stop_trade
    await callback.answer()
    await cmd_stop_trade(callback.message, engines)


@router.callback_query(F.data == "menu_status")
async def cb_status(callback: CallbackQuery, db: Database, engines: dict, vault: KeyVault) -> None:
    from bot.handlers.trading import cmd_status
    await callback.answer()
    await cmd_status(callback.message, db, engines, vault)


@router.callback_query(F.data == "menu_buy")
async def cb_buy(
    callback: CallbackQuery, db: Database, vault: KeyVault, engines: dict
) -> None:
    from bot.handlers.trading import cmd_buy
    await callback.answer()
    await cmd_buy(callback.message, db, vault, engines)


# ═══════════════════════════════════════════════════════════════════════════════
#  Inline callbacks — Info submenu
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "menu_balance")
async def cb_balance(
    callback: CallbackQuery, db: Database, vault: KeyVault, engines: dict
) -> None:
    from bot.handlers.balance import cmd_balance
    await callback.answer()
    await cmd_balance(callback.message, db, vault, engines)


@router.callback_query(F.data == "menu_price")
async def cb_price(
    callback: CallbackQuery, db: Database, vault: KeyVault, engines: dict
) -> None:
    from bot.handlers.trading import cmd_price
    await callback.answer()
    await cmd_price(callback.message, db, vault, engines)


@router.callback_query(F.data == "menu_positions")
async def cb_positions(callback: CallbackQuery, db: Database, engines: dict) -> None:
    """Show positions page 0 — edit current message."""
    await callback.answer()
    await _show_positions_page(callback, db, engines, page=0)


@router.callback_query(F.data.startswith("pos_page_"))
async def cb_positions_page(callback: CallbackQuery, db: Database, engines: dict) -> None:
    """Navigate positions pages."""
    page = int(callback.data.replace("pos_page_", ""))  # type: ignore
    await callback.answer()
    await _show_positions_page(callback, db, engines, page=page)


@router.callback_query(F.data == "pos_noop")
async def cb_pos_noop(callback: CallbackQuery) -> None:
    await callback.answer()


async def _show_positions_page(
    callback: CallbackQuery, db: Database, engines: dict, page: int
) -> None:
    """Render a single page of positions and edit the message."""
    user_id = callback.message.chat.id
    positions = await queries.get_active_positions(db, user_id)

    if not positions:
        await _edit_to_menu(
            callback,
            "📋 У вас нет открытых позиций",
            positions_page_kb(0, 1),
        )
        return

    total_pages = max(1, math.ceil(len(positions) / POSITIONS_PER_PAGE))
    page = max(0, min(page, total_pages - 1))

    start = page * POSITIONS_PER_PAGE
    end = start + POSITIONS_PER_PAGE
    page_positions = positions[start:end]

    settings = await queries.get_settings(db, user_id)
    pair = settings.pair if settings else "BTCUSDC"

    engine = engines.get(user_id)
    active_id = engine._active_position_id if engine else None

    lines = [f"📋 Открытые позиции ({len(positions)} шт.)\n"]
    for i, p in enumerate(page_positions, start + 1):
        base, quote = PAIR_INFO.get(p.pair, (p.pair[:3], p.pair[3:]))
        active_mark = " 🔄" if p.id == active_id else ""
        lines.append(
            f"{i}. {_fmt_qty(p.pair, p.buy_qty)} {base}{active_mark}\n"
            f"   Покупка: {_fmt_price(p.pair, p.buy_price)} {quote}\n"
            f"   Цель: {_fmt_price(p.pair, p.sell_target_price)} {quote}\n"
            f"   Стоимость: {p.buy_cost:.2f} {quote}"
        )

    text = "\n".join(lines)
    kb = positions_page_kb(page, total_pages)
    await _edit_to_menu(callback, text, kb)


@router.callback_query(F.data == "menu_average")
async def cb_average(callback: CallbackQuery, db: Database) -> None:
    from bot.handlers.balance import cmd_average
    await callback.answer()
    await cmd_average(callback.message, db)


@router.callback_query(F.data == "menu_results")
async def cb_results(callback: CallbackQuery) -> None:
    await callback.answer()
    await _edit_to_menu(
        callback,
        "📊 Выберите период:",
        results_period_kb(),
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  Inline callback — Fee (inside settings menu)
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "set_fee")
async def cb_set_fee(callback: CallbackQuery, db: Database) -> None:
    user_id = callback.from_user.id
    s = await queries.get_settings(db, user_id)
    if not s:
        await callback.answer("Ошибка")
        return

    text = (
        f"🏷 Комиссия биржи\n\n"
        f"• Мейкер: {s.maker_fee}%\n"
        f"• Тейкер: {s.taker_fee}%\n\n"
        f"Выберите для изменения:"
    )
    await callback.answer()
    await _edit_to_menu(callback, text, fee_type_kb())
