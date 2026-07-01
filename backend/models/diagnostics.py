"""Privacy-safe administrative projections and execution diagnostics."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from backend.database import Base


class AdminProjection(Base):
    """A cached, versioned, fail-closed view of one raw text field."""

    __tablename__ = "admin_projections"
    __table_args__ = (
        UniqueConstraint(
            "content_type",
            "content_id",
            "source_field",
            "version",
            name="uq_admin_projection_source_version",
        ),
    )

    id = Column(Integer, primary_key=True)
    content_type = Column(String(40), nullable=False, index=True)
    content_id = Column(Integer, nullable=False, index=True)
    source_field = Column(String(40), nullable=False)
    version = Column(Integer, nullable=False)
    status = Column(String(16), nullable=False)
    redacted_text = Column(Text, nullable=True)
    safe_error_category = Column(String(40), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class ExecutionTrace(Base):
    """A bounded operational trace for one assistant message."""

    __tablename__ = "execution_traces"

    id = Column(Integer, primary_key=True)
    chat_message_id = Column(
        Integer,
        ForeignKey("chat_messages.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    version = Column(Integer, nullable=False)
    status = Column(String(16), nullable=False)
    events = Column(JSON, nullable=False)
    event_count = Column(Integer, nullable=False)
    byte_size = Column(Integer, nullable=False)
    truncated = Column(Boolean, nullable=False, default=False)
    safe_error_category = Column(String(40), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    chat_message = relationship("ChatMessage", back_populates="execution_trace")

