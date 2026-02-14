from __future__ import annotations
"""SQLAlchemy 2.0 async database engine and session management.

Strict MySQL 8.0+ dialect — no PostgreSQL types (UUID, ARRAY, JSONB).
Forces utf8mb4 charset and pool health settings to prevent connection staleness.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_recycle=3600,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all ORM models.

    Forces utf8mb4 charset to prevent Emoji crashes in MySQL.
    """

    __table_args__ = {
        "mysql_charset": "utf8mb4",
        "mysql_collate": "utf8mb4_unicode_ci",
    }


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session.

    The session is committed on success and rolled back on error.
    Always closed after use.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Create the database (if missing) and all tables defined by Base metadata.

    Called once at application startup.
    Uses a separate connection without specifying a database to run CREATE DATABASE.
    """
    from urllib.parse import quote_plus
    from sqlalchemy import text

    # Step 1: Ensure the database exists
    admin_url = (
        f"mysql+asyncmy://{settings.DB_USER}:{quote_plus(settings.DB_PASSWORD)}"
        f"@{settings.DB_HOST}:{settings.DB_PORT}/?charset=utf8mb4"
    )
    admin_engine = create_async_engine(admin_url, echo=False)
    try:
        async with admin_engine.begin() as conn:
            await conn.execute(text(
                f"CREATE DATABASE IF NOT EXISTS `{settings.DB_NAME}` "
                f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            ))
    finally:
        await admin_engine.dispose()

    # Step 2: Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Dispose of the engine connection pool.

    Called at application shutdown.
    """
    await engine.dispose()
