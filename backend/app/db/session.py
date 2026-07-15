"""Async database engine and session management.

Exposes a single async engine per process and a FastAPI dependency
(`get_db`) that hands request handlers a scoped `AsyncSession`, closing
it (and rolling back on error) when the request is done.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

settings = get_settings()

engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=settings.db_echo,
    pool_pre_ping=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a request-scoped `AsyncSession`.

    Usage:
        @router.get("/things")
        async def list_things(db: AsyncSession = Depends(get_db)):
            ...

    Rolls back automatically on unhandled exceptions and always closes
    the session, so a single request can never leak a connection back
    to the pool in a bad state.
    """

    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for using a session outside of a FastAPI request
    (e.g. in scripts, background jobs, or the eval harness).
    """

    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def dispose_engine() -> None:
    """Dispose the engine's connection pool. Call on application shutdown."""

    await engine.dispose()
