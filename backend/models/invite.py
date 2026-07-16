"""Invite model for user invitation system."""

from datetime import datetime
from enum import Enum

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import relationship, validates

# from database import Base
from backend.database import Base


class InviteStatus(str, Enum):
    """Invite status."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class Invite(Base):
    """Invite model for user invitations."""

    __tablename__ = "invites"
    __table_args__ = (
        Index(
            "uq_invites_email_canonical_pending",
            "email_canonical",
            unique=True,
            postgresql_where=text("status = 'pending'"),
            sqlite_where=text("status = 'pending'"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, index=True, nullable=False)
    # Trimmed lowercase; comparisons and the pending unique index use this.
    email_canonical = Column(String, index=True, nullable=False)
    token = Column(String, unique=True, index=True, nullable=False)
    role = Column(String, default="user", nullable=False)  # "admin" or "user"
    status = Column(String, default=InviteStatus.PENDING, nullable=False)
    expiry_date = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Foreign Keys
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Relationships
    created_by = relationship(
        "User", foreign_keys=[created_by_id], back_populates="created_invites"
    )

    @validates("email")
    def _populate_email_canonical(self, _key, address: str) -> str:
        trimmed = address.strip()
        self.email_canonical = trimmed.lower()
        return trimmed

    def __repr__(self):
        return f"<Invite(id={self.id}, email={self.email}, status={self.status}, role={self.role})>"

    @property
    def is_expired(self) -> bool:
        """Check if invite is expired."""
        return datetime.utcnow() > self.expiry_date

    def expire(self):
        """Mark invite as expired."""
        self.status = InviteStatus.EXPIRED
        self.updated_at = datetime.utcnow()
