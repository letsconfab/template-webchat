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
                    ADD COLUMN langfuse_base_url VARCHAR(500),
                    ADD COLUMN rag_provider VARCHAR(50) DEFAULT 'openai',
                    ADD COLUMN rag_model VARCHAR(100) DEFAULT 'gpt-4o-mini',
                    ADD COLUMN rag_api_key VARCHAR(500),
                    ADD COLUMN rag_base_url VARCHAR(500)
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

        # Knowledge book tables
        try:
            result = await db.execute(
                text("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_name = 'knowledge_sources'
            """)
            )
            if not result.fetchone():
                await db.execute(
                    text("""
                    CREATE TABLE knowledge_sources (
                        id SERIAL PRIMARY KEY,
                        original_filename VARCHAR(255) NOT NULL,
                        title VARCHAR(255),
                        file_type VARCHAR(20) NOT NULL,
                        storage_path VARCHAR(500) NOT NULL,
                        file_size INTEGER NOT NULL,
                        checksum VARCHAR(64) NOT NULL,
                        source_text TEXT,
                        redacted_text TEXT,
                        status VARCHAR(30) NOT NULL DEFAULT 'uploaded',
                        error_message TEXT,
                        uploaded_by_id INTEGER REFERENCES users(id),
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                """)
                )
                await db.execute(
                    text("""
                    CREATE TABLE knowledge_book_patches (
                        id SERIAL PRIMARY KEY,
                        source_id INTEGER NOT NULL REFERENCES knowledge_sources(id) ON DELETE CASCADE,
                        status VARCHAR(20) NOT NULL DEFAULT 'draft',
                        draft_title VARCHAR(255) NOT NULL,
                        draft_json JSON NOT NULL,
                        draft_markdown TEXT NOT NULL,
                        redaction_report JSON,
                        proposed_by_id INTEGER REFERENCES users(id),
                        committed_by_id INTEGER REFERENCES users(id),
                        committed_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                """)
                )
                await db.execute(
                    text("""
                    CREATE TABLE knowledge_book_audit_log (
                        id SERIAL PRIMARY KEY,
                        patch_id INTEGER NOT NULL REFERENCES knowledge_book_patches(id) ON DELETE CASCADE,
                        action VARCHAR(50) NOT NULL,
                        actor_user_id INTEGER REFERENCES users(id),
                        details JSON,
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """)
                )
                await db.execute(
                    text("""
                    CREATE TABLE knowledge_book_nodes (
                        id SERIAL PRIMARY KEY,
                        patch_id INTEGER NOT NULL REFERENCES knowledge_book_patches(id) ON DELETE CASCADE,
                        source_id INTEGER REFERENCES knowledge_sources(id),
                        parent_id INTEGER REFERENCES knowledge_book_nodes(id) ON DELETE CASCADE,
                        level INTEGER NOT NULL,
                        node_type VARCHAR(20) NOT NULL,
                        title VARCHAR(255) NOT NULL,
                        slug VARCHAR(255) NOT NULL,
                        content_md TEXT,
                        sort_order INTEGER NOT NULL DEFAULT 0,
                        is_active BOOLEAN NOT NULL DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                """)
                )
                await db.execute(
                    text("""
                    CREATE TABLE knowledge_book_jobs (
                        id SERIAL PRIMARY KEY,
                        source_id INTEGER NOT NULL REFERENCES knowledge_sources(id) ON DELETE CASCADE,
                        job_type VARCHAR(30) NOT NULL DEFAULT 'ingest',
                        status VARCHAR(30) NOT NULL DEFAULT 'pending',
                        progress INTEGER NOT NULL DEFAULT 0,
                        message TEXT,
                        started_at TIMESTAMP,
                        finished_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                """)
                )
                print("Migration: Created knowledge book tables")
        except Exception as e:
            print(f"Migration check failed (may already exist): {e}")

        await db.commit()
        print("Migration 001: Base schema setup complete")

    # --- Migration 002: CocoIndex / GraphRAG support ---
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'system_settings' AND column_name = 'google_drive_enabled'
            """)
            )
            if not result.fetchone():
                await db.execute(
                    text("""
                    ALTER TABLE system_settings
                      ADD COLUMN google_drive_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                      ADD COLUMN google_drive_refresh_token TEXT,
                      ADD COLUMN google_drive_root_folder_id VARCHAR(500),
                      ADD COLUMN google_drive_last_synced TIMESTAMP,
                      ADD COLUMN neo4j_url VARCHAR(500) NOT NULL DEFAULT 'bolt://localhost:7687',
                      ADD COLUMN neo4j_user VARCHAR(100) NOT NULL DEFAULT 'neo4j',
                      ADD COLUMN neo4j_password VARCHAR(500),
                      ADD COLUMN neo4j_database VARCHAR(100) NOT NULL DEFAULT 'neo4j',
                      ADD COLUMN cocoindex_embedding_model VARCHAR(200) NOT NULL DEFAULT 'sentence-transformers/all-MiniLM-L6-v2',
                      ADD COLUMN graphrag_enabled BOOLEAN NOT NULL DEFAULT FALSE
                """)
                )
                print("Migration 002: Added CocoIndex/GraphRAG columns to system_settings")
        except Exception as e:
            print(f"Migration 002 check failed: {e}")

        try:
            await db.execute(
                text("""
                DROP TABLE IF EXISTS knowledge_book_audit_log CASCADE;
                DROP TABLE IF EXISTS knowledge_book_jobs CASCADE;
                DROP TABLE IF EXISTS knowledge_book_nodes CASCADE;
                DROP TABLE IF EXISTS knowledge_book_patches CASCADE;
                DROP TABLE IF EXISTS knowledge_sources CASCADE;
                DROP TABLE IF EXISTS knowledge_chunks CASCADE;
                DROP TABLE IF EXISTS knowledge_documents CASCADE;
            """)
            )
            print("Migration 002: Dropped legacy knowledge book tables")
        except Exception as e:
            print(f"Migration 002 drop tables failed (may not exist): {e}")

        try:
            await db.execute(
                text("""
                ALTER TABLE system_settings
                  DROP COLUMN IF EXISTS rag_provider,
                  DROP COLUMN IF EXISTS rag_model,
                  DROP COLUMN IF EXISTS rag_api_key,
                  DROP COLUMN IF EXISTS rag_base_url
            """)
            )
            print("Migration 002: Removed unused RAG columns from system_settings")
        except Exception as e:
            print(f"Migration 002 drop columns failed: {e}")

        await db.commit()
        print("Migrations completed!")


if __name__ == "__main__":
    asyncio.run(run_migrations())
