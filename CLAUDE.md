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
├── db/
│   ├── database.py         # SQLite WAL + auto-migration (ALTER TABLE on startup)
│   ├── models.py           # TradingSettings, Position, User, etc.
│   └── queries.py          # Async DB queries (defensive reads for new columns)
├── exchange/
│   ├── client.py           # MexcClient — REST API v3, typed exceptions, 30s timeout
│   └── websocket.py        # MexcWebSocket — price streaming
├── trading/
│   ├── engine.py           # TradingEngine — main loop, resilient to timeouts
│   ├── strategy.py         # ScalpStrategy — drop-buy logic
│   ├── calculator.py       # Order sizing, sell price, expected income
│   └── order_manager.py    # Buy/sell execution, fill detection
├── handlers/
│   ├── menu.py             # Reply keyboard → inline submenus, navigation, pagination
│   ├── trading.py          # Start/stop/status/buy commands
│   ├── settings.py         # FSM-based settings input with cancel, reset to defaults
│   ├── fee.py              # Fee settings (maker/taker) with cancel
│   ├── api_keys.py         # API key binding with confirmation dialog
│   ├── balance.py          # Balance query
│   ├── results.py          # Trading results by period
│   └── start.py            # /start, /help
├── keyboards/
│   ├── reply.py            # Main 2×2 reply keyboard
│   └── inline.py           # Inline keyboards (values rendered on buttons)
├── notifications/notifier.py  # Daily (00:00 MSK) / monthly (1st, 06:00 MSK) summaries
├── security/crypto.py      # Fernet encryption for API keys
├── middlewares/auth.py     # Admin user ID check
└── utils/
    ├── formatting.py       # Message formatting, pair info, precision maps
    └── scheduler.py        # APScheduler cron setup
```

## Key Patterns

### Telegram UI
- **Reply keyboard** (persistent, 2×2): Торговля, Информация, Настройки, Помощь
- **Inline keyboards** for submenus — each has 🔙 Назад (back button)
- **Settings buttons show current values inline** (`settings_main_kb` takes `TradingSettings`, renders each value into its button label — e.g. `💵 Размер: 2.0% от капитала`, `🔄 Автопокупка при падении: ВКЛ`)
- **Message tracking**: `_last_menu` dict in menu.py — old inline messages deleted on navigation
- **FSM inputs**: all have ❌ Отмена (cancel) button, prompt messages deleted after input
- **Pagination**: positions shown 10 per page with ◀️ ▶️ navigation

### Trading Settings
Schema (`trading_settings` table) — auto-migrated via `PRAGMA table_info` on startup:
- `pair`, `order_type` (dynamic/fixed), `order_param`
- `profit_pct`, `drop_pct`
- `maker_fee`, `taker_fee`
- `auto_buy_interval` (1-60s) — delay between sell of active order and next buy
- `drop_buy_enabled` (bool) — toggle for price-drop based additional buys

**Reset defaults** (preserves pair + fees): dynamic 2%, profit 0.3%, drop 1%, interval 30s, drop-buy ON.

### Trading Engine
- One `TradingEngine` instance per user, stored in `app["engines"]`
- WebSocket for real-time price + REST fallback every 15s for low-volume pairs
- **Active position concept**: only ONE position is the "active" one — only its sell fill triggers a new buy. Drop-buy also replaces the active position.
- **Active position pick on start**: when starting with existing positions, the one with the **lowest `sell_target_price`** becomes active (it'll sell first). The initial `_try_buy()` is skipped — no fresh buy on top of existing inventory. User is notified which order is active.
- **Auto-buy delay**: after sell of active position, wait `auto_buy_interval` seconds before new buy (interruptible if engine stopped)
- **Drop-buy toggle**: `_check_drop_buy` skipped entirely if `settings.drop_buy_enabled` is False
- **`_reconcile()` sends notifications** for positions filled while bot was offline (previously silent)
- **`_no_funds_price` flag**: after insufficient-funds failure, notify once; suppress repeat notifications until price drops another `drop_pct` below failure point, or a sell frees balance
- **Auto-stop**: 5 consecutive `InvalidApiKey` errors → engine stops, notifies user
- **Network resilience**: timeouts wrapped in `NetworkError`, backoff 5→60s, session recreated after 10 consecutive errors. Engine **does not crash** on transient network failures
- **`_safe_send` wrapper**: `send_message` is wrapped in `__init__` with try/except — a `TelegramNetworkError` from a notification never reaches the trading loop. Best-effort delivery only.
- **WS-outage notification dedup**: `_ws_failure_notified` flag. "Проблемы с подключением к бирже" is sent ONCE per outage (when `consecutive_failures >= WS_FAILURE_NOTIFY_THRESHOLD`) and re-armed only after WS reconnects (`consecutive_failures == 0`). Prevents flood during long outages.
- **Iteration-level resilience**: loop body extracted into `_loop_iteration()`. Each tick is wrapped in try/except — unknown exceptions log + sleep 5s + retry. Auto-stop only after `UNKNOWN_ERROR_LIMIT` (20) consecutive unexpected failures, not on the first error.
- Adaptive poll intervals: 30s (no positions), 5s (1-5), 3s (6+)

### MEXC API
- All requests signed with HMAC-SHA256
- `ClientTimeout(total=30, connect=10)` on aiohttp session
- Error 10072 → `InvalidApiKey` (auto-stop trigger)
- Error 10101 → `InsufficientBalance`
- Transient errors (timeouts, connection failures) → `NetworkError` (retryable)
- POST/DELETE: params in query string + `Content-Type: application/json` header

### Security
- API keys encrypted with Fernet (AES-128-CBC) in SQLite
- Key messages deleted from Telegram chat after processing
- `/set_api` has confirmation dialog if keys already exist

## Deployment
- VPS: SSH alias `vps_new`, 1 CPU / 1 GB RAM (IP in `CLAUDE.local.md`)
- systemd service: `trading-bot` at `/opt/trading_bot/`
- Python venv: `/opt/trading_bot/.venv/`
- DB: `/opt/trading_bot/data/bot.db`
- Deploy: `scp` files → `systemctl restart trading-bot`
- **journald limit**: 50MB (configured in `/etc/systemd/journald.conf`) to prevent memory pressure on 1GB VPS
- **Weekly auto-restart**: systemd timer `trading-bot-restart.timer` (Sun 02:00 UTC, `Persistent=true`, randomized delay up to 5 min) restarts the bot to mitigate the slow memory drift (~2 MB/day). Units live at `/etc/systemd/system/trading-bot-restart.{service,timer}`.
- **Telegram IP pin**: `/etc/hosts` has `149.154.167.220 api.telegram.org` because the IP that DNS returns for the VPS is unreachable from this provider. If that pinned IP ever fails, try another Telegram DC IP (`149.154.167.197/99/220`).

## Local-only context
Bot username, admin Telegram ID and VPS IP are stored in `CLAUDE.local.md`
(gitignored). Read it when those values are needed.

## Conventions
- Use `message.chat.id` (not `message.from_user.id`) in callback handlers — `callback.message.from_user` is the bot
- All handlers use structlog for logging
- Settings changes sync to running engine in real-time (mutate `engine.settings` alongside DB upsert)
- Router registration order matters: `menu_router` registered LAST (catches reply keyboard text)
- Language: Russian for all user-facing messages
- Schema changes: add to `_SCHEMA` for new DBs + add `ALTER TABLE` in `Database._migrate()` for existing DBs
