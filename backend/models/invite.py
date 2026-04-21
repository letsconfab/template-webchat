"""Invite model for user invitation system."""
from datetime import datetime, timedelta
from typing import Optional
from enum import Enum

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from database import Base


class InviteStatus(str, Enum):
    """Invite status."""
    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class UserRole(str, Enum):
    """User roles."""
    ADMIN = "admin"
    GENERAL = "general"


class Invite(Base):
    """Invite model for user invitations."""
    
    __tablename__ = "invites"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, index=True, nullable=False)
    token = Column(String, unique=True, index=True, nullable=False)
    status = Column(String, default=InviteStatus.PENDING, nullable=False)
    role = Column(String, default=UserRole.GENERAL, nullable=False)
    expiry_date = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Foreign Keys
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Relationships
    created_by = relationship("User", foreign_keys=[created_by_id], back_populates="created_invites")
    
    def __repr__(self):
        return f"<Invite(id={self.id}, email={self.email}, status={self.status})>"
    
    @property
    def is_expired(self) -> bool:
        """Check if invite is expired."""
        return datetime.utcnow() > self.expiry_date
    
    def expire(self):
        """Mark invite as expired."""
        self.status = InviteStatus.EXPIRED
        self.updated_at = datetime.utcnow()
