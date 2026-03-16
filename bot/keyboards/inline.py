from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def settings_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Торговая пара", callback_data="set_pair")],
        [InlineKeyboardButton(text="Тип ордера", callback_data="set_order_type")],
        [InlineKeyboardButton(text="Размер ордера", callback_data="set_order_size")],
        [InlineKeyboardButton(text="Процент прибыли", callback_data="set_profit_pct")],
        [InlineKeyboardButton(text="Процент снижения цены", callback_data="set_drop_pct")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="set_close")],
    ])


def pair_select_kb() -> InlineKeyboardMarkup:
    pairs = [
        ("BTC/USDC", "pair_BTCUSDC"),
        ("KAS/USDT", "pair_KASUSDT"),
        ("XRP/USDT", "pair_XRPUSDT"),
        ("SOL/USDT", "pair_SOLUSDT"),
    ]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data=data)]
        for label, data in pairs
    ])


def order_type_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Динамический ордер", callback_data="otype_dynamic")],
        [InlineKeyboardButton(text="Фиксированный ордер", callback_data="otype_fixed")],
    ])


def results_period_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="За сегодня", callback_data="results_today")],
        [InlineKeyboardButton(text="За месяц", callback_data="results_month")],
        [InlineKeyboardButton(text="За всё время", callback_data="results_all")],
    ])


def fee_type_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Мейкер", callback_data="fee_maker")],
        [InlineKeyboardButton(text="Тейкер", callback_data="fee_taker")],
    ])
