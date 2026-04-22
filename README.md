# MEXC Scalping Bot

Telegram-бот для автоматического скальпинга на бирже MEXC (спот).

Стратегия: покупка по рынку, выставление лимитного ордера на продажу с заданным % прибыли, докупка при падении цены на заданный %.

## Возможности

- Автоматическая торговля BTC/USDC, KAS/USDT, KAS/USDC, XRP/USDT, SOL/USDT
- Динамические и фиксированные ордера
- WebSocket мониторинг цен в реальном времени
- REST polling для обнаружения исполненных sell-ордеров
- REST fallback для пар с низким объёмом (каждые 15 сек)
- Восстановление после сбоев (SQLite WAL + автомиграция схемы)
- Сверка позиций при старте с уведомлениями о закрытых позициях
- Демо-режим с виртуальным балансом $5000
- Кнопочное меню с подменю и навигацией (reply + inline keyboards)
- Значения настроек отображаются прямо на кнопках
- Пагинация открытых позиций (10 шт. на странице)
- Настраиваемый интервал автопокупки (1–60 сек)
- Переключатель автопокупки при падении цены (ВКЛ/ВЫКЛ)
- Сброс настроек на дефолтные с подтверждением
- Подавление флуда при нехватке средств (однократное уведомление)
- Ежедневная сводка по прибыли (00:00 МСК)
- Ежемесячная сводка (1-е число, 06:00 МСК)
- Шифрование API-ключей (Fernet AES-128-CBC)
- Диалог подтверждения при смене API-ключей
- Автоостановка при невалидных API-ключах (ошибка 10072, после 5 подряд)
- Устойчивость к сетевым сбоям: таймауты 30/10 сек, backoff 5→60 сек
- Ограничение доступа по Telegram user ID

## Управление ботом

### Главное меню (reply-кнопки)

| Кнопка | Подменю |
|--------|---------|
| 📊 Торговля | ▶️ Старт, ⏹ Стоп, 📈 Статус, 🛒 Купить |
| 💰 Информация | 💵 Баланс, 💲 Цена, 📋 Позиции, 📊 Средняя, 📈 Результаты |
| ⚙️ Настройки | Пара, Тип ордера, Размер, Прибыль%, Снижение%, Интервал автопокупки, Автопокупка при падении (вкл/выкл), Комиссия, Сброс |
| ❓ Помощь | Справка с описанием всех команд |

### Команды

| Команда | Описание |
|---------|----------|
| `/start` | Регистрация |
| `/set_api` | Привязка API-ключей MEXC |
| `/start_trade` | Запуск торговли |
| `/stop_trade` | Остановка торговли |
| `/status` | Текущий статус алгоритма |
| `/buy` | Немедленная покупка |
| `/price` | Текущая цена |
| `/balance` | Баланс на бирже |
| `/results` | Результаты за период |
| `/open_orders` | Открытые позиции |
| `/average` | Средняя цена покупки |
| `/settings` | Параметры торговли |
| `/fee` | Настройка комиссии |
| `/demo` | Демо-счёт |
| `/help` | Справка |

## Стек

- Python 3.12, aiogram 3.x
- aiohttp (MEXC REST API), websockets (WS)
- aiosqlite (SQLite WAL)
- cryptography (Fernet)
- APScheduler, pydantic-settings, structlog

## Быстрый старт

```bash
# 1. Клонировать
git clone https://github.com/Drovosex/trading_bot.git
cd trading_bot

# 2. Создать .env
cp .env.example .env
# Заполнить BOT_TOKEN, ENCRYPTION_KEY, ADMIN_USER_ID

# 3. Сгенерировать ключ шифрования
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 4. Запустить
docker compose up -d
```

## Запуск без Docker

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows
pip install -r requirements.txt
python -m bot
```

## Тесты

```bash
pip install -r requirements.txt
python -m pytest tests/ -v
```

34 теста: calculator, strategy, order_manager (mocked), DB queries, crypto.

## Структура проекта

```
bot/
├── app.py              # Точка сборки: Bot + Dispatcher + middleware
├── config.py           # pydantic-settings конфигурация
├── db/                 # SQLite: schema, models, queries
├── exchange/           # MEXC API: REST client, WebSocket, models
├── trading/            # Торговый движок: engine, strategy, calculator, order_manager
├── handlers/           # Telegram команды (aiogram routers)
│   └── menu.py         # Reply-кнопки → inline-подменю, навигация, пагинация
├── keyboards/
│   ├── inline.py       # Inline-клавиатуры (подменю, настройки, пагинация)
│   └── reply.py        # Главное reply-меню (2×2 кнопки)
├── middlewares/        # Auth (admin), Subscription (stub)
├── notifications/      # Уведомления (daily/monthly summary)
├── security/           # Fernet шифрование API-ключей
├── services/           # Демо-режим
└── utils/              # Форматирование, scheduler
```

## Переменные окружения

| Переменная | Описание | По умолчанию |
|-----------|----------|-------------|
| `BOT_TOKEN` | Токен Telegram бота | — |
| `ENCRYPTION_KEY` | Fernet-ключ для шифрования API-ключей | — |
| `ADMIN_USER_ID` | Telegram ID владельца (0 = без ограничений) | `0` |
| `DB_PATH` | Путь к SQLite базе | `data/bot.db` |
| `LOG_LEVEL` | Уровень логирования | `INFO` |

## Требования к серверу

- VDS: 1 CPU, 1 GB RAM
- Docker или Python 3.12+
