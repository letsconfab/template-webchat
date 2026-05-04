"""Knowledge base management endpoints."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# from database import get_db
from backend.database import get_db
from backend.dependencies.auth import get_current_admin_user
from backend.models.user import User
from backend.models.settings import SystemSettings
from backend.services.knowledge import knowledge_service
from backend.config import config

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".md", ".txt"}


class SyncFromFoundryRequest(BaseModel):
    """Request to sync from Foundry."""

    foundry_url: str
    access_token: str
    confab_id: int


class AddDocumentRequest(BaseModel):
    """Request to add a document."""

    filename: str
    content_base64: str


class DocumentResponse(BaseModel):
    """Document response."""

    id: int
    filename: str
    size: int
    file_type: str
    created_at: str


class SyncResponse(BaseModel):
    """Sync response."""

    synced_count: int
    total_docs: int
    errors: List[str]


@router.get("/documents", response_model=List[DocumentResponse])
async def list_documents(
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """List all documents in knowledge base (admin only)."""
    return await knowledge_service.list_documents(db)


@router.get("/status")
async def get_knowledge_status(db: AsyncSession = Depends(get_db)):
    """Get knowledge base status (any authenticated user)."""
    # Get system settings for LLM config
    result = await db.execute(select(SystemSettings).limit(1))
    settings = result.scalar_one_or_none()

    doc_count = await knowledge_service.get_document_count(db)

    return {
        "document_count": doc_count,
        "kb_directory": str(config.KB_ASSETS_DIR),
        "llm_provider": settings.llm_provider if settings else None,
        "llm_model": settings.llm_model if settings else None,
    }


@router.post("/sync-foundry", response_model=SyncResponse)
async def sync_from_foundry(
    request: SyncFromFoundryRequest,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Sync documents from Foundry confab (admin only)."""
    result = await knowledge_service.sync_from_foundry(
        foundry_url=request.foundry_url,
        access_token=request.access_token,
        confab_id=request.confab_id,
    )

    return result


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a document to knowledge base (admin only).

    Supported file types: PDF, DOCX, MD, TXT
    """
    # Check file extension
    file_ext = (
        "." + file.filename.split(".")[-1].lower() if "." in file.filename else ""
    )
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # Read file content
    content = await file.read()

    # Add document
    result = await knowledge_service.add_document(
        db=db,
        filename=file.filename,
        content=content,
        file_type=file_ext[1:],  # Remove the dot
    )

    return result


@router.post("/documents", status_code=status.HTTP_201_CREATED)
async def add_document(
    request: AddDocumentRequest, current_user: User = Depends(get_current_admin_user)
):
    """Add a document to knowledge base (admin only)."""
    result = await knowledge_service.add_document(
        filename=request.filename, content_base64=request.content_base64
    )
    return result


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a document and its chunks from knowledge base (admin only)."""
    success = await knowledge_service.delete_document(db, document_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with id {document_id} not found",
        )

    return {"message": "Document deleted successfully"}


@router.get("/documents/{document_id}/download")
async def download_document(
    document_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Download a document from knowledge base (admin only)."""
    from fastapi.responses import FileResponse
    from pathlib import Path

    doc = await knowledge_service.get_document(db, document_id)

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with id {document_id} not found",
        )

    file_path = Path(doc["file_path"])
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found on disk",
        )

    return FileResponse(
        path=file_path, filename=doc["filename"], media_type="application/octet-stream"
    )


@router.post("/search")
async def search_knowledge_base(
    query: str,
    limit: int = 5,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Search the knowledge base for relevant documents."""
    results = await knowledge_service.search(db, query, limit)
    return {"results": results}
