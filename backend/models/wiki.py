"""Wiki and Knowledge models for Knowledge Book."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    JSON,
    Boolean,
)
from sqlalchemy.orm import relationship

from backend.database import Base


class WikiPage(Base):
    """Wiki page for Knowledge Book."""

    __tablename__ = "wiki_pages"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=True)  # Markdown content
    category = Column(String(100), nullable=True)
    parent_id = Column(Integer, ForeignKey("wiki_pages.id"), nullable=True)
    source_type = Column(
        String(50), nullable=False
    )  # 'document', 'quick_note', 'insight'
    source_id = Column(Integer, nullable=True)  # Reference to source document/insight
    is_draft = Column(Boolean, default=False)
    is_processed = Column(
        Boolean, default=False
    )  # False = input (raw), True = output (wiki)
    is_folder = Column(Boolean, default=False)  # True = folder, False = page
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    parent = relationship("WikiPage", remote_side=[id], backref="children")
    creator = relationship("User", foreign_keys=[created_by_id])
    versions = relationship(
        "WikiVersion", back_populates="page", cascade="all, delete-orphan"
    )


class WikiVersion(Base):
    """Version history for Wiki pages."""

    __tablename__ = "wiki_versions"

    id = Column(Integer, primary_key=True, index=True)
    page_id = Column(Integer, ForeignKey("wiki_pages.id"), nullable=False)
    content = Column(Text, nullable=False)
    diff_from_previous = Column(Text, nullable=True)  # Git-like diff
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    page = relationship("WikiPage", back_populates="versions")
    creator = relationship("User", foreign_keys=[created_by_id])


class KnowledgeInsight(Base):
    """Knowledge insights auto-detected from user chats."""

    __tablename__ = "knowledge_insights"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=True)
    content = Column(Text, nullable=False)
    source_type = Column(String(50), nullable=False)  # 'auto_detected'
    source_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    source_message_id = Column(Integer, nullable=True)
    chat_session_id = Column(String(100), nullable=True)
    status = Column(String(20), default="pending")  # pending, approved, rejected
    tags = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    reviewed_at = Column(DateTime, nullable=True)
    reviewed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Relationships
    source_user = relationship("User", foreign_keys=[source_user_id])
    reviewer = relationship("User", foreign_keys=[reviewed_by_id])


class UserFeedback(Base):
    """User feedback on chat responses."""

    __tablename__ = "user_feedback"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    rating = Column(Integer, nullable=True)  # 1-5
    feedback_type = Column(String(20), nullable=False)  # 'thumbs_up', 'thumbs_down'
    message = Column(Text, nullable=True)
    categories = Column(JSON, nullable=True)  # e.g. ['inaccurate', 'too_long']
    chat_message_id = Column(Integer, ForeignKey("chat_messages.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    chat_message = relationship("ChatMessage", foreign_keys=[chat_message_id])


class ChatMessage(Base):
    """Chat messages for feedback context."""

    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(100), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # 'user', 'assistant'
    content = Column(Text, nullable=False)
    msg_metadata = Column(JSON, nullable=True)  # Renamed to avoid reserved keyword
    created_at = Column(DateTime, default=datetime.utcnow)
