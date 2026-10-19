"""Member-facing Resource Library, grouped by INTEGRATE System.

Documents come only from ``backend.services.library`` (the synced Library
Manifest). System listings show browsable documents; ``/file`` serves both
Library and Reference Documents because Librarian citations link to both.
"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from backend.dependencies.auth import get_current_active_user
from backend.models.user import User
from backend.services import library

router = APIRouter(prefix="/api/library", tags=["library"])


def _summary(doc: dict) -> dict:
    return {
        "id": doc.get("file_id"),
        "title": doc.get("title"),
        "organization": doc.get("organization"),
        "type": doc.get("type"),
        "systems": list(doc.get("systems") or []),
        "modified_time": doc.get("modified_time"),
    }


@router.get("/systems")
async def list_systems(current_user: User = Depends(get_current_active_user)):
    """All nine INTEGRATE Systems in canonical order, with document counts."""
    return [
        {
            "slug": slug,
            "name": name,
            "document_count": len(library.documents_for_system(slug)),
        }
        for slug, name in library.SYSTEMS
    ]


@router.get("/systems/{slug}")
async def get_system(slug: str, current_user: User = Depends(get_current_active_user)):
    """Browsable documents spotlighting one System, sorted by title."""
    name = library.SYSTEM_NAMES.get(slug)
    if not name:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown INTEGRATE System")
    return {
        "slug": slug,
        "name": name,
        "documents": [_summary(doc) for doc in library.documents_for_system(slug)],
    }


@router.get("/documents/{file_id}/file")
async def get_document_file(file_id: str, current_user: User = Depends(get_current_active_user)):
    """Stream a Library or Reference Document's served PDF, looked up by id."""
    doc = library.get_document(file_id)
    path = library.served_pdf_path(doc) if doc else None
    if not path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return FileResponse(
        path,
        media_type="application/pdf",
        headers={"Content-Disposition": _inline_disposition(f"{doc.get('title') or file_id}.pdf")},
    )


def _inline_disposition(filename: str) -> str:
    ascii_name = "".join(
        c if 32 <= ord(c) < 127 and c not in '"\\' else "_" for c in filename
    )
    header = f'inline; filename="{ascii_name}"'
    if ascii_name != filename:
        header += f"; filename*=UTF-8''{quote(filename)}"
    return header
