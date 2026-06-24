from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


# Main menu button labels
BTN_TRADING = "📊 Торговля"
BTN_INFO = "💰 Информация"
BTN_SETTINGS = "⚙️ Настройки"
BTN_HELP = "ℹ️ Помощь"

ALL_MENU_BUTTONS = {BTN_TRADING, BTN_INFO, BTN_SETTINGS, BTN_HELP}


def main_menu_kb() -> ReplyKeyboardMarkup:
    """Reply keyboard with main menu sections.
    is_persistent=False so the keyboard hides on system Back press."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=BTN_TRADING),
                KeyboardButton(text=BTN_INFO),
            ],
            [
                KeyboardButton(text=BTN_SETTINGS),
                KeyboardButton(text=BTN_HELP),
            ],
        ],
        resize_keyboard=True,
        is_persistent=False,
    )
