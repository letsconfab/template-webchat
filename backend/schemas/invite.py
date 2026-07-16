"""Pydantic schemas for invite-related operations."""

from datetime import datetime

from pydantic import BaseModel, EmailStr

from backend.models.user import UserRole


class InviteCreate(BaseModel):
    """Invite creation schema."""

    email: EmailStr
    role: UserRole = UserRole.USER


class InviteResponse(BaseModel):
    """Invite response schema."""

    id: int
    email: str
    token: str
    role: str
    status: str
    expiry_date: datetime
    created_at: datetime
    created_by_id: int

    class Config:
        from_attributes = True


class InviteAccept(BaseModel):
    """Invite acceptance schema."""

    token: str
    password: str


class InviteStatusUpdate(BaseModel):
    """Invite status update schema."""

    status: str


class InviteListResponse(BaseModel):
    """Paginated invite list envelope (same shape as user list).

    ``total`` is a real COUNT(*) over the same status predicate as the page.
    ``accepted`` / ``pending`` are unfiltered status counts (after the expiry
    reaper), so dashboard tiles stay correct beyond a single page.
    """

    items: list[InviteResponse]
    total: int
    skip: int
    limit: int
    accepted: int = 0
    pending: int = 0
