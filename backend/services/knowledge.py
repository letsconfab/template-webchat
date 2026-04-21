"""Knowledge base service for managing document sync and indexing."""

import base64
import shutil
from typing import List, Optional
from pathlib import Path

from ..config import config
from ..services.foundry import FoundryService


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
        foundry = FoundryService(foundry_url, access_token)

        try:
            # Get list of documents
            documents = await foundry.get_documents(confab_id)

            kb_dir = self._get_kb_dir()
            synced_count = 0
            errors = []

            for doc in documents:
                doc_id = doc.get("id")
                filename = doc.get("filename", f"doc_{doc_id}")
                content_type = doc.get("content_type", "application/octet-stream")

                try:
                    # Get document content
                    content = await foundry.get_document_content(confab_id, doc_id)

                    # Save to KB directory
                    file_path = kb_dir / filename
                    file_path.write_bytes(content)
                    synced_count += 1

                except Exception as e:
                    errors.append(f"Failed to sync {filename}: {str(e)}")

            return {
                "synced_count": synced_count,
                "total_docs": len(documents),
                "errors": errors,
            }

        finally:
            await foundry.close()

    async def add_document(self, filename: str, content_base64: str) -> dict:
        """Add a document directly to the KB directory."""
        kb_dir = self._get_kb_dir()

        # Decode content
        content = base64.b64decode(content_base64)

        # Save file
        file_path = kb_dir / filename
        file_path.write_bytes(content)

        return {"filename": filename, "size": len(content), "path": str(file_path)}

    async def delete_document(self, filename: str) -> bool:
        """Delete a document from the KB directory."""
        kb_dir = self._get_kb_dir()
        file_path = kb_dir / filename

        if file_path.exists():
            file_path.unlink()
            return True
        return False

    def list_documents(self) -> List[dict]:
        """List all documents in the KB directory."""
        kb_dir = self._get_kb_dir()

        documents = []
        for file_path in kb_dir.iterdir():
            if file_path.is_file():
                stat = file_path.stat()
                documents.append(
                    {
                        "filename": file_path.name,
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                    }
                )

        return documents

    def get_document_count(self) -> int:
        """Get the count of documents in KB directory."""
        kb_dir = self._get_kb_dir()
        return sum(1 for f in kb_dir.iterdir() if f.is_file())


# Global knowledge service instance
knowledge_service = KnowledgeService()
