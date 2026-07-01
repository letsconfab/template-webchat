"""Durable tester Feedback Cases."""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from backend.database import Base


class FeedbackCase(Base):
    """A durable negative rating tied to its owned conversation."""

    __tablename__ = "feedback_cases"

    id = Column(Integer, primary_key=True)
    public_id = Column(String(36), nullable=False, unique=True, index=True)
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

