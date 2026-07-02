"""Owned Chat Session persistence."""

from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from backend.database import Base


class ChatSession(Base):
    """An authenticated user's durable conversation."""

    __tablename__ = "chat_sessions"
    __table_args__ = (
        UniqueConstraint(
            "client_uuid",
            name="uq_chat_sessions_client_uuid",
        ),
        Index(
            "ix_chat_sessions_client_uuid",
            "client_uuid",
            unique=True,
        ),
    )

    id = Column(Integer, primary_key=True)
    client_uuid = Column(String(36), nullable=False)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    ownership_state = Column(String(20), nullable=False, default="owned")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    owner = relationship("User", back_populates="chat_sessions")
    messages = relationship(
        "ChatMessage",
        back_populates="chat_session",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
