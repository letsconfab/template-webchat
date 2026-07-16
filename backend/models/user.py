"""User model for authentication and authorization."""
from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import relationship, validates

# from database import Base
from backend.database import Base


class UserRole(str, Enum):
    """User roles."""
    ADMIN = "admin"
    USER = "user"


class User(Base):
    """User model for authentication."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    # Trimmed lowercase; all identity comparisons use this, not email.
    email_canonical = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, default=UserRole.USER, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    # Written only on real login. Never conflated with inferred activity.
    last_login_at = Column(DateTime, nullable=True)
    # Populated by the out-of-band activity backfill from recorded history.
    inferred_last_activity_at = Column(DateTime, nullable=True)

    # Relationships
    created_invites = relationship("Invite", foreign_keys="Invite.created_by_id", back_populates="created_by")
    chat_sessions = relationship(
        "ChatSession",
        back_populates="owner",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    feedback_cases = relationship(
        "FeedbackCase",
        back_populates="owner",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @validates("email")
    def _populate_email_canonical(self, _key, address: str) -> str:
        trimmed = address.strip()
        self.email_canonical = trimmed.lower()
        return trimmed

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, role={self.role})>"
