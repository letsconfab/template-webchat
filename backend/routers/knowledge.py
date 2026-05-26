"""Knowledge book ingestion and review endpoints."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.dependencies.auth import (
    get_current_active_user,
    get_current_admin_user,
)
from backend.models.user import User
from backend.services.knowledge_book_service import knowledge_book_service

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


class NoteCreateRequest(BaseModel):
    title: str = "Quick Note"
    content: str


class PatchUpdateRequest(BaseModel):
    draft_json: Dict[str, Any]
    draft_markdown: str


@router.get("/status")
async def get_knowledge_status(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get knowledge book and ingestion status."""
    return await knowledge_book_service.get_status(db)


@router.get("/sources")
async def list_sources(
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """List uploaded source artifacts."""
    return {"sources": await knowledge_book_service.list_sources(db)}


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_source(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload PDF, DOCX, or Markdown source material."""
    try:
        return await knowledge_book_service.create_source_from_upload(
            db=db, file=file, current_user=current_user
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/note", status_code=status.HTTP_201_CREATED)
async def create_note_source(
    request: NoteCreateRequest,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a markdown note source that enters the same draft pipeline."""
    return await knowledge_book_service.create_source_from_note(
        db=db,
        title=request.title,
        content=request.content,
        current_user=current_user,
    )


@router.delete("/sources/{source_id}")
async def delete_source(
    source_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an uncommitted source and its draft artifacts."""
    try:
        return await knowledge_book_service.delete_source(
            db=db,
            source_id=source_id,
            current_user=current_user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/patches")
async def list_patches(
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """List all draft and committed patches."""
    return {"patches": await knowledge_book_service.list_patches(db)}


@router.get("/patches/{patch_id}")
async def get_patch(
    patch_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch a single draft patch."""
    patch = await knowledge_book_service.get_patch(db, patch_id)
    if not patch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patch not found")
    return patch


@router.put("/patches/{patch_id}")
async def update_patch(
    patch_id: int,
    request: PatchUpdateRequest,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Edit a draft patch before commit."""
    try:
        return await knowledge_book_service.update_patch(
            db=db,
            patch_id=patch_id,
            draft_json=request.draft_json,
            draft_markdown=request.draft_markdown,
            current_user=current_user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/patches/{patch_id}/commit")
async def commit_patch(
    patch_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Commit a draft patch to the active knowledge book."""
    try:
        return await knowledge_book_service.commit_patch(
            db=db, patch_id=patch_id, current_user=current_user
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/tree")
async def get_tree(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the current active knowledge book tree."""
    return await knowledge_book_service.get_tree(db)


@router.get("/audit")
async def get_audit(
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Get patch audit history."""
    return {"audit": await knowledge_book_service.get_audit(db)}


@router.post("/reindex")
async def reindex_book(
    current_user: User = Depends(get_current_admin_user),
):
    """Rebuild the external RAG service index from the committed knowledge book."""
    return await knowledge_book_service.reindex_current_book()


@router.post("/hard-reset")
async def hard_reset_knowledge_book(
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Hard reset: delete all sources, patches, and published nodes."""
    try:
        return await knowledge_book_service.hard_reset(db, current_user)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.delete("/tree/{node_id}")
async def delete_published_node(
    node_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a published node from the active knowledge book."""
    try:
        return await knowledge_book_service.delete_published_node(
            db=db,
            node_id=node_id,
            current_user=current_user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
