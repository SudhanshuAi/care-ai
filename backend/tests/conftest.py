"""Test isolation for the process-global async SQLAlchemy engine.

The application intentionally owns one engine for production. Pytest's
function-scoped event loops cannot safely reuse an asyncpg connection
created by a prior test loop, so dispose the pool around each test.
"""

import pytest_asyncio

from app.db.session import dispose_engine


@pytest_asyncio.fixture(autouse=True)
async def dispose_async_engine_between_tests() -> None:
    await dispose_engine()
    yield
    await dispose_engine()
