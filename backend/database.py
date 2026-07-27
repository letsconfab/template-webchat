"""Database configuration and connection setup."""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base

# from config import config
from backend.config import config

# Database URL from environment variable
DATABASE_URL = config.DATABASE_URL

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Create base model class
Base = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Initialize model registration without changing the schema.

    Schema changes are an explicit deployment step through ``scripts/migrate.py``.
    Importing models here keeps relationship configuration deterministic.
    """
    from backend.models import (  # noqa: F401
        chat,
        diagnostics,
        feedback_case,
        invite,
        journey,
        settings,
        user,
        wiki,
    )


async def close_db():
    """Close database connection."""
    await engine.dispose()
