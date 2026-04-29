"""
backend/api/database.py — SQLAlchemy async engine + session factory
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from api.config import settings

_is_sqlite = settings.DATABASE_URL.startswith("sqlite")

# SQLite (dev) uses NullPool and no pool_size/max_overflow
# PostgreSQL (prod) uses connection pooling
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.APP_ENV in {"development", "test"},
    **(
        {"poolclass": NullPool}
        if _is_sqlite
        else {"pool_size": 10, "max_overflow": 20, "pool_pre_ping": True}
    ),
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
