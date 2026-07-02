"""Durable tester Feedback Cases."""

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


class FeedbackCase(Base):
    """A durable negative rating tied to its owned conversation."""

    __tablename__ = "feedback_cases"
    __table_args__ = (
        UniqueConstraint(
            "public_id",
            name="uq_feedback_cases_public_id",
        ),
        Index(
            "ix_feedback_cases_public_id",
            "public_id",
            unique=True,
        ),
    )

    id = Column(Integer, primary_key=True)
    public_id = Column(String(36), nullable=False)
    feedback_id = Column(
        Integer,
        ForeignKey("user_feedback.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chat_session_id = Column(
        Integer,
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rated_message_id = Column(
        Integer,
        ForeignKey("chat_messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status = Column(String(24), nullable=False, default="awaiting_admin")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    feedback = relationship("UserFeedback", back_populates="case")
    owner = relationship("User", back_populates="feedback_cases")
    chat_session = relationship("ChatSession")
    rated_message = relationship("ChatMessage")
    replies = relationship(
        "CaseReply",
        back_populates="case",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="CaseReply.id",
    )


class CaseReply(Base):
    """An immutable reply with the author's role captured at creation."""

    __tablename__ = "case_replies"

    id = Column(Integer, primary_key=True)
    case_id = Column(
        Integer,
        ForeignKey("feedback_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    author_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    author_role = Column(String(16), nullable=False)
    raw_text = Column(String(4000), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    case = relationship("FeedbackCase", back_populates="replies")
    author = relationship("User")
    notification = relationship(
        "CaseNotification",
        back_populates="reply",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class CaseNotification(Base):
    """Durable outbound notification for one committed admin reply."""

    __tablename__ = "case_notifications"

    id = Column(Integer, primary_key=True)
    case_reply_id = Column(
        Integer,
        ForeignKey("case_replies.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    recipient_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    state = Column(String(16), nullable=False, default="pending")
    attempt_count = Column(Integer, nullable=False, default=0)
    safe_error_category = Column(String(40), nullable=True)
    last_attempt_at = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    reply = relationship("CaseReply", back_populates="notification")
    recipient = relationship("User")
