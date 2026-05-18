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
    from backend.models.knowledge import KnowledgeDocument, KnowledgeChunk
    from backend.models.wiki import (
        WikiPage,
        WikiVersion,
        WikiGenerationJob,
        WikiGraphBinding,
        WikiDraftRevision,
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
        bind = db.get_bind()
        dialect = bind.dialect.name if bind else ""

        async def table_exists(table_name: str) -> bool:
            if dialect == "sqlite":
                result = await db.execute(
                    text(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name=:table_name"
                    ),
                    {"table_name": table_name},
                )
            else:
                result = await db.execute(
                    text("""
                    SELECT table_name FROM information_schema.tables
                    WHERE table_name = :table_name
                """),
                    {"table_name": table_name},
                )
            return result.fetchone() is not None

        async def column_exists(table_name: str, column_name: str) -> bool:
            if dialect == "sqlite":
                result = await db.execute(text(f"PRAGMA table_info({table_name})"))
                return any(row[1] == column_name for row in result.fetchall())
            result = await db.execute(
                text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = :table_name AND column_name = :column_name
            """),
                {"table_name": table_name, "column_name": column_name},
            )
            return result.fetchone() is not None

        async def add_column_if_missing(
            table_name: str, column_name: str, column_sql: str
        ) -> None:
            if await column_exists(table_name, column_name):
                return
            if dialect == "sqlite":
                await db.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}"))
            else:
                await db.execute(
                    text(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_sql}")
                )

        # Check if langfuse columns exist, add if not
        try:
            if await table_exists("system_settings"):
                await add_column_if_missing(
                    "system_settings",
                    "langfuse_secret_key",
                    "langfuse_secret_key VARCHAR(500)",
                )
                await add_column_if_missing(
                    "system_settings",
                    "langfuse_public_key",
                    "langfuse_public_key VARCHAR(500)",
                )
                await add_column_if_missing(
                    "system_settings",
                    "langfuse_base_url",
                    "langfuse_base_url VARCHAR(500)",
                )
                print("Migration: Added langfuse columns to system_settings")
        except Exception as e:
            pass  # Columns may already exist

        # Check if knowledge_documents table exists
        try:
            if not await table_exists("knowledge_documents"):
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

        try:
            if await table_exists("wiki_pages"):
                for column_name, column_sql in [
                    ("slug", "slug VARCHAR(255)"),
                    ("summary", "summary TEXT"),
                    ("source_confidence", "source_confidence VARCHAR(30)"),
                    ("is_auto_generated", "is_auto_generated BOOLEAN DEFAULT FALSE"),
                    ("last_graph_hash", "last_graph_hash VARCHAR(128)"),
                ]:
                    await add_column_if_missing("wiki_pages", column_name, column_sql)

            await db.execute(
                text("""
                CREATE TABLE IF NOT EXISTS wiki_generation_jobs (
                    id SERIAL PRIMARY KEY,
                    document_id INTEGER REFERENCES knowledge_documents(id),
                    lightrag_doc_id VARCHAR(255),
                    status VARCHAR(40) NOT NULL DEFAULT 'queued',
                    error_message TEXT,
                    graph_before_hash VARCHAR(128),
                    graph_after_hash VARCHAR(128),
                    pages_created INTEGER DEFAULT 0,
                    pages_updated INTEGER DEFAULT 0,
                    created_by_id INTEGER REFERENCES users(id),
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
            )
            await db.execute(
                text("""
                CREATE TABLE IF NOT EXISTS wiki_graph_bindings (
                    id SERIAL PRIMARY KEY,
                    page_id INTEGER NOT NULL REFERENCES wiki_pages(id) ON DELETE CASCADE,
                    entity_id VARCHAR(500) NOT NULL,
                    entity_type VARCHAR(100),
                    graph_hash VARCHAR(128) NOT NULL,
                    source_doc_ids JSON,
                    source_chunk_ids JSON,
                    relation_ids JSON,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
            )
            await db.execute(
                text("""
                CREATE TABLE IF NOT EXISTS wiki_draft_revisions (
                    id SERIAL PRIMARY KEY,
                    page_id INTEGER REFERENCES wiki_pages(id),
                    title VARCHAR(255) NOT NULL,
                    proposed_content TEXT NOT NULL,
                    previous_content TEXT,
                    source VARCHAR(50) NOT NULL DEFAULT 'graph',
                    status VARCHAR(30) NOT NULL DEFAULT 'pending',
                    diff_from_previous TEXT,
                    generation_job_id INTEGER REFERENCES wiki_generation_jobs(id),
                    created_by_id INTEGER REFERENCES users(id),
                    reviewed_by_id INTEGER REFERENCES users(id),
                    created_at TIMESTAMP DEFAULT NOW(),
                    reviewed_at TIMESTAMP
                )
            """)
            )
            if dialect != "sqlite":
                await db.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_wiki_generation_jobs_lightrag_doc_id ON wiki_generation_jobs (lightrag_doc_id)"
                    )
                )
                await db.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_wiki_graph_bindings_entity_id ON wiki_graph_bindings (entity_id)"
                    )
                )
            print("Migration: Added graph wiki tables and columns")
        except Exception as e:
            pass

        await db.commit()


async def close_db():
    """Close database connection."""
    await engine.dispose()
