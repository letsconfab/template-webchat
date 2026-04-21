"""System settings model for storing application configuration."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from ..database import Base


class SystemSettings(Base):
    """System settings model for storing application configuration."""

    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)

    # Configuration status
    is_configured = Column(Boolean, default=False, nullable=False)
    configured_at = Column(DateTime, nullable=True)
    configured_by = Column(String, nullable=True)

    # Application Settings
    app_name = Column(String(255), nullable=True)
    app_description = Column(Text, nullable=True)
    company_name = Column(String(255), nullable=True)

    # Email Configuration
    smtp_server = Column(String(255), nullable=True)
    smtp_port = Column(Integer, nullable=True)
    smtp_username = Column(String(255), nullable=True)
    smtp_password = Column(String(255), nullable=True)
    from_email = Column(String(255), nullable=True)
    use_tls = Column(Boolean, default=True, nullable=False)

    # Frontend Configuration
    frontend_url = Column(String(500), nullable=True)

    # Security Settings
    session_timeout_minutes = Column(Integer, default=30, nullable=False)
    max_login_attempts = Column(Integer, default=5, nullable=False)

    # Feature Flags
    email_notifications_enabled = Column(Boolean, default=True, nullable=False)
    user_registration_enabled = Column(Boolean, default=True, nullable=False)

    # LLM Configuration (admin-controlled, shared by all users)
    llm_provider = Column(String(50), default="openai", nullable=False)
    llm_model = Column(String(100), default="gpt-4o-mini", nullable=False)
    llm_api_key = Column(String(500), nullable=True)

    # Foundry Configuration
    foundry_url = Column(String(500), nullable=True)
    foundry_confab_id = Column(Integer, nullable=True)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def __repr__(self):
        return f"<SystemSettings(id={self.id}, is_configured={self.is_configured})>"
