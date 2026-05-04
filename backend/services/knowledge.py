"""Knowledge base service for managing document sync and indexing."""

import base64
import shutil
from typing import List, Optional
from pathlib import Path
from datetime import datetime

# from config import config
from backend.config import config
from backend.database import AsyncSessionLocal
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession


class KnowledgeService:
    """Service for managing knowledge base operations."""

    def __init__(self):
        self.initialized = False

    def _get_kb_dir(self) -> Path:
        """Get the knowledge base directory."""
        kb_dir = config.KB_ASSETS_DIR
        kb_dir.mkdir(parents=True, exist_ok=True)
        return kb_dir

    async def sync_from_foundry(
        self, foundry_url: str, access_token: str, confab_id: int
    ) -> dict:
        """Sync documents from a Foundry confab to the local KB directory."""
        # Placeholder - Foundry sync is deprecated
        return {
            "synced_count": 0,
            "total_docs": 0,
            "errors": [
                "Foundry sync is no longer supported. Please upload documents directly."
            ],
        }

    async def add_document(
        self,
        db: AsyncSession,
        filename: str,
        content: bytes = None,
        content_base64: str = None,
        file_type: str = None,
    ) -> dict:
        """Add a document to the KB directory and database."""
        from backend.models.knowledge import KnowledgeDocument

        kb_dir = self._get_kb_dir()

        # Determine content
        if content is None and content_base64:
            content = base64.b64decode(content_base64)

        if content is None:
            raise ValueError("No content provided")

        # Generate unique filename if exists
        file_path = kb_dir / filename
        counter = 1
        while file_path.exists():
            name, ext = filename.rsplit(".", 1) if "." in filename else (filename, "")
            filename = f"{name}_{counter}.{ext}" if ext else f"{name}_{counter}"
            file_path = kb_dir / filename
            counter += 1

        # Save file
        file_path.write_bytes(content)

        # Extract text content for later chunking
        content_text = self._extract_text(
            content, file_type or filename.split(".")[-1].lower()
        )

        # Save to database
        doc = KnowledgeDocument(
            filename=filename,
            file_type=file_type or filename.split(".")[-1].lower(),
            file_path=str(file_path),
            file_size=len(content),
            content_text=content_text,
            created_at=datetime.utcnow(),
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)

        # Create chunks from text
        if content_text:
            await self._create_chunks(db, doc, content_text)

        return {
            "id": doc.id,
            "filename": doc.filename,
            "size": doc.file_size,
            "file_type": doc.file_type,
            "created_at": doc.created_at.isoformat(),
        }

    def _extract_text(self, content: bytes, file_type: str) -> str:
        """Extract text from file content based on file type."""
        try:
            if file_type == "txt" or file_type == "md":
                return content.decode("utf-8", errors="ignore")

            # For now, just return empty for PDF/DOCX - would need proper extraction libraries
            # In production, you'd use libraries like PyPDF2, python-docx
            return ""
        except Exception as e:
            print(f"Error extracting text: {e}")
            return ""

    async def _create_chunks(self, db: AsyncSession, document, content_text: str):
        """Create text chunks from document content."""
        from backend.models.knowledge import KnowledgeChunk

        if not content_text:
            return

        # Simple chunking - split by paragraphs or by max length
        chunk_size = 1000
        chunks = []

        # Split by paragraphs first
        paragraphs = content_text.split("\n\n")
        current_chunk = ""

        for para in paragraphs:
            if len(current_chunk) + len(para) < chunk_size:
                current_chunk += para + "\n\n"
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = para + "\n\n"

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        # Save chunks
        for i, chunk_content in enumerate(chunks):
            chunk = KnowledgeChunk(
                document_id=document.id, chunk_index=i, content=chunk_content
            )
            db.add(chunk)

        await db.commit()

    async def delete_document(self, db: AsyncSession, document_id: int) -> bool:
        """Delete a document from the KB directory and database."""
        from backend.models.knowledge import KnowledgeDocument

        result = await db.execute(
            select(KnowledgeDocument).where(KnowledgeDocument.id == document_id)
        )
        doc = result.scalar_one_or_none()

        if not doc:
            return False

        # Delete file
        file_path = Path(doc.file_path)
        if file_path.exists():
            file_path.unlink()

        # Delete from database (chunks are deleted via cascade)
        await db.delete(doc)
        await db.commit()

        return True

    async def list_documents(self, db: AsyncSession) -> List[dict]:
        """List all documents in the KB directory."""
        from backend.models.knowledge import KnowledgeDocument

        result = await db.execute(
            select(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc())
        )
        docs = result.scalars().all()

        return [
            {
                "id": doc.id,
                "filename": doc.filename,
                "size": doc.file_size,
                "file_type": doc.file_type,
                "created_at": doc.created_at.isoformat(),
            }
            for doc in docs
        ]

    async def get_document(self, db: AsyncSession, document_id: int) -> Optional[dict]:
        """Get a single document by ID."""
        from backend.models.knowledge import KnowledgeDocument

        result = await db.execute(
            select(KnowledgeDocument).where(KnowledgeDocument.id == document_id)
        )
        doc = result.scalar_one_or_none()

        if not doc:
            return None

        return {
            "id": doc.id,
            "filename": doc.filename,
            "file_type": doc.file_type,
            "file_path": doc.file_path,
            "file_size": doc.file_size,
            "created_at": doc.created_at.isoformat(),
        }

    async def get_document_count(self, db: AsyncSession) -> int:
        """Get the count of documents in KB directory."""
        from backend.models.knowledge import KnowledgeDocument

        result = await db.execute(select(KnowledgeDocument))
        return len(result.scalars().all())

    async def search(self, db: AsyncSession, query: str, limit: int = 5) -> List[dict]:
        """Search knowledge base for relevant content."""
        from backend.models.knowledge import KnowledgeChunk, KnowledgeDocument

        # Simple text search - find chunks containing query
        result = await db.execute(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.content.ilike(f"%{query}%"))
            .limit(limit)
        )
        chunks = result.scalars().all()

        results = []
        for chunk in chunks:
            # Get document info
            doc_result = await db.execute(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.id == chunk.document_id
                )
            )
            doc = doc_result.scalar_one_or_none()

            if doc:
                results.append(
                    {
                        "document_id": doc.id,
                        "filename": doc.filename,
                        "chunk_index": chunk.chunk_index,
                        "content": chunk.content[:200] + "..."
                        if len(chunk.content) > 200
                        else chunk.content,
                    }
                )

        return results


# Global knowledge service instance
knowledge_service = KnowledgeService()
