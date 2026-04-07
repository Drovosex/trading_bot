# MEXC Scalping Bot — Project Context

## Overview
Telegram-бот для автоматического скальпинга криптовалют на бирже MEXC (спот).
Стратегия: market buy → limit sell с % прибыли → докупка при падении цены.

## Stack
- Python 3.12, aiogram 3.x (Telegram), aiohttp (MEXC REST), websockets (MEXC WS)
- aiosqlite (SQLite WAL), cryptography (Fernet), APScheduler, structlog, pydantic-settings

## Architecture

```
bot/
├── app.py                  # Bot + Dispatcher + middleware assembly
├── config.py               # pydantic-settings (.env)
├── db/                     # SQLite: schema (WAL), models, async queries
├── exchange/
│   ├── client.py           # MexcClient — REST API v3, typed exceptions
│   └── websocket.py        # MexcWebSocket — price streaming
├── trading/
│   ├── engine.py           # TradingEngine — main loop, auto-stop on InvalidApiKey
│   ├── strategy.py         # ScalpStrategy — drop-buy logic
│   ├── calculator.py       # Order sizing, sell price, expected income
│   └── order_manager.py    # Buy/sell execution, fill detection
├── handlers/
│   ├── menu.py             # Reply keyboard → inline submenus, navigation, pagination
│   ├── trading.py          # Start/stop/status/buy commands
│   ├── settings.py         # FSM-based settings input with cancel
│   ├── fee.py              # Fee settings (maker/taker) with cancel
│   ├── api_keys.py         # API key binding with confirmation dialog
│   ├── balance.py          # Balance query
│   ├── results.py          # Trading results by period
│   └── start.py            # /start, /help
├── keyboards/
│   ├── reply.py            # Main 2×2 reply keyboard
│   └── inline.py           # All inline keyboards (submenus, pagination, cancel)
├── notifications/notifier.py  # Daily (00:00 MSK) / monthly (1st, 06:00 MSK) summaries
├── security/crypto.py      # Fernet encryption for API keys
├── middlewares/auth.py      # Admin user ID check
└── utils/
    ├── formatting.py        # Message formatting, pair info, precision maps
    └── scheduler.py         # APScheduler cron setup
```

## Key Patterns

### Telegram UI
- **Reply keyboard** (persistent, 2×2): Торговля, Информация, Настройки, Помощь
- **Inline keyboards** for submenus — each has 🔙 Назад (back button)
- **Message tracking**: `_last_menu` dict in menu.py — old inline messages deleted on navigation
- **FSM inputs**: all have ❌ Отмена (cancel) button, prompt messages deleted after input
- **Pagination**: positions shown 10 per page with ◀️ ▶️ navigation

### Trading Engine
- One `TradingEngine` instance per user, stored in `app["engines"]`
- WebSocket for real-time price + REST fallback every 15s for low-volume pairs
- Active position concept: only the last buy triggers re-buy on sell fill
- **Auto-stop**: 5 consecutive `InvalidApiKey` errors → engine stops, notifies user
- Adaptive poll intervals: 30s (no positions), 5s (1-5), 3s (6+)

### MEXC API
- All requests signed with HMAC-SHA256
- Error 10072 → `InvalidApiKey` (auto-stop trigger)
- Error 10101 → `InsufficientBalance`
- POST/DELETE: params in query string + `Content-Type: application/json` header

### Security
- API keys encrypted with Fernet (AES-128-CBC) in SQLite
- Key messages deleted from Telegram chat after processing
- `/set_api` has confirmation dialog if keys already exist

## Deployment
- VPS: `vps_new` (REDACTED_IP), 1 CPU / 1 GB RAM
- systemd service: `trading-bot` at `/opt/trading_bot/`
- Python venv: `/opt/trading_bot/.venv/`
- DB: `/opt/trading_bot/data/bot.db`
- Deploy: `scp` files → `systemctl restart trading-bot`

## Important IDs
- Bot: `@REDACTED_BOT` (id: REDACTED_BOT_ID)
- Admin user_id: REDACTED_USER_ID

## Conventions
- Use `message.chat.id` (not `message.from_user.id`) in callback handlers — callback.message.from_user is the bot
- All handlers use structlog for logging
- Settings changes sync to running engine in real-time
- Router registration order matters: menu_router registered LAST (catches reply keyboard text)
- Language: Russian for all user-facing messages
