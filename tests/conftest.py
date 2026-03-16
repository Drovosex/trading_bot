import pytest
import pytest_asyncio

from bot.db.database import Database


@pytest_asyncio.fixture
async def tmp_db():
    """In-memory SQLite database for testing."""
    db = Database(":memory:")
    await db.connect()
    yield db
    await db.close()
