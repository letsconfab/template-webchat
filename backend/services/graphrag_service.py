"""GraphRAG query service — provides tools for deep_agent to query Neo4j + Qdrant."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import httpx
from neo4j import AsyncGraphDatabase, AsyncSession as Neo4jSession

from backend.config import config

logger = logging.getLogger(__name__)

QDRANT_COLLECTION = "kb_chunks"


class GraphRAGService:
    """Query Neo4j knowledge graph and Qdrant vector store for grounding context."""

    def __init__(self) -> None:
        self._neo4j_driver: Optional[Any] = None
        self._neo4j_ready = False
        self._qdrant_url = config.QDRANT_URL
        self._qdrant_ready = False

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
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self._qdrant_url}/collections/{QDRANT_COLLECTION}", timeout=5)
                self._qdrant_ready = resp.status_code == 200
                if not self._qdrant_ready:
                    logger.warning("Qdrant collection '%s' not found", QDRANT_COLLECTION)
        except Exception as e:
            logger.warning("Qdrant check failed: %s", e)
            self._qdrant_ready = False

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
            OPTIONAL MATCH (c:Chunk)-[:MENTIONS]->(e)
            RETURN e.name AS entity_name,
                   e.type AS entity_type,
                   e.description AS entity_desc,
                   collect(DISTINCT {name: related.name, rel: type(r)}) AS relations,
                   collect(DISTINCT c.text)[0..3] AS snippets
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
                    if rec.get("snippets"):
                        snippets = [s for s in rec["snippets"] if s]
                        if snippets:
                            parts.append(f"  Context: {snippets[0][:300]}")
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
        """Find chunks similar to query text."""
        if not self._qdrant_ready:
            return ""

        # We need to embed the query. Use the same embedding model.
        # Since we don't keep the embedder in memory here, we use a simple approach:
        # rely on the deep_agent to pass embeddings or use LLM to extract terms
        # For now, return empty — the main query flow uses retrieve_knowledge.
        return ""

    # ── Combined retrieval (the main tool) ───────────────────────────────

    async def retrieve_knowledge(self, query: str, top_k: int = 5) -> str:
        """Main retrieval function: extract entities, query graph + vectors, return context."""
        if not self._neo4j_ready:
            return "Knowledge graph is not connected."

        # Extract potential entity terms from the query (simple heuristic)
        # A more sophisticated approach would use LLM for entity extraction
        terms = [t.strip() for t in query.split() if len(t.strip()) > 3][:10]

        # Query Neo4j subgraph
        graph_context = await self.find_subgraph(terms)

        if not graph_context:
            return "No relevant information found in the knowledge base."

        return f"""
Relevant information from the knowledge base:

{graph_context}
""".strip()


graphrag_service = GraphRAGService()
