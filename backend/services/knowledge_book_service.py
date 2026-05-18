"""Service for source ingestion, knowledge book drafting, and indexing."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import AsyncSessionLocal
from backend.llm_providers import LLMProvider
from backend.models.knowledge_book import (
    KnowledgeBookAuditLog,
    KnowledgeBookJob,
    KnowledgeBookNode,
    KnowledgeBookPatch,
    KnowledgeSource,
)
from backend.models.settings import SystemSettings
from backend.models.user import User
from backend.services.rag_anything_service import rag_anything_service

logger = logging.getLogger(__name__)


class KnowledgeBookService:
    """Manage uploaded sources, draft patches, and the active knowledge book."""

    def __init__(self) -> None:
        self.storage_dir = Path(
            os.getenv("KNOWLEDGE_STORAGE_DIR", "./garage_storage")
        ).resolve()
        self.sources_dir = self.storage_dir / "sources"
        self.drafts_dir = self.storage_dir / "drafts"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.sources_dir.mkdir(parents=True, exist_ok=True)
        self.drafts_dir.mkdir(parents=True, exist_ok=True)
        self._tasks: set[asyncio.Task] = set()

    def _track_task(self, task: asyncio.Task) -> None:
        self._tasks.add(task)
        task.add_done_callback(lambda t: self._tasks.discard(t))

    def _now(self) -> datetime:
        return datetime.utcnow()

    def _sha256(self, content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def _slugify(self, value: str) -> str:
        value = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
        return value or "untitled"

    def _source_path(self, source_id: int, filename: str) -> Path:
        ext = Path(filename).suffix.lower() or ".bin"
        return self.sources_dir / f"{source_id}-{uuid4().hex}{ext}"

    async def _persist_source_bytes(
        self, source_id: int, filename: str, content: bytes
    ) -> Path:
        path = self._source_path(source_id, filename)
        path.write_bytes(content)
        return path

    def _extract_text(self, file_path: Path, file_type: str) -> str:
        file_type = file_type.lower()
        try:
            if file_type == "pdf":
                from pypdf import PdfReader

                reader = PdfReader(str(file_path))
                pages = []
                for page in reader.pages:
                    pages.append(page.extract_text() or "")
                return "\n\n".join(pages)

            if file_type == "docx":
                from docx import Document

                doc = Document(str(file_path))
                paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
                return "\n\n".join(paragraphs)

            return file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as exc:
            logger.error("Failed to extract text from %s: %s", file_path, exc)
            return ""

    def _redact_pii(self, content: str) -> Tuple[str, Dict[str, int]]:
        """Remove obvious PII from draft content."""
        stats = {
            "emails": 0,
            "phones": 0,
            "password_lines": 0,
            "contact_lines": 0,
            "secret_lines": 0,
            "addresses": 0,
        }

        def replace(pattern: str, label: str, text: str, repl: str = "[REDACTED]"):
            compiled = re.compile(pattern, flags=re.IGNORECASE | re.MULTILINE)
            matches = len(compiled.findall(text))
            stats[label] += matches
            return compiled.sub(repl, text)

        content = replace(r"[\w\.-]+@[\w\.-]+\.\w+", "emails", content)
        content = replace(
            r"\b(?:\+?\d{1,3}[\s-]?)?(?:\d[\s-]?){9,13}\b", "phones", content
        )

        redacted_lines = []
        for line in content.splitlines():
            lowered = line.lower()
            keywords = (
                "password",
                "secret",
                "token",
                "api key",
                "api-key",
                "mobile",
                "phone",
                "contact",
                "address",
                "email",
            )
            if any(key in lowered for key in keywords):
                if any(key in lowered for key in ("password", "secret", "token")):
                    stats["secret_lines"] += 1
                    continue
                if any(key in lowered for key in ("mobile", "phone", "contact", "email")):
                    stats["contact_lines"] += 1
                    continue
                if "address" in lowered:
                    stats["addresses"] += 1
                    continue
            redacted_lines.append(line)

        redacted = "\n".join(redacted_lines)
        redacted = re.sub(r"[ \t]+", " ", redacted)
        return redacted.strip(), stats

    def _chunk_text(self, text: str, chunk_size: int = 900) -> List[str]:
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if not paragraphs:
            return []

        chunks: List[str] = []
        current = ""
        for para in paragraphs:
            if len(current) + len(para) + 2 <= chunk_size:
                current = f"{current}\n\n{para}".strip()
            else:
                if current:
                    chunks.append(current.strip())
                current = para
        if current:
            chunks.append(current.strip())
        return chunks

    def _markdown_from_tree(self, tree: Dict[str, Any]) -> str:
        lines: List[str] = []
        book_title = tree.get("book_title") or tree.get("title") or "Knowledge Book"
        lines.append(f"# {book_title}")
        summary = tree.get("summary")
        if summary:
            lines.extend(["", summary, ""])

        for chapter in tree.get("chapters", []):
            lines.append(f"## {chapter.get('title', 'Chapter')}")
            chapter_summary = chapter.get("summary")
            if chapter_summary:
                lines.extend(["", chapter_summary, ""])
            for topic in chapter.get("topics", []):
                lines.append(f"### {topic.get('title', 'Topic')}")
                topic_summary = topic.get("summary")
                if topic_summary:
                    lines.extend(["", topic_summary, ""])
                for page in topic.get("pages", []):
                    lines.append(f"#### {page.get('title', 'Page')}")
                    page_content = page.get("content_md") or ""
                    if page_content:
                        lines.extend(["", page_content.strip(), ""])

        return "\n".join(lines).strip() + "\n"

    def _sanitize_tree(self, tree: Dict[str, Any]) -> Dict[str, Any]:
        book_title = (tree.get("book_title") or tree.get("title") or "Knowledge Book")
        sanitized = {
            "book_title": book_title.strip()[:255] or "Knowledge Book",
            "summary": (tree.get("summary") or "").strip(),
            "chapters": [],
        }

        for chapter in (tree.get("chapters") or [])[:20]:
            chapter_title = (chapter.get("title") or "Chapter").strip()[:255]
            chapter_node = {
                "title": chapter_title or "Chapter",
                "summary": (chapter.get("summary") or "").strip(),
                "topics": [],
            }
            for topic in (chapter.get("topics") or [])[:12]:
                topic_title = (topic.get("title") or "Topic").strip()[:255]
                topic_node = {
                    "title": topic_title or "Topic",
                    "summary": (topic.get("summary") or "").strip(),
                    "pages": [],
                }
                for page in (topic.get("pages") or [])[:12]:
                    page_title = (page.get("title") or "Page").strip()[:255]
                    page_content = (page.get("content_md") or "").strip()
                    if not page_content:
                        continue
                    topic_node["pages"].append(
                        {
                            "title": page_title or "Page",
                            "content_md": page_content,
                        }
                    )
                if topic_node["pages"]:
                    chapter_node["topics"].append(topic_node)
            if chapter_node["topics"]:
                sanitized["chapters"].append(chapter_node)

        if not sanitized["chapters"]:
            sanitized["chapters"] = [
                {
                    "title": "Overview",
                    "summary": "Auto-generated knowledge page",
                    "topics": [
                        {
                            "title": "Summary",
                            "summary": "",
                            "pages": [
                                {
                                    "title": "Page 1",
                                    "content_md": "No structured content was extracted.",
                                }
                            ],
                        }
                    ],
                }
            ]

        return sanitized

    def _default_tree_from_text(
        self, title: str, redacted_text: str, filename: str
    ) -> Dict[str, Any]:
        chunks = self._chunk_text(redacted_text)
        if not chunks:
            chunks = ["No structured content was extracted from the source."]

        chapter_title = title or Path(filename).stem.replace("_", " ").title()
        topics = []
        for index, chunk in enumerate(chunks[:8], start=1):
            topic_title = f"Section {index}"
            pages = []
            page_chunks = self._chunk_text(chunk, chunk_size=500) or [chunk]
            for page_index, page_chunk in enumerate(page_chunks[:4], start=1):
                pages.append(
                    {
                        "title": f"Page {page_index}",
                        "content_md": page_chunk,
                    }
                )
            topics.append({"title": topic_title, "summary": "", "pages": pages})

        return {
            "book_title": chapter_title,
            "summary": "Auto-generated from uploaded source.",
            "chapters": [
                {
                    "title": chapter_title,
                    "summary": "",
                    "topics": topics,
                }
            ],
        }

    async def _get_settings(self, db: AsyncSession) -> Optional[SystemSettings]:
        result = await db.execute(select(SystemSettings).limit(1))
        return result.scalar_one_or_none()

    async def _generate_tree_with_llm(
        self,
        db: AsyncSession,
        source: KnowledgeSource,
        redacted_text: str,
        current_outline: str,
    ) -> Optional[Dict[str, Any]]:
        settings = await self._get_settings(db)
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

        prompt = f"""
