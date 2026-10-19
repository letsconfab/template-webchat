"""GraphRAG query service — provides tools for deep_agent to query Neo4j + Qdrant."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, Optional

import httpx
from neo4j import AsyncGraphDatabase, AsyncSession as Neo4jSession

from backend.config import config
from backend.services import library
from backend.services.source_provenance import format_retrieval_source

logger = logging.getLogger(__name__)

QDRANT_COLLECTION = "kb_chunks"
# Must match the model used by the CocoIndex pipeline (384-dim vectors).
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
NO_LIBRARY_PASSAGES = "No relevant passages found in the library."


class GraphRAGService:
    """Query Neo4j knowledge graph and Qdrant vector store for grounding context."""

    def __init__(self) -> None:
        self._neo4j_driver: Optional[Any] = None
        self._neo4j_ready = False
        self._qdrant_url = config.QDRANT_URL
        self._qdrant_ready = False
        self._qdrant_last_check: float = 0.0
        self._embedder: Optional[Any] = None

    async def _embed_query(self, text: str) -> Optional[list[float]]:
        """Embed a query string with the same model used for indexing.

        The model is loaded lazily on first use and the (CPU-bound) encode call
        runs in a worker thread so it never blocks the event loop.
        """
        try:
            if self._embedder is None:
                def _load():
                    from sentence_transformers import SentenceTransformer
                    return SentenceTransformer(EMBEDDING_MODEL)

                self._embedder = await asyncio.to_thread(_load)
                logger.info("Loaded query embedder: %s", EMBEDDING_MODEL)

            vec = await asyncio.to_thread(
                lambda: self._embedder.encode(text, normalize_embeddings=False)
            )
            return vec.tolist() if hasattr(vec, "tolist") else list(vec)
        except Exception as e:
            logger.error("Query embedding failed: %s", e)
            return None

    async def initialize(
        self,
        neo4j_uri: str,
        neo4j_user: str,
        neo4j_password: str,
        neo4j_database: str,
        qdrant_url: Optional[str] = None,
    ) -> None:
        if qdrant_url:
            self._qdrant_url = qdrant_url

        # Connect Neo4j
        try:
            self._neo4j_driver = AsyncGraphDatabase.driver(
                neo4j_uri, auth=(neo4j_user, neo4j_password)
            )
            await self._neo4j_driver.verify_connectivity()
            self._neo4j_ready = True
            logger.info("Neo4j connected: %s", neo4j_uri)
        except Exception as e:
            logger.warning("Neo4j connection failed: %s", e)
            self._neo4j_ready = False

        # Check Qdrant
        await self._check_qdrant()
        if not self._qdrant_ready:
            logger.warning("Qdrant collection '%s' not found", QDRANT_COLLECTION)

    async def _check_qdrant(self) -> bool:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self._qdrant_url}/collections/{QDRANT_COLLECTION}", timeout=5)
                self._qdrant_ready = resp.status_code == 200
        except Exception as e:
            logger.warning("Qdrant check failed: %s", e)
            self._qdrant_ready = False
        self._qdrant_last_check = time.monotonic()
        return self._qdrant_ready

    async def qdrant_ready(self) -> bool:
        """Whether the Qdrant collection exists; re-probes at most once per 60s when not ready."""
        if self._qdrant_ready:
            return True
        if time.monotonic() - self._qdrant_last_check < 60:
            return False
        return await self._check_qdrant()

    async def close(self) -> None:
        if self._neo4j_driver:
            await self._neo4j_driver.close()

    async def is_ready(self) -> bool:
        return self._neo4j_ready

    # ── Neo4j query ──────────────────────────────────────────────────────

    async def _query_neo4j(self, query: str) -> list[dict]:
        """Run a Cypher query and return results as list of dicts."""
        if not self._neo4j_driver:
            return []
        try:
            async with self._neo4j_driver.session() as session:
                result = await session.run(query)
                records = await result.data()
                return records
        except Exception as e:
            logger.error("Neo4j query error: %s", e)
            return []

    async def find_subgraph(self, terms: list[str]) -> str:
        """Find entities matching terms and their 1-2 hop neighborhood."""
        if not self._neo4j_ready or not self._neo4j_driver:
            return ""

        all_parts = []
        seen_entities = set()

        for term in terms:
            query = """
            MATCH (e:Entity)
            WHERE e.name CONTAINS $term
            OPTIONAL MATCH (e)-[r:RELATED_TO]-(related:Entity)
            RETURN e.name AS entity_name,
                   e.type AS entity_type,
                   e.description AS entity_desc,
                   collect(DISTINCT {name: related.name, rel: type(r)}) AS relations
            LIMIT 10
            """
            async with self._neo4j_driver.session() as session:
                result = await session.run(query, {"term": term})
                records = await result.data()

            for rec in records:
                ename = rec.get("entity_name")
                if ename and ename not in seen_entities:
                    seen_entities.add(ename)
                    rels = [f"{r['name']} ({r['rel']})" for r in rec.get("relations", []) if r.get("name")]
                    parts = [f"Entity: {ename} ({rec.get('entity_type', '?')})"]
                    if rec.get("entity_desc"):
                        parts.append(f"  Description: {rec['entity_desc']}")
                    if rels:
                        parts.append(f"  Related to: {', '.join(rels)}")
                    all_parts.append("\n".join(parts))

        return "\n\n".join(all_parts) if all_parts else ""

    # ── Qdrant query ─────────────────────────────────────────────────────

    async def _search_qdrant(
        self, embedding: list[float], top_k: int = 5
    ) -> list[dict]:
        """Search Qdrant for similar vectors."""
        try:
            async with httpx.AsyncClient() as client:
                payload = {
                    "vector": embedding,
                    "limit": top_k,
                    "with_payload": True,
                    "with_vector": False,
                }
                resp = await client.post(
                    f"{self._qdrant_url}/collections/{QDRANT_COLLECTION}/points/search",
                    json=payload,
                    timeout=10,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("result", [])
        except Exception as e:
            logger.error("Qdrant search error: %s", e)
        return []

    @staticmethod
    def _library_source(payload: dict) -> Optional[dict]:
        """The Library or Reference Document a passage came from, or None.

        A passage maps to its source by the Drive file id in its provenance,
        and must come from the manifest-synced copy (kb_cache/library/), not a
        root-folder copy of the same file. Unresolvable passages are dropped.
        """
        file_id = payload.get("google_file_id")
        if not file_id:
            return None
        doc = library.get_document(str(file_id))
        if not doc:
            return None
        if payload.get("source_dir") != library.LIBRARY_SOURCE_DIR:
            return None
        cache_path = doc.get("cache_path")
        if cache_path and payload.get("filename") != Path(cache_path).name:
            return None
        return doc

    async def retrieve_library_context(
        self, query: str, top_k: int = 5
    ) -> tuple[str, list[dict]]:
        """Passages from Library and Reference Documents, plus their citations.

        Knowledge-graph facts are not returned: graph entities carry no source
        document, so they cannot be attributed to a Library Document.
        """
        if not await self.qdrant_ready():
            return "", []
        embedding = await self._embed_query(query)
        if not embedding:
            return "", []

        # Oversample: passages outside the library are filtered out below.
        hits = await self._search_qdrant(embedding, top_k=top_k * 4)
        parts: list[str] = []
        citations: dict[str, dict] = {}
        for hit in hits:
            payload = hit.get("payload", {}) or {}
            text = (payload.get("text") or "").strip()
            doc = self._library_source(payload) if text else None
            if not doc:
                continue
            locator = payload.get("locator")
            chunk_index = payload.get("chunk_index")
            score = hit.get("score")
            parts.append(
                format_retrieval_source(
                    title=str(doc.get("title")),
                    passage=text[:1500],
                    google_url=library.document_file_url(str(doc["file_id"])),
                    locator=locator if isinstance(locator, str) else None,
                    modified_time=doc.get("modified_time"),
                    chunk_index=chunk_index if isinstance(chunk_index, int) else 0,
                    relevance=score if isinstance(score, (int, float)) else None,
                )
            )
            citations.setdefault(str(doc["file_id"]), library.citation(doc))
            if len(parts) >= top_k:
                break

        if not parts:
            return "", []
        context = "Relevant passages from the library:\n\n" + "\n\n---\n\n".join(parts)
        return context, list(citations.values())

    async def retrieve_knowledge(self, query: str, top_k: int = 5) -> str:
        """Library-scoped retrieval as text for the Librarian's tool."""
        context, _ = await self.retrieve_library_context(query, top_k=top_k)
        return context or NO_LIBRARY_PASSAGES


graphrag_service = GraphRAGService()
