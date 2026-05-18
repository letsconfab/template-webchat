"""Graph-backed wiki generation service."""

import difflib
import hashlib
import json
import logging
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.llm_providers import LLMProvider
from backend.models.knowledge import KnowledgeChunk, KnowledgeDocument
from backend.models.settings import SystemSettings
from backend.models.wiki import (
    WikiDraftRevision,
    WikiGenerationJob,
    WikiGraphBinding,
    WikiPage,
    WikiVersion,
)
from backend.services.rag_anything_service import (
    make_lightrag_doc_id,
    rag_anything_service,
)

logger = logging.getLogger(__name__)


GENERIC_ENTITY_TYPES = {"", "unknown", "generic", "entity", "other"}
STOPWORD_TITLES = {
    "a",
    "an",
    "and",
    "or",
    "the",
    "to",
    "of",
    "in",
    "on",
    "for",
    "with",
}


class WikiGraphService:
    """Synchronize the LightRAG knowledge graph into reviewable wiki drafts."""

    def stable_hash(self, value: Any) -> str:
        payload = json.dumps(value, sort_keys=True, default=str, ensure_ascii=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def slugify(self, title: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        return slug or "untitled"

    def entity_id(self, entity: Dict[str, Any]) -> str:
        entity_id = (
            entity.get("id")
            or entity.get("entity_id")
            or entity.get("name")
            or entity.get("entity_name")
            or entity.get("label")
        )
        return str(entity_id or "").strip()

    def entity_title(self, entity: Dict[str, Any]) -> str:
        title = (
            entity.get("name")
            or entity.get("entity_name")
            or entity.get("label")
            or self.entity_id(entity)
        )
        return str(title or "Untitled").strip().strip('"')

    def entity_type(self, entity: Dict[str, Any]) -> Optional[str]:
        value = entity.get("entity_type") or entity.get("type")
        labels = entity.get("labels")
        if not value and isinstance(labels, list) and labels:
            value = labels[0]
        return str(value).strip() if value else None

    def entity_description(self, entity: Dict[str, Any]) -> str:
        value = (
            entity.get("description")
            or entity.get("summary")
            or entity.get("content")
            or entity.get("entity_description")
            or ""
        )
        return str(value).strip()

    def edge_endpoints(self, edge: Dict[str, Any]) -> Tuple[str, str]:
        source = edge.get("source") or edge.get("src_id") or edge.get("source_id")
        target = edge.get("target") or edge.get("tgt_id") or edge.get("target_id")
        return str(source or ""), str(target or "")

    def edge_description(self, edge: Dict[str, Any]) -> str:
        return str(
            edge.get("description")
            or edge.get("relationship")
            or edge.get("keywords")
            or edge.get("label")
            or edge.get("type")
            or "related to"
        ).strip()

    def source_doc_ids_from_payload(self, payload: Any) -> List[str]:
        text = json.dumps(payload, default=str, ensure_ascii=True)
        ids = set(re.findall(r"knowledge-document-\d+", text))
        ids.update(re.findall(r"(?:doc_id|document_id)['\":\s]+(\d+)", text))
        return sorted(ids)

    def relation_id(self, edge: Dict[str, Any]) -> str:
        source, target = self.edge_endpoints(edge)
        label = self.edge_description(edge)
        return self.stable_hash({"source": source, "target": target, "label": label})[:24]

    async def create_generation_job(
        self,
        db: AsyncSession,
        document_id: Optional[int],
        user_id: Optional[int],
        status: str = "queued",
    ) -> WikiGenerationJob:
        lightrag_doc_id = make_lightrag_doc_id(document_id) if document_id else None
        job = WikiGenerationJob(
            document_id=document_id,
            lightrag_doc_id=lightrag_doc_id,
            status=status,
            created_by_id=user_id,
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        return job

    async def process_existing_job(
        self,
        db: AsyncSession,
        job_id: int,
        file_path: str,
        filename: str,
        user_id: int,
    ) -> WikiGenerationJob:
        result = await db.execute(
            select(WikiGenerationJob).where(WikiGenerationJob.id == job_id)
        )
        job = result.scalar_one_or_none()
        if not job:
            raise ValueError(f"Wiki generation job {job_id} not found")

        try:
            job.status = "processing"
            job.updated_at = datetime.utcnow()
            before_nodes, before_edges = await self.load_graph_snapshot()
            job.graph_before_hash = self.stable_hash(
                {"nodes": before_nodes, "edges": before_edges}
            )
            await db.commit()

            process_result = await rag_anything_service.process_document(
                file_path=file_path,
                parse_method="auto",
                doc_id=job.lightrag_doc_id,
                file_name=filename,
            )
            if not process_result.get("success"):
                raise RuntimeError(process_result.get("error") or "RAG processing failed")

            nodes, edges = await self.load_graph_snapshot()
            job.graph_after_hash = self.stable_hash({"nodes": nodes, "edges": edges})
            created, updated = await self.create_drafts_for_changes(
                db=db,
                job=job,
                nodes=nodes,
                edges=edges,
                user_id=user_id,
                changed_doc_id=job.document_id,
            )
            job.pages_created = created
            job.pages_updated = updated
            job.status = "completed"
            job.updated_at = datetime.utcnow()
            await db.commit()
            await db.refresh(job)
            return job
        except Exception as e:
            logger.error(f"Graph wiki generation failed for job {job_id}: {e}", exc_info=True)
            job.status = "failed"
            job.error_message = str(e)
            job.updated_at = datetime.utcnow()
            await db.commit()
            await db.refresh(job)
            return job

    async def process_document_into_graph_and_wiki(
        self,
        db: AsyncSession,
        document_id: int,
        file_path: str,
        filename: str,
        user_id: int,
    ) -> WikiGenerationJob:
        job = await self.create_generation_job(
            db=db, document_id=document_id, user_id=user_id, status="processing"
        )
        return await self.process_existing_job(
            db=db,
            job_id=job.id,
            file_path=file_path,
            filename=filename,
            user_id=user_id,
        )

    async def sync_graph_to_wiki(
        self,
        db: AsyncSession,
        user_id: int,
        changed_doc_id: Optional[int] = None,
    ) -> WikiGenerationJob:
        job = await self.create_generation_job(
            db=db, document_id=changed_doc_id, user_id=user_id, status="processing"
        )
        try:
            nodes, edges = await self.load_graph_snapshot()
            graph_hash = self.stable_hash({"nodes": nodes, "edges": edges})
            job.graph_before_hash = graph_hash
            job.graph_after_hash = graph_hash
            created, updated = await self.create_drafts_for_changes(
                db=db,
                job=job,
                nodes=nodes,
                edges=edges,
                user_id=user_id,
                changed_doc_id=changed_doc_id,
            )
            if changed_doc_id:
                updated += await self.create_removed_document_review_drafts(
                    db=db,
                    job=job,
                    user_id=user_id,
                    changed_doc_id=changed_doc_id,
                    current_entity_ids={self.entity_id(node) for node in nodes},
                )
            job.pages_created = created
            job.pages_updated = updated
            job.status = "completed"
            job.updated_at = datetime.utcnow()
            await db.commit()
            await db.refresh(job)
            return job
        except Exception as e:
            job.status = "failed"
            job.error_message = str(e)
            job.updated_at = datetime.utcnow()
            await db.commit()
            await db.refresh(job)
            return job

    async def load_graph_snapshot(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        nodes = await rag_anything_service.get_all_graph_nodes()
        edges = await rag_anything_service.get_all_graph_edges()
        if not nodes:
            graph = await rag_anything_service.get_knowledge_graph(
                node_label="*", max_depth=2, max_nodes=500
            )
            nodes = graph.get("nodes", [])
            edges = graph.get("edges", edges)
        return self.sort_records(nodes), self.sort_records(edges)

    def sort_records(self, records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return sorted(
            [dict(record) for record in records or []],
            key=lambda item: json.dumps(item, sort_keys=True, default=str),
        )

    async def create_drafts_for_changes(
        self,
        db: AsyncSession,
        job: WikiGenerationJob,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        user_id: int,
        changed_doc_id: Optional[int] = None,
    ) -> Tuple[int, int]:
        node_by_id = {self.entity_id(node): node for node in nodes if self.entity_id(node)}
        edges_by_node: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for edge in edges:
            source, target = self.edge_endpoints(edge)
            if source:
                edges_by_node[source].append(edge)
            if target:
                edges_by_node[target].append(edge)

        result = await db.execute(select(WikiGraphBinding))
        bindings = {binding.entity_id: binding for binding in result.scalars().all()}

        created = 0
        updated = 0
        for entity_id, entity in node_by_id.items():
            related_edges = edges_by_node.get(entity_id, [])
            if changed_doc_id and not self.entity_matches_doc(
                entity, related_edges, changed_doc_id
            ):
                existing = bindings.get(entity_id)
                if existing:
                    continue

            if not self.should_generate_entity_page(entity, related_edges):
                continue

            related_nodes = self.related_nodes(entity_id, related_edges, node_by_id)
            graph_hash = self.entity_graph_hash(entity, related_edges, related_nodes)
            binding = bindings.get(entity_id)
            if binding and binding.graph_hash == graph_hash:
                continue
            if await self.pending_draft_exists(db, entity_id, graph_hash):
                continue

            page = await self.find_existing_page(db, entity, binding)
            source_chunks = await self.source_chunks_for_entity(
                db=db,
                entity=entity,
                related_edges=related_edges,
                changed_doc_id=changed_doc_id,
            )
            draft = await self.generate_concept_page_draft(
                db=db,
                entity=entity,
                related_edges=related_edges,
                related_nodes=related_nodes,
                source_chunks=source_chunks,
                existing_page=page,
                generation_job_id=job.id,
                user_id=user_id,
                graph_hash=graph_hash,
            )
            db.add(draft)
            if page:
                updated += 1
            else:
                created += 1
            job.pages_created = created
            job.pages_updated = updated
            job.updated_at = datetime.utcnow()
            await db.commit()

        return created, updated

    async def create_removed_document_review_drafts(
        self,
        db: AsyncSession,
        job: WikiGenerationJob,
        user_id: int,
        changed_doc_id: int,
        current_entity_ids: set[str],
    ) -> int:
        """Create review drafts for bound pages affected by a deleted source doc."""
        result = await db.execute(
            select(WikiGraphBinding, WikiPage)
            .join(WikiPage, WikiPage.id == WikiGraphBinding.page_id)
            .where(WikiPage.is_processed == True)
        )
        updated = 0
        for binding, page in result.all():
            source_doc_ids = {str(value) for value in (binding.source_doc_ids or [])}
            if str(changed_doc_id) not in source_doc_ids:
                continue
            if binding.entity_id in current_entity_ids:
                continue
            graph_hash = self.stable_hash(
                {
                    "entity_id": binding.entity_id,
                    "removed_document_id": changed_doc_id,
                    "previous_graph_hash": binding.graph_hash,
                }
            )
            if await self.pending_draft_exists(db, binding.entity_id, graph_hash):
                continue
            metadata = {
                "entity_id": binding.entity_id,
                "entity_type": binding.entity_type,
                "graph_hash": graph_hash,
                "source_doc_ids": sorted(source_doc_ids - {str(changed_doc_id)}),
                "source_chunk_ids": binding.source_chunk_ids or [],
                "relation_ids": binding.relation_ids or [],
                "summary": page.summary,
                "confidence": "low",
            }
            review_note = (
                "\n\n## Review Note\n"
                f"- Source document {changed_doc_id} was removed from the knowledge graph. "
                "Review this page for facts that depended on that document."
            )
            db.add(
                WikiDraftRevision(
                    page_id=page.id,
                    title=page.title,
                    proposed_content=(page.content or "") + review_note,
                    previous_content=page.content,
                    source="graph",
                    status="pending",
                    diff_from_previous=json.dumps(metadata, sort_keys=True),
                    generation_job_id=job.id,
                    created_by_id=user_id,
                )
            )
            updated += 1
        await db.commit()
        return updated

    def should_generate_entity_page(
        self, entity: Dict[str, Any], related_edges: List[Dict[str, Any]]
    ) -> bool:
        title = self.entity_title(entity)
        if not title or title.lower() in STOPWORD_TITLES or len(title) < 3:
            return False
        if Path(title).suffix.lower() in {".pdf", ".docx", ".txt", ".md"}:
            return False
        entity_type = (self.entity_type(entity) or "").lower()
        description = self.entity_description(entity)
        chunk_ids = self.source_doc_ids_from_payload(entity)
        return (
            len(related_edges) >= 2
            or entity_type not in GENERIC_ENTITY_TYPES
            or len(chunk_ids) >= 2
            or len(description) >= 40
            or len(related_edges) >= 1
        )

    def entity_matches_doc(
        self,
        entity: Dict[str, Any],
        related_edges: List[Dict[str, Any]],
        changed_doc_id: int,
    ) -> bool:
        doc_markers = {
            str(changed_doc_id),
            make_lightrag_doc_id(changed_doc_id),
        }
        payload = json.dumps(
            {"entity": entity, "edges": related_edges}, default=str, ensure_ascii=True
        )
        return any(marker in payload for marker in doc_markers)

    def related_nodes(
        self,
        entity_id: str,
        related_edges: List[Dict[str, Any]],
        node_by_id: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        nodes = []
        seen = set()
        for edge in related_edges:
            source, target = self.edge_endpoints(edge)
            other_id = target if source == entity_id else source
            if other_id and other_id not in seen and other_id in node_by_id:
                nodes.append(node_by_id[other_id])
                seen.add(other_id)
        return nodes

    def entity_graph_hash(
        self,
        entity: Dict[str, Any],
        related_edges: List[Dict[str, Any]],
        related_nodes: List[Dict[str, Any]],
    ) -> str:
        return self.stable_hash(
            {
                "entity": entity,
                "edges": self.sort_records(related_edges),
                "related_nodes": self.sort_records(related_nodes),
            }
        )

    async def pending_draft_exists(
        self, db: AsyncSession, entity_id: str, graph_hash: str
    ) -> bool:
        result = await db.execute(
            select(WikiDraftRevision).where(WikiDraftRevision.status == "pending")
        )
        for draft in result.scalars().all():
            metadata = self.parse_draft_metadata(draft)
            if metadata.get("entity_id") == entity_id and metadata.get("graph_hash") == graph_hash:
                return True
        return False

    async def find_existing_page(
        self,
        db: AsyncSession,
        entity: Dict[str, Any],
        binding: Optional[WikiGraphBinding],
    ) -> Optional[WikiPage]:
        if binding:
            result = await db.execute(select(WikiPage).where(WikiPage.id == binding.page_id))
            page = result.scalar_one_or_none()
            if page:
                return page
        slug = self.slugify(self.entity_title(entity))
        result = await db.execute(
            select(WikiPage)
            .where(WikiPage.slug == slug)
            .where(WikiPage.is_processed == True)
        )
        return result.scalar_one_or_none()

    async def source_chunks_for_entity(
        self,
        db: AsyncSession,
        entity: Dict[str, Any],
        related_edges: List[Dict[str, Any]],
        changed_doc_id: Optional[int],
    ) -> List[Dict[str, Any]]:
        query = select(KnowledgeChunk, KnowledgeDocument).join(
            KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id
        )
        if changed_doc_id:
            query = query.where(KnowledgeChunk.document_id == changed_doc_id)
        query = query.limit(5)
        result = await db.execute(query)
        rows = result.all()
        title = self.entity_title(entity).lower()
        chunks = []
        for chunk, doc in rows:
            if changed_doc_id or title in (chunk.content or "").lower():
                chunks.append(
                    {
                        "document_id": doc.id,
                        "filename": doc.filename,
                        "chunk_id": chunk.id,
                        "chunk_index": chunk.chunk_index,
                        "content": (chunk.content or "")[:1200],
                    }
                )
        return chunks[:5]

    async def generate_concept_page_draft(
        self,
        db: AsyncSession,
        entity: Dict[str, Any],
        related_edges: List[Dict[str, Any]],
        related_nodes: List[Dict[str, Any]],
        source_chunks: List[Dict[str, Any]],
        existing_page: Optional[WikiPage],
        generation_job_id: Optional[int],
        user_id: Optional[int],
        graph_hash: str,
    ) -> WikiDraftRevision:
        generated = await self.generate_with_llm(
            db, entity, related_edges, related_nodes, source_chunks
        )
        if not generated:
            generated = self.generate_template(entity, related_edges, related_nodes, source_chunks)

        entity_id = self.entity_id(entity)
        relation_ids = [self.relation_id(edge) for edge in related_edges]
        metadata = {
            "entity_id": entity_id,
            "entity_type": self.entity_type(entity),
            "graph_hash": graph_hash,
            "source_doc_ids": sorted(
                {
                    str(chunk["document_id"])
                    for chunk in source_chunks
                    if chunk.get("document_id") is not None
                }
            ),
            "source_chunk_ids": sorted(
                {
                    str(chunk["chunk_id"])
                    for chunk in source_chunks
                    if chunk.get("chunk_id") is not None
                }
            ),
            "relation_ids": relation_ids,
            "summary": generated.get("summary"),
            "confidence": generated.get("confidence", "medium"),
        }

        previous_content = existing_page.content if existing_page else None
        return WikiDraftRevision(
            page_id=existing_page.id if existing_page else None,
            title=generated.get("title") or self.entity_title(entity),
            proposed_content=generated.get("markdown") or "",
            previous_content=previous_content,
            source="graph",
            status="pending",
            diff_from_previous=json.dumps(metadata, sort_keys=True),
            generation_job_id=generation_job_id,
            created_by_id=user_id,
        )

    async def generate_with_llm(
        self,
        db: AsyncSession,
        entity: Dict[str, Any],
        related_edges: List[Dict[str, Any]],
        related_nodes: List[Dict[str, Any]],
        source_chunks: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        result = await db.execute(select(SystemSettings).limit(1))
        settings = result.scalar_one_or_none()
        if not settings or not settings.llm_api_key:
            return None

        llm_provider = LLMProvider(
            settings.llm_provider or "openai",
            settings.llm_model or "gpt-4o-mini",
            settings.llm_api_key,
        )
        llm = llm_provider.get_llm()
        if not llm:
            return None

        from langchain_core.messages import HumanMessage

        payload = {
            "entity": {
                "id": self.entity_id(entity),
                "title": self.entity_title(entity),
                "type": self.entity_type(entity),
                "description": self.entity_description(entity),
            },
            "related_entities": [
                {
                    "id": self.entity_id(node),
                    "title": self.entity_title(node),
                    "type": self.entity_type(node),
                    "description": self.entity_description(node),
                }
                for node in related_nodes[:12]
            ],
            "relationships": [
                {
                    "source": self.edge_endpoints(edge)[0],
                    "target": self.edge_endpoints(edge)[1],
                    "description": self.edge_description(edge),
                }
                for edge in related_edges[:20]
            ],
            "source_chunks": source_chunks,
        }
        prompt = f"""Create a graph-backed concept wiki page from this JSON.

Rules:
- Use only facts supported by the entity, relationships, and source chunks.
- Store wiki-style links as [[Concept Name]].
- Include source document references where filenames or chunk indexes are available.
- Return strict JSON only with these keys: title, summary, markdown, confidence, source_entity_ids, source_relation_ids.
- confidence must be one of: high, medium, low.

Input JSON:
{json.dumps(payload, ensure_ascii=False, default=str)}
"""

        response = await llm.ainvoke([HumanMessage(content=prompt)])
        parsed = self.extract_json(response.content)
        if parsed:
            return parsed

        repair_prompt = f"""Repair this response into strict JSON with keys title, summary, markdown, confidence, source_entity_ids, source_relation_ids. Return JSON only.

Response:
{response.content}
"""
        repair_response = await llm.ainvoke([HumanMessage(content=repair_prompt)])
        return self.extract_json(repair_response.content)

    def extract_json(self, content: str) -> Optional[Dict[str, Any]]:
        try:
            parsed = json.loads(content)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            pass
        match = re.search(r"\{.*\}", content or "", re.DOTALL)
        if not match:
            return None
        try:
            parsed = json.loads(match.group())
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None

    def generate_template(
        self,
        entity: Dict[str, Any],
        related_edges: List[Dict[str, Any]],
        related_nodes: List[Dict[str, Any]],
        source_chunks: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        title = self.entity_title(entity)
        description = self.entity_description(entity)
        summary = description or f"{title} is a graph entity extracted from source documents."

        facts = []
        if description:
            facts.append(description)
        entity_type = self.entity_type(entity)
        if entity_type:
            facts.append(f"Entity type: {entity_type}.")
        if not facts:
            facts.append("This concept was identified in the knowledge graph.")

        node_titles = {self.entity_id(node): self.entity_title(node) for node in related_nodes}
        relationship_lines = []
        see_also = []
        for edge in related_edges[:12]:
            source, target = self.edge_endpoints(edge)
            other_id = target if source == self.entity_id(entity) else source
            other_title = node_titles.get(other_id, other_id)
            if other_title:
                relationship_lines.append(
                    f"- **{other_title}**: {self.edge_description(edge)}."
                )
                see_also.append(f"- [[{other_title}]]")

        source_lines = []
        for chunk in source_chunks:
            source_lines.append(
                f"- {chunk.get('filename', 'Uploaded document')}, chunk {chunk.get('chunk_index', 0)}"
            )

        markdown = "\n\n".join(
            [
                f"# {title}",
                f"## Summary\n{summary}",
                "## Key Facts\n" + "\n".join(f"- {fact}" for fact in facts),
                "## Relationships\n"
                + ("\n".join(relationship_lines) if relationship_lines else "- No graph relationships available yet."),
                "## Source Documents\n"
                + ("\n".join(source_lines) if source_lines else "- Source document references are not available yet."),
                "## See Also\n" + ("\n".join(dict.fromkeys(see_also)) if see_also else "- None yet."),
            ]
        )
        return {
            "title": title,
            "summary": summary,
            "markdown": markdown,
            "confidence": "medium" if description or source_chunks else "low",
            "source_entity_ids": [self.entity_id(entity)],
            "source_relation_ids": [self.relation_id(edge) for edge in related_edges],
        }

    def parse_draft_metadata(self, draft: WikiDraftRevision) -> Dict[str, Any]:
        if not draft.diff_from_previous:
            return {}
        try:
            metadata = json.loads(draft.diff_from_previous)
            return metadata if isinstance(metadata, dict) else {}
        except Exception:
            return {}

    async def approve_draft(
        self, db: AsyncSession, draft_id: int, reviewer_id: int
    ) -> WikiDraftRevision:
        result = await db.execute(
            select(WikiDraftRevision).where(WikiDraftRevision.id == draft_id)
        )
        draft = result.scalar_one_or_none()
        if not draft:
            raise ValueError("Draft not found")
        if draft.status != "pending":
            raise ValueError("Draft has already been reviewed")

        metadata = self.parse_draft_metadata(draft)
        page = None
        if draft.page_id:
            result = await db.execute(select(WikiPage).where(WikiPage.id == draft.page_id))
            page = result.scalar_one_or_none()

        if page:
            db.add(
                WikiVersion(
                    page_id=page.id,
                    content=page.content or "",
                    diff_from_previous=self.render_diff(
                        page.content or "", draft.proposed_content
                    ),
                    created_by_id=reviewer_id,
                )
            )
            page.title = draft.title
            page.content = draft.proposed_content
            page.summary = metadata.get("summary")
            page.source_confidence = metadata.get("confidence")
            page.last_graph_hash = metadata.get("graph_hash")
            page.updated_at = datetime.utcnow()
        else:
            slug = await self.unique_slug(db, draft.title, metadata.get("entity_id", ""))
            page = WikiPage(
                title=draft.title,
                slug=slug,
                content=draft.proposed_content,
                summary=metadata.get("summary"),
                source_type="graph",
                source_id=draft.generation_job_id,
                is_draft=False,
                is_processed=True,
                is_auto_generated=True,
                source_confidence=metadata.get("confidence"),
                last_graph_hash=metadata.get("graph_hash"),
                created_by_id=reviewer_id,
            )
            db.add(page)
            await db.flush()

        if metadata.get("entity_id") and metadata.get("graph_hash"):
            await self.upsert_binding(db, page.id, metadata)

        draft.page_id = page.id
        draft.status = "approved"
        draft.reviewed_by_id = reviewer_id
        draft.reviewed_at = datetime.utcnow()
        await db.commit()
        await db.refresh(draft)
        return draft

    async def reject_draft(
        self, db: AsyncSession, draft_id: int, reviewer_id: int
    ) -> WikiDraftRevision:
        result = await db.execute(
            select(WikiDraftRevision).where(WikiDraftRevision.id == draft_id)
        )
        draft = result.scalar_one_or_none()
        if not draft:
            raise ValueError("Draft not found")
        if draft.status != "pending":
            raise ValueError("Draft has already been reviewed")
        draft.status = "rejected"
        draft.reviewed_by_id = reviewer_id
        draft.reviewed_at = datetime.utcnow()
        await db.commit()
        await db.refresh(draft)
        return draft

    def render_diff(self, previous: str, proposed: str) -> str:
        return "\n".join(
            difflib.unified_diff(
                previous.splitlines(),
                proposed.splitlines(),
                fromfile="previous",
                tofile="proposed",
                lineterm="",
            )
        )

    async def unique_slug(self, db: AsyncSession, title: str, entity_id: str) -> str:
        base_slug = self.slugify(title)
        slug = base_slug
        result = await db.execute(select(WikiPage).where(WikiPage.slug == slug))
        if not result.scalar_one_or_none():
            return slug
        suffix = self.stable_hash(entity_id or title)[:8]
        return f"{base_slug}-{suffix}"

    async def upsert_binding(
        self, db: AsyncSession, page_id: int, metadata: Dict[str, Any]
    ) -> WikiGraphBinding:
        entity_id = metadata["entity_id"]
        result = await db.execute(
            select(WikiGraphBinding).where(WikiGraphBinding.entity_id == entity_id)
        )
        binding = result.scalar_one_or_none()
        if not binding:
            binding = WikiGraphBinding(page_id=page_id, entity_id=entity_id, graph_hash=metadata["graph_hash"])
            db.add(binding)
        binding.page_id = page_id
        binding.entity_type = metadata.get("entity_type")
        binding.graph_hash = metadata["graph_hash"]
        binding.source_doc_ids = metadata.get("source_doc_ids")
        binding.source_chunk_ids = metadata.get("source_chunk_ids")
        binding.relation_ids = metadata.get("relation_ids")
        binding.updated_at = datetime.utcnow()
        return binding

    async def graph_status(self, db: AsyncSession) -> Dict[str, Any]:
        nodes, edges = await self.load_graph_snapshot()
        result = await db.execute(
            select(WikiGenerationJob).order_by(desc(WikiGenerationJob.created_at)).limit(1)
        )
        job = result.scalar_one_or_none()
        return {
            "rag_initialized": rag_anything_service.is_initialized,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "last_sync_job": (
                {
                    "id": job.id,
                    "status": job.status,
                }
                if job
                else None
            ),
        }


wiki_graph_service = WikiGraphService()