You are converting a redacted source into a three-level knowledge book.

Constraints:
- Maximum depth is 3 levels: chapter -> topic -> page.
- Never include email addresses, phone numbers, mobile numbers, addresses, passwords, secrets, tokens, or API keys.
- Keep only essential names if they are required for the topic.
- Prefer a concise, wiki-like markdown style.
- If an existing outline is provided, place the new content into the most relevant existing chapters/topics or create new ones if needed.
- Return ONLY valid JSON. No prose, no markdown fences.

Existing outline:
{current_outline or "(none)"}

Source file:
Filename: {source.original_filename}
File type: {source.file_type}

Redacted source text:
---
{redacted_text[:12000]}
---

Return JSON in this exact shape:
{{
  "book_title": "string",
  "summary": "string",
  "chapters": [
    {{
      "title": "string",
      "summary": "string",
      "topics": [
        {{
          "title": "string",
          "summary": "string",
          "pages": [
            {{
              "title": "string",
              "content_md": "markdown content"
            }}
          ]
        }}
      ]
    }}
  ]
}}
""".strip()

        try:
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            match = re.search(r"\{.*\}", str(response.content), re.DOTALL)
            if not match:
                return None
            return json.loads(match.group())
        except Exception as exc:
            logger.warning("LLM draft generation failed: %s", exc)
            return None

    async def _current_outline(self, db: AsyncSession) -> str:
        result = await db.execute(
            select(KnowledgeBookNode)
            .where(KnowledgeBookNode.is_active == True)  # noqa: E712
            .order_by(KnowledgeBookNode.level, KnowledgeBookNode.sort_order)
        )
        nodes = result.scalars().all()
        if not nodes:
            return ""

        nodes_by_id = {
            node.id: {
                "title": node.title,
                "node_type": node.node_type,
                "parent_id": node.parent_id,
            }
            for node in nodes
        }
        children_by_parent: Dict[Optional[int], List[Dict[str, Any]]] = {}
        for node in nodes:
            children_by_parent.setdefault(node.parent_id, []).append(
                {
                    "id": node.id,
                    "title": node.title,
                    "node_type": node.node_type,
                }
            )

        lines: List[str] = []

        def walk(node_id: int, indent: int = 0) -> None:
            node = nodes_by_id[node_id]
            lines.append(f"{'  ' * indent}- {node['title']} ({node['node_type']})")
            for child in children_by_parent.get(node_id, []):
                walk(child["id"], indent + 1)

        for root in children_by_parent.get(None, []):
            if nodes_by_id[root["id"]]["node_type"] == "chapter":
                walk(root["id"])
        return "\n".join(lines)

    async def _create_job(
        self, db: AsyncSession, source_id: int, message: str = "Queued"
    ) -> KnowledgeBookJob:
        job = KnowledgeBookJob(
            source_id=source_id,
            status="pending",
            progress=0,
            message=message,
            created_at=self._now(),
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        return job

    async def create_source_from_upload(
        self,
        db: AsyncSession,
        file: UploadFile,
        current_user: Optional[User] = None,
    ) -> Dict[str, Any]:
        content = await file.read()
        if not content:
            raise ValueError("Uploaded file is empty")

        file_type = (Path(file.filename).suffix.lower() or "").lstrip(".")
        if file_type not in {"pdf", "docx", "md"}:
            raise ValueError("Unsupported file type")

        source = KnowledgeSource(
            original_filename=file.filename,
            title=Path(file.filename).stem.replace("_", " ").title(),
            file_type=file_type,
            storage_path="",
            file_size=len(content),
            checksum=self._sha256(content),
            uploaded_by_id=current_user.id if current_user else None,
            status="uploaded",
        )
        db.add(source)
        await db.commit()
        await db.refresh(source)

        storage_path = await self._persist_source_bytes(source.id, file.filename, content)
        source.storage_path = str(storage_path)
        await db.commit()
        await db.refresh(source)

        await self._create_job(db, source.id, "Upload accepted")

        task = asyncio.create_task(self.process_source(source.id))
        self._track_task(task)

        return await self.get_source_summary(db, source.id)

    async def create_source_from_note(
        self,
        db: AsyncSession,
        content: str,
        title: str,
        current_user: Optional[User] = None,
    ) -> Dict[str, Any]:
        title = (title or "Quick Note").strip()
        payload = content.encode("utf-8")
        source = KnowledgeSource(
            original_filename=f"{self._slugify(title)}.md",
            title=title,
            file_type="md",
            storage_path="",
            file_size=len(payload),
            checksum=self._sha256(payload),
            source_text=content,
            uploaded_by_id=current_user.id if current_user else None,
            status="uploaded",
        )
        db.add(source)
        await db.commit()
        await db.refresh(source)

        storage_path = self.sources_dir / f"{source.id}-{uuid4().hex}.md"
        storage_path.write_text(content, encoding="utf-8")
        source.storage_path = str(storage_path)
        await db.commit()
        await db.refresh(source)

        await self._create_job(db, source.id, "Note accepted")

        task = asyncio.create_task(self.process_source(source.id))
        self._track_task(task)

        return await self.get_source_summary(db, source.id)

    async def process_source(self, source_id: int) -> None:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(KnowledgeSource).where(KnowledgeSource.id == source_id)
            )
            source = result.scalar_one_or_none()
            if not source:
                return

            job_result = await db.execute(
                select(KnowledgeBookJob)
                .where(KnowledgeBookJob.source_id == source_id)
                .order_by(KnowledgeBookJob.created_at.desc())
            )
            job = job_result.scalars().first()
            if not job:
                job = await self._create_job(db, source_id)

            try:
                source.status = "processing"
                source.error_message = None
                job.status = "processing"
                job.started_at = self._now()
                job.progress = 10
                job.message = "Extracting text"
                await db.commit()

                source_path = Path(source.storage_path)
                if source.source_text:
                    extracted = source.source_text
                else:
                    extracted = self._extract_text(source_path, source.file_type)
                source.source_text = extracted
                job.progress = 35
                job.message = "Redacting sensitive data"
                await db.commit()

                redacted_text, redaction_report = self._redact_pii(extracted)
                source.redacted_text = redacted_text
                await db.commit()

                if rag_anything_service.is_initialized:
                    try:
                        job.progress = 50
                        job.message = "Indexing source in RAG service"
                        await db.commit()
                        await rag_anything_service.ingest_file(
                            source.storage_path,
                            source_name=source.original_filename,
                            parse_method="auto",
                        )
                        job.progress = 65
                        job.message = "RAG service ingestion complete"
                        await db.commit()
                    except Exception as exc:
                        logger.warning(
                            "RAG service ingestion failed for source %s: %s",
                            source_id,
                            exc,
                        )

                current_outline = await self._current_outline(db)
                tree = await self._generate_tree_with_llm(
                    db, source, redacted_text, current_outline
                )
                if not tree:
                    tree = self._default_tree_from_text(
                        source.title or source.original_filename,
                        redacted_text,
                        source.original_filename,
                    )

                tree = self._sanitize_tree(tree)
                markdown = self._markdown_from_tree(tree)

                patch = KnowledgeBookPatch(
                    source_id=source.id,
                    status="draft",
                    draft_title=tree["book_title"],
                    draft_json=tree,
                    draft_markdown=markdown,
                    redaction_report=redaction_report,
                    proposed_by_id=source.uploaded_by_id,
                )
                db.add(patch)
                await db.commit()
                await db.refresh(patch)

                audit = KnowledgeBookAuditLog(
                    patch_id=patch.id,
                    action="draft_created",
                    actor_user_id=source.uploaded_by_id,
                    details={
                        "source_id": source.id,
                        "file_type": source.file_type,
                        "redaction_report": redaction_report,
                    },
                )
                db.add(audit)

                source.status = "draft_ready"
                job.progress = 100
                job.status = "completed"
                job.message = "Draft patch ready"
                job.finished_at = self._now()
                await db.commit()
                logger.info("Created draft patch %s for source %s", patch.id, source.id)
            except Exception as exc:
                logger.exception("Failed to process source %s", source_id)
                source.status = "failed"
                source.error_message = str(exc)
                job.status = "failed"
                job.message = str(exc)
                job.finished_at = self._now()
                await db.commit()

    async def get_source_summary(
        self, db: AsyncSession, source_id: int
    ) -> Dict[str, Any]:
        result = await db.execute(
            select(KnowledgeSource).where(KnowledgeSource.id == source_id)
        )
        source = result.scalar_one_or_none()
        if not source:
            raise ValueError("Source not found")

        patch_result = await db.execute(
            select(KnowledgeBookPatch)
            .where(KnowledgeBookPatch.source_id == source.id)
            .order_by(KnowledgeBookPatch.created_at.desc())
        )
        patch = patch_result.scalars().first()

        job_result = await db.execute(
            select(KnowledgeBookJob)
            .where(KnowledgeBookJob.source_id == source.id)
            .order_by(KnowledgeBookJob.created_at.desc())
        )
        job = job_result.scalars().first()

        return {
            "id": source.id,
            "original_filename": source.original_filename,
            "title": source.title,
            "file_type": source.file_type,
            "status": source.status,
            "error_message": source.error_message,
            "created_at": source.created_at.isoformat(),
            "updated_at": source.updated_at.isoformat(),
            "job": self._job_to_dict(job) if job else None,
            "patch": self._patch_to_dict(patch) if patch else None,
        }

    def _job_to_dict(self, job: KnowledgeBookJob) -> Dict[str, Any]:
        return {
            "id": job.id,
            "source_id": job.source_id,
            "job_type": job.job_type,
            "status": job.status,
            "progress": job.progress,
            "message": job.message,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            "created_at": job.created_at.isoformat(),
            "updated_at": job.updated_at.isoformat(),
        }

    def _patch_to_dict(self, patch: KnowledgeBookPatch) -> Dict[str, Any]:
        return {
            "id": patch.id,
            "source_id": patch.source_id,
            "status": patch.status,
            "draft_title": patch.draft_title,
            "draft_json": patch.draft_json,
            "draft_markdown": patch.draft_markdown,
            "redaction_report": patch.redaction_report,
            "created_at": patch.created_at.isoformat(),
            "updated_at": patch.updated_at.isoformat(),
            "committed_at": patch.committed_at.isoformat() if patch.committed_at else None,
        }

    def _node_to_dict(self, node: KnowledgeBookNode) -> Dict[str, Any]:
        return {
            "id": node.id,
            "patch_id": node.patch_id,
            "source_id": node.source_id,
            "parent_id": node.parent_id,
            "level": node.level,
            "node_type": node.node_type,
            "title": node.title,
            "slug": node.slug,
            "content_md": node.content_md,
            "sort_order": node.sort_order,
            "is_active": node.is_active,
            "created_at": node.created_at.isoformat(),
            "updated_at": node.updated_at.isoformat(),
            "children": [],
        }

    async def list_sources(self, db: AsyncSession) -> List[Dict[str, Any]]:
        result = await db.execute(
            select(KnowledgeSource).order_by(KnowledgeSource.created_at.desc())
        )
        sources = result.scalars().all()
        return [await self.get_source_summary(db, source.id) for source in sources]

    async def list_patches(self, db: AsyncSession) -> List[Dict[str, Any]]:
        result = await db.execute(
            select(KnowledgeBookPatch).order_by(KnowledgeBookPatch.created_at.desc())
        )
        patches = result.scalars().all()
        return [self._patch_to_dict(patch) for patch in patches]

    async def get_patch(self, db: AsyncSession, patch_id: int) -> Optional[Dict[str, Any]]:
        result = await db.execute(
            select(KnowledgeBookPatch).where(KnowledgeBookPatch.id == patch_id)
        )
        patch = result.scalar_one_or_none()
        return self._patch_to_dict(patch) if patch else None

    async def update_patch(
        self,
        db: AsyncSession,
        patch_id: int,
        draft_json: Dict[str, Any],
        draft_markdown: str,
        current_user: Optional[User] = None,
    ) -> Dict[str, Any]:
        result = await db.execute(
            select(KnowledgeBookPatch).where(KnowledgeBookPatch.id == patch_id)
        )
        patch = result.scalar_one_or_none()
        if not patch:
            raise ValueError("Patch not found")
        if patch.status != "draft":
            raise ValueError("Only draft patches can be edited")

        patch.draft_json = self._sanitize_tree(draft_json)
        patch.draft_markdown = draft_markdown
        patch.updated_at = self._now()
        db.add(
            KnowledgeBookAuditLog(
                patch_id=patch.id,
                action="draft_updated",
                actor_user_id=current_user.id if current_user else None,
                details={"title": patch.draft_title},
            )
        )
        await db.commit()
        await db.refresh(patch)
        return self._patch_to_dict(patch)

    async def _deactivate_current_book(self, db: AsyncSession) -> None:
        result = await db.execute(
            select(KnowledgeBookNode).where(KnowledgeBookNode.is_active == True)  # noqa: E712
        )
        for node in result.scalars().all():
            node.is_active = False
        await db.flush()

    def _build_nodes(
        self,
        tree: Dict[str, Any],
        patch_id: int,
        source_id: int,
    ) -> List[KnowledgeBookNode]:
        nodes: List[KnowledgeBookNode] = []

        def make_slug(title: str, fallback: str) -> str:
            slug = self._slugify(title)
            return slug or fallback

        chapter_order = 0
        for chapter in tree.get("chapters", []):
            chapter_order += 1
            chapter_node = KnowledgeBookNode(
                patch_id=patch_id,
                source_id=source_id,
                parent_id=None,
                level=1,
                node_type="chapter",
                title=chapter["title"],
                slug=make_slug(chapter["title"], f"chapter-{chapter_order}"),
                content_md=chapter.get("summary") or None,
                sort_order=chapter_order,
                is_active=True,
            )
            nodes.append(chapter_node)
            topic_order = 0
            for topic in chapter.get("topics", []):
                topic_order += 1
                topic_node = KnowledgeBookNode(
                    patch_id=patch_id,
                    source_id=source_id,
                    parent=chapter_node,
                    level=2,
                    node_type="topic",
                    title=topic["title"],
                    slug=make_slug(topic["title"], f"topic-{chapter_order}-{topic_order}"),
                    content_md=topic.get("summary") or None,
                    sort_order=topic_order,
                    is_active=True,
                )
                nodes.append(topic_node)
                page_order = 0
                for page in topic.get("pages", []):
                    page_order += 1
                    page_node = KnowledgeBookNode(
                        patch_id=patch_id,
                        source_id=source_id,
                        parent=topic_node,
                        level=3,
                        node_type="page",
                        title=page["title"],
                        slug=make_slug(
                            page["title"], f"page-{chapter_order}-{topic_order}-{page_order}"
                        ),
                        content_md=page.get("content_md"),
                        sort_order=page_order,
                        is_active=True,
                    )
                    nodes.append(page_node)

        return nodes

    async def commit_patch(
        self, db: AsyncSession, patch_id: int, current_user: Optional[User] = None
    ) -> Dict[str, Any]:
        result = await db.execute(
            select(KnowledgeBookPatch).where(KnowledgeBookPatch.id == patch_id)
        )
        patch = result.scalar_one_or_none()
        if not patch:
            raise ValueError("Patch not found")
        if patch.status == "committed":
            return self._patch_to_dict(patch)

        tree = self._sanitize_tree(patch.draft_json)

        await self._deactivate_current_book(db)
        nodes = self._build_nodes(tree, patch.id, patch.source_id)
        for node in nodes:
            db.add(node)

        patch.status = "committed"
        patch.committed_by_id = current_user.id if current_user else None
        patch.committed_at = self._now()
        patch.updated_at = self._now()

        source_result = await db.execute(
            select(KnowledgeSource).where(KnowledgeSource.id == patch.source_id)
        )
        source = source_result.scalar_one_or_none()
        if source:
            source.status = "committed"
            source.error_message = None

        db.add(
            KnowledgeBookAuditLog(
                patch_id=patch.id,
                action="patch_committed",
                actor_user_id=current_user.id if current_user else None,
                details={
                    "source_id": patch.source_id,
                    "book_title": tree.get("book_title"),
                    "node_count": len(nodes),
                },
            )
        )
        await db.commit()
        await db.refresh(patch)

        if rag_anything_service.is_initialized:
            await self.reindex_current_book()

        return self._patch_to_dict(patch)

    async def get_tree(self, db: AsyncSession) -> Dict[str, Any]:
        result = await db.execute(
            select(KnowledgeBookNode)
            .where(KnowledgeBookNode.is_active == True)  # noqa: E712
            .order_by(KnowledgeBookNode.level, KnowledgeBookNode.sort_order)
        )
        nodes = result.scalars().all()
        if not nodes:
            return {"book_title": "Knowledge Book", "chapters": []}

        nodes_by_id = {node.id: self._node_to_dict(node) for node in nodes}
        roots: List[Dict[str, Any]] = []
        for node in nodes:
            node_dict = nodes_by_id[node.id]
            if node.parent_id and node.parent_id in nodes_by_id:
                nodes_by_id[node.parent_id]["children"].append(node_dict)
            else:
                roots.append(node_dict)

        def simplify(node: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "id": node["id"],
                "title": node["title"],
                "node_type": node["node_type"],
                "level": node["level"],
                "content_md": node["content_md"],
                "children": [simplify(child) for child in node["children"]],
                "updated_at": node["updated_at"],
            }

        chapters = [simplify(node) for node in sorted(roots, key=lambda n: n["sort_order"]) if node["node_type"] == "chapter"]
        book_title = "Knowledge Book"
        if chapters:
            book_title = chapters[0]["title"] if chapters[0]["title"] else book_title
        return {"book_title": book_title, "chapters": chapters}

    async def get_audit(self, db: AsyncSession) -> List[Dict[str, Any]]:
        result = await db.execute(
            select(KnowledgeBookAuditLog).order_by(KnowledgeBookAuditLog.created_at.desc())
        )
        entries = result.scalars().all()
        return [
            {
                "id": entry.id,
                "patch_id": entry.patch_id,
                "action": entry.action,
                "actor_user_id": entry.actor_user_id,
                "details": entry.details,
                "created_at": entry.created_at.isoformat(),
            }
            for entry in entries
        ]

    async def get_status(self, db: AsyncSession) -> Dict[str, Any]:
        source_counts = {}
        for status_name in ["uploaded", "processing", "draft_ready", "committed", "failed"]:
            result = await db.execute(
                select(func.count(KnowledgeSource.id)).where(
                    KnowledgeSource.status == status_name
                )
            )
            source_counts[status_name] = result.scalar_one()

        patch_counts = {}
        for status_name in ["draft", "committed"]:
            result = await db.execute(
                select(func.count(KnowledgeBookPatch.id)).where(
                    KnowledgeBookPatch.status == status_name
                )
            )
            patch_counts[status_name] = result.scalar_one()

        result = await db.execute(
            select(func.count(KnowledgeBookNode.id)).where(
                KnowledgeBookNode.is_active == True  # noqa: E712
            )
        )
        active_nodes = result.scalar_one()
        processing_progress = 0
        result = await db.execute(
            select(KnowledgeBookJob.progress)
            .join(KnowledgeSource, KnowledgeBookJob.source_id == KnowledgeSource.id)
            .where(KnowledgeSource.status == "processing")
            .where(KnowledgeBookJob.status == "processing")
        )
        progress_values = [row[0] for row in result.all()]
        if progress_values:
            processing_progress = int(sum(progress_values) / len(progress_values))

        rag_healthy = False
        if rag_anything_service.is_initialized:
            rag_healthy = await rag_anything_service.health()

        return {
            "source_counts": source_counts,
            "patch_counts": patch_counts,
            "active_nodes": active_nodes,
            "processing_sources": source_counts.get("processing", 0),
            "processing_progress": processing_progress,
            "rag_initialized": rag_anything_service.is_initialized,
            "rag_healthy": rag_healthy,
            "chat_ready": rag_healthy and active_nodes > 0,
            "storage_root": str(self.storage_dir),
        }

    async def resume_pending_sources(self) -> None:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(KnowledgeSource.id).where(
                    KnowledgeSource.status.in_(["uploaded", "processing"])
                )
            )
            source_ids = [row[0] for row in result.all()]
            for source_id in source_ids:
                task = asyncio.create_task(self.process_source(source_id))
                self._track_task(task)

    async def reindex_current_book(self) -> Dict[str, Any]:
        if not rag_anything_service.is_initialized:
            return {"success": False, "error": "RAG-Anything not initialized"}

        async with AsyncSessionLocal() as db:
            tree = await self.get_tree(db)
            if not tree.get("chapters"):
                return {"success": False, "error": "No active knowledge book"}

            markdown = self._markdown_from_tree(
                {
                    "book_title": tree.get("book_title", "Knowledge Book"),
                    "chapters": [
                        {
                            "title": chapter["title"],
                            "summary": "",
                            "topics": [
                                {
                                    "title": child["title"],
                                    "summary": "",
                                    "pages": [
                                        {
                                            "title": grandchild["title"],
                                            "content_md": grandchild.get("content_md") or "",
                                        }
                                        for grandchild in child.get("children", [])
                                        if grandchild["node_type"] == "page"
                                    ],
                                }
                                for child in chapter.get("children", [])
                                if child["node_type"] == "topic"
                            ],
                        }
                        for chapter in tree["chapters"]
                    ],
                }
            )

        snapshot_path = self.drafts_dir / "current-book.md"
        snapshot_path.write_text(markdown, encoding="utf-8")

        result = await rag_anything_service.reindex_markdown(
            title=tree.get("book_title", "Knowledge Book"),
            content=markdown,
            source_name=snapshot_path.name,
        )
        return result


knowledge_book_service = KnowledgeBookService()
