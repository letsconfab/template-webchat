"""Bulk invite batch and recipient models."""

from datetime import datetime
from enum import Enum

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from backend.database import Base


class InviteBatchState(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class RecipientState(str, Enum):
    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    RETRY_WAIT = "retry_wait"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
    UNKNOWN_DELIVERY = "unknown_delivery"


class InviteBatch(Base):
    """Parent row for a CSV bulk-invite upload."""

    __tablename__ = "invite_batches"

    id = Column(Integer, primary_key=True)
    filename = Column(String(512), nullable=False)
    role = Column(String(32), nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    state = Column(String(32), nullable=False, default=InviteBatchState.QUEUED, index=True)
    total_count = Column(Integer, nullable=False, default=0)
    pending_count = Column(Integer, nullable=False, default=0)
    sent_count = Column(Integer, nullable=False, default=0)
    failed_count = Column(Integer, nullable=False, default=0)
    skipped_count = Column(Integer, nullable=False, default=0)
    cancelled_count = Column(Integer, nullable=False, default=0)
    unknown_delivery_count = Column(Integer, nullable=False, default=0)
    retry_wait_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    created_by = relationship("User", foreign_keys=[created_by_id])
    recipients = relationship(
        "BulkInviteRecipient",
        back_populates="batch",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class BulkInviteRecipient(Base):
    """One address in a bulk invite batch."""

    __tablename__ = "bulk_invite_recipients"

    id = Column(Integer, primary_key=True)
    batch_id = Column(
        Integer,
        ForeignKey("invite_batches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email = Column(String, nullable=False)
    email_canonical = Column(String, nullable=False, index=True)
    line_number = Column(Integer, nullable=False)
    invite_id = Column(Integer, ForeignKey("invites.id"), nullable=True, index=True)
    state = Column(
        String(32), nullable=False, default=RecipientState.PENDING, index=True
    )
    attempt_count = Column(Integer, nullable=False, default=0)
    lease_owner = Column(String(128), nullable=True)
    lease_expires_at = Column(DateTime, nullable=True)
    next_attempt_at = Column(DateTime, nullable=True)
    safe_error_category = Column(String(64), nullable=True)
    sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    batch = relationship("InviteBatch", back_populates="recipients")
    invite = relationship("Invite", foreign_keys=[invite_id])
