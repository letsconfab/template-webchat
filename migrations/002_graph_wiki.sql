-- Migration 002: Graph-backed Knowledge Book wiki support

ALTER TABLE wiki_pages ADD COLUMN IF NOT EXISTS slug VARCHAR(255);
ALTER TABLE wiki_pages ADD COLUMN IF NOT EXISTS summary TEXT;
ALTER TABLE wiki_pages ADD COLUMN IF NOT EXISTS source_confidence VARCHAR(30);
ALTER TABLE wiki_pages ADD COLUMN IF NOT EXISTS is_auto_generated BOOLEAN DEFAULT FALSE;
ALTER TABLE wiki_pages ADD COLUMN IF NOT EXISTS last_graph_hash VARCHAR(128);

CREATE INDEX IF NOT EXISTS ix_wiki_pages_slug ON wiki_pages (slug);

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
);

CREATE INDEX IF NOT EXISTS ix_wiki_generation_jobs_lightrag_doc_id
    ON wiki_generation_jobs (lightrag_doc_id);

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
);

CREATE INDEX IF NOT EXISTS ix_wiki_graph_bindings_entity_id
    ON wiki_graph_bindings (entity_id);

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
);
