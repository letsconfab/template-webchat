"""Administrator-curated starter journeys for the chat empty state."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
)
from sqlalchemy.types import JSON

from backend.database import Base


class Journey(Base):
    """A curated ALO starter journey shown on the chat start screen."""

    __tablename__ = "journeys"

    id = Column(Integer, primary_key=True)
    title = Column(String(120), nullable=False)
    purpose = Column(String(500), nullable=False, default="")
    starter_prompt = Column(Text, nullable=False)
    icon = Column(String(64), nullable=True)
    display_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    # Human-readable Knowledge Source labels that support this journey.
    knowledge_source_labels = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
