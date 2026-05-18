"""Knowledge book models for uploaded sources, drafts, and audit history."""

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
)
from sqlalchemy.orm import relationship

from backend.database import Base


class KnowledgeSource(Base):
    """Raw uploaded source artifact."""

    __tablename__ = "knowledge_sources"

    id = Column(Integer, primary_key=True, index=True)
    original_filename = Column(String(255), nullable=False)
    title = Column(String(255), nullable=True)
    file_type = Column(String(20), nullable=False)  # pdf, docx, md
    storage_path = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=False)
    checksum = Column(String(64), nullable=False, index=True)
    source_text = Column(Text, nullable=True)
    redacted_text = Column(Text, nullable=True)
    status = Column(String(30), default="uploaded", nullable=False, index=True)
    error_message = Column(Text, nullable=True)
    uploaded_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    uploaded_by = relationship("User")
    patches = relationship(
        "KnowledgeBookPatch", back_populates="source", cascade="all, delete-orphan"
    )
    jobs = relationship(
        "KnowledgeBookJob", back_populates="source", cascade="all, delete-orphan"
    )


class KnowledgeBookPatch(Base):
    """Draft patch that can be edited before commit."""

    __tablename__ = "knowledge_book_patches"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("knowledge_sources.id"), nullable=False)
    status = Column(String(20), default="draft", nullable=False, index=True)
    draft_title = Column(String(255), nullable=False)
    draft_json = Column(JSON, nullable=False)
    draft_markdown = Column(Text, nullable=False)
    redaction_report = Column(JSON, nullable=True)
    proposed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    committed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    committed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    source = relationship("KnowledgeSource", back_populates="patches")
    proposed_by = relationship("User", foreign_keys=[proposed_by_id])
    committed_by = relationship("User", foreign_keys=[committed_by_id])
    audits = relationship(
        "KnowledgeBookAuditLog", back_populates="patch", cascade="all, delete-orphan"
    )


class KnowledgeBookAuditLog(Base):
    """Immutable audit log for patch lifecycle events."""

    __tablename__ = "knowledge_book_audit_log"

    id = Column(Integer, primary_key=True, index=True)
    patch_id = Column(Integer, ForeignKey("knowledge_book_patches.id"), nullable=False)
    action = Column(String(50), nullable=False)
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    patch = relationship("KnowledgeBookPatch", back_populates="audits")
    actor = relationship("User")


class KnowledgeBookNode(Base):
    """Active knowledge book node, constrained to three levels."""

    __tablename__ = "knowledge_book_nodes"

    id = Column(Integer, primary_key=True, index=True)
    patch_id = Column(Integer, ForeignKey("knowledge_book_patches.id"), nullable=False)
    source_id = Column(Integer, ForeignKey("knowledge_sources.id"), nullable=True)
    parent_id = Column(Integer, ForeignKey("knowledge_book_nodes.id"), nullable=True)
    level = Column(Integer, nullable=False)  # 1=chapter, 2=topic, 3=page
    node_type = Column(String(20), nullable=False)  # chapter, topic, page
    title = Column(String(255), nullable=False)
    slug = Column(String(255), nullable=False, index=True)
    content_md = Column(Text, nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    parent = relationship(
        "KnowledgeBookNode", remote_side=[id], backref="children"
    )


class KnowledgeBookJob(Base):
    """Background processing job for a source artifact."""

    __tablename__ = "knowledge_book_jobs"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("knowledge_sources.id"), nullable=False)
    job_type = Column(String(30), default="ingest", nullable=False)
    status = Column(String(30), default="pending", nullable=False, index=True)
    progress = Column(Integer, default=0, nullable=False)
    message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    source = relationship("KnowledgeSource", back_populates="jobs")
