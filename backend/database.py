"""Database configuration and connection setup."""

import os
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
    echo=True,  # Set to False in production
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
    """Initialize database tables."""
    # Import all models here to ensure they are registered
    from backend.models.user import User
    from backend.models.invite import Invite
    from backend.models.settings import SystemSettings
    from backend.models.wiki import (
        WikiPage,
        WikiVersion,
        KnowledgeInsight,
        UserFeedback,
        ChatMessage,
    )

    async with engine.begin() as conn:
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)

    # Run migrations
    await run_migrations()


async def run_migrations():
    """Run database migrations."""
    from sqlalchemy import text

    async with AsyncSessionLocal() as db:
        # Check if langfuse columns exist, add if not
        try:
            result = await db.execute(
                text("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'system_settings' AND column_name = 'langfuse_secret_key'
            """)
            )
            if not result.fetchone():
                await db.execute(
                    text("""
                    ALTER TABLE system_settings 
                    ADD COLUMN IF NOT EXISTS langfuse_secret_key VARCHAR(500),
                    ADD COLUMN IF NOT EXISTS langfuse_public_key VARCHAR(500),
                    ADD COLUMN IF NOT EXISTS langfuse_base_url VARCHAR(500),
                    ADD COLUMN IF NOT EXISTS rag_provider VARCHAR(50) DEFAULT 'openai',
                    ADD COLUMN IF NOT EXISTS rag_model VARCHAR(100) DEFAULT 'gpt-4o-mini',
                    ADD COLUMN IF NOT EXISTS rag_api_key VARCHAR(500),
                    ADD COLUMN IF NOT EXISTS rag_base_url VARCHAR(500)
                """)
                )
                print("Migration: Added langfuse columns to system_settings")
        except Exception as e:
            pass  # Columns may already exist

        # Check if knowledge_documents table exists
        try:
            result = await db.execute(
                text("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_name = 'knowledge_documents'
            """)
            )
            if not result.fetchone():
                await db.execute(
                    text("""
                    CREATE TABLE knowledge_documents (
                        id SERIAL PRIMARY KEY,
                        filename VARCHAR(255) NOT NULL,
                        file_type VARCHAR(50) NOT NULL,
                        file_path VARCHAR(500) NOT NULL,
                        file_size INTEGER NOT NULL,
                        content_text TEXT,
                        created_by_id INTEGER REFERENCES users(id),
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                """)
                )
                await db.execute(
                    text("""
                    CREATE TABLE knowledge_chunks (
                        id SERIAL PRIMARY KEY,
                        document_id INTEGER NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
                        chunk_index INTEGER NOT NULL,
                        content TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """)
                )
                print(
                    "Migration: Created knowledge_documents and knowledge_chunks tables"
                )
        except Exception as e:
            pass  # Tables may already exist

        await db.commit()


async def close_db():
    """Close database connection."""
    await engine.dispose()
