from aiogram import Dispatcher

from bot.handlers.start import router as start_router
from bot.handlers.api_keys import router as api_keys_router
from bot.handlers.trading import router as trading_router
from bot.handlers.balance import router as balance_router
from bot.handlers.results import router as results_router
from bot.handlers.settings import router as settings_router
from bot.handlers.fee import router as fee_router
from bot.handlers.menu import router as menu_router


def register_all_handlers(dp: Dispatcher) -> None:
    dp.include_router(start_router)
    dp.include_router(api_keys_router)
    dp.include_router(trading_router)
    dp.include_router(balance_router)
    dp.include_router(results_router)
    dp.include_router(settings_router)
    dp.include_router(fee_router)
    # Menu button handlers — MUST be last so they don't interfere with FSM states
    dp.include_router(menu_router)
