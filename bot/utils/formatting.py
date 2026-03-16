from __future__ import annotations

# Pair symbol → (base_asset, quote_asset)
PAIR_INFO: dict[str, tuple[str, str]] = {
    "BTCUSDC": ("BTC", "USDC"),
    "KASUSDT": ("KAS", "USDT"),
    "XRPUSDT": ("XRP", "USDT"),
    "SOLUSDT": ("SOL", "USDT"),
}

# Pair symbol → price decimal places for display
PAIR_PRICE_PRECISION: dict[str, int] = {
    "BTCUSDC": 2,
    "KASUSDT": 6,
    "XRPUSDT": 4,
    "SOLUSDT": 2,
}

# Pair symbol → quantity decimal places
PAIR_QTY_PRECISION: dict[str, int] = {
    "BTCUSDC": 5,
    "KASUSDT": 2,
    "XRPUSDT": 2,
    "SOLUSDT": 4,
}


def _fmt_price(pair: str, price: float) -> str:
    prec = PAIR_PRICE_PRECISION.get(pair, 6)
    return f"{price:.{prec}f}"


def _fmt_qty(pair: str, qty: float) -> str:
    prec = PAIR_QTY_PRECISION.get(pair, 2)
    return f"{qty:.{prec}f}"


def _base_quote(pair: str) -> tuple[str, str]:
    return PAIR_INFO.get(pair, (pair[:3], pair[3:]))


def format_buy(
    pair: str,
    qty: float,
    cost: float,
    price: float,
    sell_price: float,
    expected_income: float,
    is_demo: bool = False,
) -> str:
    base, quote = _base_quote(pair)
    prefix = "💼 [Демо-счёт]\n\n" if is_demo else ""
    return (
        f"{prefix}"
        f"☑️ ПОКУПКА\n"
        f"{_fmt_qty(pair, qty)} {base} за {cost:.2f} {quote}\n"
        f"по цене {_fmt_price(pair, price)} {quote}\n\n"
        f"🔜 Выставлено на продажу\n"
        f"по цене {_fmt_price(pair, sell_price)} {quote}\n\n"
        f"💲Ожидаемый доход\n"
        f"{expected_income:.2f} {quote}"
    )


def format_sell(
    pair: str,
    qty: float,
    revenue: float,
    price: float,
    profit: float,
    is_demo: bool = False,
) -> str:
    base, quote = _base_quote(pair)
    prefix = "💼 [Демо-счёт]\n\n" if is_demo else ""
    return (
        f"{prefix}"
        f"✅ ПРОДАЖА\n"
        f"{_fmt_qty(pair, qty)} {base} за {revenue:.2f} {quote}\n"
        f"по цене {_fmt_price(pair, price)} {quote}\n\n"
        f"💲 ДОХОД\n"
        f"{profit:.2f} {quote}"
    )


def format_price_drop(
    pair: str,
    drop_pct: float,
    from_price: float,
    is_demo: bool = False,
) -> str:
    quote = _base_quote(pair)[1]
    prefix = "💼 [Демо-счёт]\n\n" if is_demo else ""
    return (
        f"{prefix}"
        f"🔻 Цена упала\n"
        f"на {drop_pct}% от {_fmt_price(pair, from_price)} {quote}"
    )


def format_insufficient_funds(
    balance: float, required: float, quote: str = "USDT"
) -> str:
    return (
        f"⛔️ Недостаточно средств для открытия позиции\n\n"
        f"Баланс: {balance:.2f} {quote}\n"
        f"Требуется: {required:.2f} {quote}\n\n"
        f"💡 Чтобы продолжить торговлю, вы можете:\n"
        f"• пополнить баланс на бирже, либо\n"
        f"• уменьшить размер ордера через команду /settings\n\n"
        f"После этого запустите торговлю с помощью /start_trade"
    )


def format_balance(
    capital: float, free: float, positions_count: int, positions_cost: float,
    quote: str = "USDT",
) -> str:
    return (
        f"💰 БАЛАНС\n\n"
        f"Торговый капитал:\n"
        f"🔸 {capital:.2f} {quote}\n\n"
        f"Свободные средства:\n"
        f"🔸 {free:.2f} {quote}\n\n"
        f"Открытые позиции:\n"
        f"🔸 кол-во - {positions_count} шт.\n"
        f"🔸 куплено за {positions_cost:.2f} {quote}"
    )


def format_status(
    is_running: bool,
    pair: str,
    current_price: float,
    next_sell_price: float | None,
    next_sell_qty: float | None,
    next_drop_price: float | None,
    free_funds: float,
    open_count: int,
    today_profit: float,
    quote: str = "USDT",
) -> str:
    icon = "🟢" if is_running else "🔴"
    state = "Торговый алгоритм запущен" if is_running else "Торговый алгоритм не запущен"
    base, _ = _base_quote(pair)

    lines = [f"{icon} {state}\n"]
    lines.append(f"• {base}/{quote}: {_fmt_price(pair, current_price)}\n")

    if is_running and (next_sell_price or next_drop_price):
        lines.append("• Условия новой покупки:")
        if next_sell_price and next_sell_qty:
            lines.append(
                f"- при закрытии позиции📍по {_fmt_price(pair, next_sell_price)} "
                f"({_fmt_qty(pair, next_sell_qty)} {base})"
            )
        if next_drop_price:
            lines.append(f"- при падении цены до {_fmt_price(pair, next_drop_price)}")
        lines.append("")

    lines.append(f"• Свободные средства: {free_funds:.2f} {quote}\n/balance")
    lines.append(f"\n• Открытых позиций: {open_count} шт.\n/open_orders")
    lines.append(f"\n• Прибыль за сегодня: {today_profit:.2f} {quote}\n/results")

    return "\n".join(lines)


def format_daily_summary(
    date_str: str, closed_count: int, profit: float, quote: str = "USDT",
) -> str:
    if closed_count == 0:
        return f"📊 {date_str}\n\nНет закрытых позиций за день."
    return (
        f"📊 {date_str}\n\n"
        f"🔹 Кол-во закрытых позиций: {closed_count}\n"
        f"🔹 Прибыль: {profit:.2f} {quote}"
    )
