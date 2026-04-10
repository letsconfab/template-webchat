"""User model for authentication and authorization."""
from datetime import datetime
from typing import Optional
from enum import Enum

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import relationship

from ..database import Base


class UserRole(str, Enum):
    """User roles."""
    ADMIN = "admin"
    USER = "user"


class User(Base):
    """User model for authentication."""
    
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, default=UserRole.USER, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    created_invites = relationship("Invite", foreign_keys="Invite.created_by_id", back_populates="created_by")
    
    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, role={self.role})>"
