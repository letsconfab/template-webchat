-- Migration 001: Add langfuse columns to system_settings
-- Run: psql -U postgres -d webchat_db -f migrations/001_add_langfuse_columns.sql

ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS langfuse_secret_key VARCHAR(500);
ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS langfuse_public_key VARCHAR(500);
ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS langfuse_base_url VARCHAR(500);

-- Migration 002: Add knowledge base tables
-- Run: psql -U postgres -d webchat_db -f migrations/002_create_knowledge_tables.sql

CREATE TABLE IF NOT EXISTS knowledge_documents (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    file_type VARCHAR(50) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    file_size INTEGER NOT NULL,
    content_text TEXT,
    created_by_id INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);