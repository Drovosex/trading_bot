from __future__ import annotations

import os
from pathlib import Path

import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT,
    api_key_enc BLOB,
    api_secret_enc BLOB,
    is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS trading_settings (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    pair TEXT NOT NULL DEFAULT 'BTCUSDC',
    order_type TEXT NOT NULL DEFAULT 'dynamic',
    order_param REAL NOT NULL DEFAULT 2.0,
    profit_pct REAL NOT NULL DEFAULT 0.7,
    drop_pct REAL NOT NULL DEFAULT 0.6,
    maker_fee REAL NOT NULL DEFAULT 0.0,
    taker_fee REAL NOT NULL DEFAULT 0.05
);

CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    pair TEXT NOT NULL,
    buy_price REAL NOT NULL,
    buy_qty REAL NOT NULL,
    buy_cost REAL NOT NULL,
    buy_order_id TEXT NOT NULL,
    buy_filled_at TIMESTAMP NOT NULL,
    sell_order_id TEXT,
    sell_target_price REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    sell_filled_at TIMESTAMP,
    sell_revenue REAL,
    profit REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_positions_user_status
    ON positions(user_id, status);
CREATE INDEX IF NOT EXISTS idx_positions_user_date
    ON positions(user_id, created_at);

CREATE TABLE IF NOT EXISTS subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    tier TEXT NOT NULL DEFAULT 'free',
    position_limit REAL,
    started_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    is_active BOOLEAN DEFAULT 1
);

CREATE TABLE IF NOT EXISTS referrals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    referrer_id INTEGER NOT NULL REFERENCES users(id),
    invitee_id INTEGER NOT NULL REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    referrer_bonus_days INTEGER DEFAULT 7,
    invitee_bonus_days INTEGER DEFAULT 14
);

CREATE TABLE IF NOT EXISTS demo_accounts (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    balance REAL NOT NULL DEFAULT 5000.0,
    initial_balance REAL NOT NULL DEFAULT 5000.0
);
"""


class Database:
    def __init__(self, db_path: str) -> None:
        self._path = db_path
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        path = Path(self._path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(path))
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA synchronous=NORMAL")
        await self._db.execute("PRAGMA busy_timeout=5000")
        await self._db.executescript(_SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._db
