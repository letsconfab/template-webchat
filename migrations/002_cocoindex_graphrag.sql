-- Migration 002: Add CocoIndex/GraphRAG support, remove legacy KB tables

-- Add new columns to system_settings
ALTER TABLE system_settings
  ADD COLUMN IF NOT EXISTS google_drive_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS google_drive_refresh_token TEXT,
  ADD COLUMN IF NOT EXISTS google_drive_root_folder_id VARCHAR(500),
  ADD COLUMN IF NOT EXISTS google_drive_last_synced TIMESTAMP,
  ADD COLUMN IF NOT EXISTS neo4j_url VARCHAR(500) NOT NULL DEFAULT 'bolt://localhost:7687',
  ADD COLUMN IF NOT EXISTS neo4j_user VARCHAR(100) NOT NULL DEFAULT 'neo4j',
  ADD COLUMN IF NOT EXISTS neo4j_password VARCHAR(500),
  ADD COLUMN IF NOT EXISTS neo4j_database VARCHAR(100) NOT NULL DEFAULT 'neo4j',
  ADD COLUMN IF NOT EXISTS cocoindex_embedding_model VARCHAR(200) NOT NULL DEFAULT 'sentence-transformers/all-MiniLM-L6-v2',
  ADD COLUMN IF NOT EXISTS graphrag_enabled BOOLEAN NOT NULL DEFAULT FALSE;

-- Drop legacy knowledge book tables
DROP TABLE IF EXISTS knowledge_book_audit_log CASCADE;
DROP TABLE IF EXISTS knowledge_book_jobs CASCADE;
DROP TABLE IF EXISTS knowledge_book_nodes CASCADE;
DROP TABLE IF EXISTS knowledge_book_patches CASCADE;
DROP TABLE IF EXISTS knowledge_sources CASCADE;
DROP TABLE IF EXISTS knowledge_chunks CASCADE;
DROP TABLE IF EXISTS knowledge_documents CASCADE;

-- Remove unused columns from system_settings
ALTER TABLE system_settings
  DROP COLUMN IF EXISTS rag_provider,
  DROP COLUMN IF EXISTS rag_model,
  DROP COLUMN IF EXISTS rag_api_key,
  DROP COLUMN IF EXISTS rag_base_url;
