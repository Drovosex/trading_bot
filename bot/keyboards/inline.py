from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


# ─── Main submenu keyboards (from reply buttons) ────────────────────────────

def trading_menu_kb() -> InlineKeyboardMarkup:
    """Submenu for 📊 Торговля."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="▶️ Старт", callback_data="menu_start_trade"),
            InlineKeyboardButton(text="⏹ Стоп", callback_data="menu_stop_trade"),
        ],
        [
            InlineKeyboardButton(text="📊 Статус", callback_data="menu_status"),
            InlineKeyboardButton(text="🛒 Купить", callback_data="menu_buy"),
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="menu_back"),
        ],
    ])


def info_menu_kb() -> InlineKeyboardMarkup:
    """Submenu for 💰 Информация."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💰 Баланс", callback_data="menu_balance"),
            InlineKeyboardButton(text="💱 Цена", callback_data="menu_price"),
        ],
        [
            InlineKeyboardButton(text="📋 Позиции", callback_data="menu_positions"),
            InlineKeyboardButton(text="📐 Средняя", callback_data="menu_average"),
        ],
        [
            InlineKeyboardButton(text="📈 Результаты", callback_data="menu_results"),
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="menu_back"),
        ],
    ])


# ─── Positions pagination ────────────────────────────────────────────────────

POSITIONS_PER_PAGE = 10


def positions_page_kb(page: int, total_pages: int) -> InlineKeyboardMarkup:
    """Keyboard for positions pagination."""
    buttons: list[InlineKeyboardButton] = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"pos_page_{page - 1}"))
    buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="pos_noop"))
    if page < total_pages - 1:
        buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"pos_page_{page + 1}"))

    rows = [buttons]
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_info")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ─── Settings keyboards ─────────────────────────────────────────────────────

def settings_main_kb(drop_buy_enabled: bool = True) -> InlineKeyboardMarkup:
    drop_buy_label = (
        "🔄 Автопокупка при падении: ВКЛ"
        if drop_buy_enabled
        else "🔄 Автопокупка при падении: ВЫКЛ"
    )
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💱 Торговая пара", callback_data="set_pair")],
        [InlineKeyboardButton(text="📦 Тип ордера", callback_data="set_order_type")],
        [InlineKeyboardButton(text="💵 Размер ордера", callback_data="set_order_size")],
        [InlineKeyboardButton(text="📈 Процент прибыли", callback_data="set_profit_pct")],
        [InlineKeyboardButton(text="📉 Процент снижения", callback_data="set_drop_pct")],
        [InlineKeyboardButton(text="⏱ Интервал автопокупки", callback_data="set_auto_buy_interval")],
        [InlineKeyboardButton(text=drop_buy_label, callback_data="toggle_drop_buy")],
        [InlineKeyboardButton(text="🏷 Комиссия", callback_data="set_fee")],
        [InlineKeyboardButton(text="♻️ Сброс настроек", callback_data="reset_settings_prompt")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_back")],
    ])


def reset_settings_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, сбросить", callback_data="reset_settings_confirm"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="back_to_settings"),
        ],
    ])


def pair_select_kb() -> InlineKeyboardMarkup:
    pairs = [
        ("BTC/USDC", "pair_BTCUSDC"),
        ("KAS/USDT", "pair_KASUSDT"),
        ("XRP/USDT", "pair_XRPUSDT"),
        ("SOL/USDT", "pair_SOLUSDT"),
        ("KAS/USDC", "pair_KASUSDC"),
    ]
    rows = [
        [InlineKeyboardButton(text=label, callback_data=data)]
        for label, data in pairs
    ]
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_settings")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def order_type_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Динамический ордер", callback_data="otype_dynamic")],
        [InlineKeyboardButton(text="Фиксированный ордер", callback_data="otype_fixed")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_settings")],
    ])


def results_period_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="За сегодня", callback_data="results_today")],
        [InlineKeyboardButton(text="За месяц", callback_data="results_month")],
        [InlineKeyboardButton(text="За всё время", callback_data="results_all")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_info")],
    ])


def fee_type_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Мейкер", callback_data="fee_maker")],
        [InlineKeyboardButton(text="Тейкер", callback_data="fee_taker")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_settings")],
    ])


def cancel_input_kb() -> InlineKeyboardMarkup:
    """Cancel button shown during FSM input (waiting for a number)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_input")],
    ])
