"""GraphRAG query service — provides tools for deep_agent to query Neo4j + Qdrant."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Optional

import httpx
from neo4j import AsyncGraphDatabase, AsyncSession as Neo4jSession

from backend.config import config

logger = logging.getLogger(__name__)

QDRANT_COLLECTION = "kb_chunks"
# Must match the model used by the CocoIndex pipeline (384-dim vectors).
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


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

    async def find_similar_chunks(self, query_text: str, top_k: int = 5) -> str:
        """Find chunks semantically similar to the query via Qdrant vector search."""
        if not await self.qdrant_ready():
            return ""

        embedding = await self._embed_query(query_text)
        if not embedding:
            return ""

        hits = await self._search_qdrant(embedding, top_k=top_k)
        if not hits:
            return ""

        parts = []
        for hit in hits:
            payload = hit.get("payload", {}) or {}
            text = (payload.get("text") or "").strip()
            if not text:
                continue
            source = payload.get("filename", "unknown")
            # Strip the Drive-id prefix from the filename for readability.
            if "_Copy of " in source:
                source = source.split("_Copy of ", 1)[1]
            elif "_" in source:
                source = source.split("_", 1)[1]
            score = hit.get("score")
            score_str = f" (relevance {score:.2f})" if isinstance(score, (int, float)) else ""
            parts.append(f"[Source: {source}{score_str}]\n{text[:1500]}")

        return "\n\n---\n\n".join(parts)

    # ── Combined retrieval (the main tool) ───────────────────────────────

    async def retrieve_knowledge(self, query: str, top_k: int = 5) -> str:
        """Main retrieval function: semantic chunk search (primary) + entity graph (secondary)."""
        # Vector search over the indexed document chunks is the primary grounding
        # signal — it returns the actual source text. The entity graph adds
        # structured relationships on top.
        vector_context = await self.find_similar_chunks(query, top_k=top_k)

        graph_context = ""
        if self._neo4j_ready:
            terms = [t.strip() for t in query.split() if len(t.strip()) > 3][:10]
            graph_context = await self.find_subgraph(terms)

        sections = []
        if vector_context:
            sections.append(
                "Relevant passages from the knowledge base:\n\n" + vector_context
            )
        if graph_context:
            sections.append(
                "Related concepts from the knowledge graph:\n\n" + graph_context
            )

        if not sections:
            return "No relevant information found in the knowledge base."

        return "\n\n========\n\n".join(sections)


graphrag_service = GraphRAGService()
