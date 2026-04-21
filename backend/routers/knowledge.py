"""Knowledge base management endpoints."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db
from dependencies.auth import get_current_admin_user
from models.user import User
from models.settings import SystemSettings
from services.knowledge import knowledge_service

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


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

    filename: str
    size: int
    modified: float


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
    return knowledge_service.list_documents()


@router.get("/status")
async def get_knowledge_status(db: AsyncSession = Depends(get_db)):
    """Get knowledge base status (any authenticated user)."""
    # Get system settings for LLM config
    result = await db.execute(select(SystemSettings).limit(1))
    settings = result.scalar_one_or_none()

    return {
        "document_count": knowledge_service.get_document_count(),
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

    # Update system settings with foundry info
    result_settings = await db.execute(select(SystemSettings).limit(1))
    settings = result_settings.scalar_one_or_none()

    if settings:
        settings.foundry_url = request.foundry_url
        settings.foundry_confab_id = request.confab_id
        await db.commit()

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


@router.delete("/documents/{filename}")
async def delete_document(
    filename: str, current_user: User = Depends(get_current_admin_user)
):
    """Delete a document from knowledge base (admin only)."""
    success = await knowledge_service.delete_document(filename)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{filename}' not found",
        )

    return {"message": "Document deleted successfully"}


# Import config at module level
from config import config
