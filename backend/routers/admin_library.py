"""Administrator view of the synced Resource Library and its manifest issues."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.dependencies.auth import get_current_admin_user
from backend.models.user import User
from backend.services import library

router = APIRouter(prefix="/api/admin/library", tags=["admin-library"])


@router.get("")
async def get_admin_library(current_user: User = Depends(get_current_admin_user)):
    """Documents with their Systems and status, plus every manifest issue."""
    return library.admin_view()
