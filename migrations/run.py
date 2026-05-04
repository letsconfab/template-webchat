"""Database migrations runner."""

import asyncio
from backend.database import AsyncSessionLocal
from sqlalchemy import text


async def run_migrations():
    """Run any pending database migrations."""
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
                    ADD COLUMN langfuse_secret_key VARCHAR(500),
                    ADD COLUMN langfuse_public_key VARCHAR(500),
                    ADD COLUMN langfuse_base_url VARCHAR(500)
                """)
                )
                print("Migration: Added langfuse columns to system_settings")
        except Exception as e:
            print(f"Migration check failed (may already exist): {e}")

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
            print(f"Migration check failed (may already exist): {e}")

        await db.commit()
        print("Migrations completed!")


if __name__ == "__main__":
    asyncio.run(run_migrations())
