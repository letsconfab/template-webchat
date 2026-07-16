"""Pydantic schemas for bulk invite batches."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class BulkInviteInvalidRow(BaseModel):
    line_number: int
    raw: str
    reason: str


class BulkInvitePreviewResponse(BaseModel):
    filename: str
    role: str
    total_rows: int
    will_invite: int
    already_registered: int
    pending_invite: int
    invalid: int
    duplicate_rows: int
    invalid_rows: list[BulkInviteInvalidRow] = Field(default_factory=list)
    sample_will_invite: list[str] = Field(default_factory=list)


class BulkInviteConfirmResponse(BaseModel):
    batch_id: int
    state: str
    total_count: int
    pending_count: int
    skipped_count: int


class BulkInviteRecipientResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    email_canonical: str
    line_number: int
    state: str
    attempt_count: int
    invite_id: Optional[int] = None
    safe_error_category: Optional[str] = None
    sent_at: Optional[datetime] = None


class BulkInviteBatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    role: str
    created_by_id: int
    state: str
    total_count: int
    pending_count: int
    sent_count: int
    failed_count: int
    skipped_count: int
    cancelled_count: int
    unknown_delivery_count: int
    retry_wait_count: int
    created_at: datetime
    updated_at: datetime
    recipients: list[BulkInviteRecipientResponse] = Field(default_factory=list)
    cancel_note: Optional[str] = None
