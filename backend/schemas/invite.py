"""Pydantic schemas for invite-related operations."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr


class InviteCreate(BaseModel):
    """Invite creation schema."""
    role: str
    email: EmailStr


class InviteResponse(BaseModel):
    """Invite response schema."""
    id: int
    email: str
    token: str
    status: str
    role: str
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
    """Invite list response schema."""
    invites: list[InviteResponse]
    total: int
