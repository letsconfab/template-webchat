"""Pydantic schemas for system settings."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, validator


class SystemSettingsBase(BaseModel):
    """Base system settings schema."""

    # Application Settings
    app_name: Optional[str] = Field(
        None, max_length=255, description="Application name"
    )
    app_description: Optional[str] = Field(None, description="Application description")
    company_name: Optional[str] = Field(
        None, max_length=255, description="Company name"
    )

    # Email Configuration
    smtp_server: Optional[str] = Field(
        None, max_length=255, description="SMTP server address"
    )
    smtp_port: Optional[int] = Field(None, ge=1, le=65535, description="SMTP port")
    smtp_username: Optional[str] = Field(
        None, max_length=255, description="SMTP username"
    )
    smtp_password: Optional[str] = Field(
        None, max_length=255, description="SMTP password"
    )
    from_email: Optional[EmailStr] = Field(None, description="From email address")
    use_tls: Optional[bool] = Field(True, description="Use TLS for SMTP")

    # Frontend Configuration
    frontend_url: Optional[str] = Field(
        None, max_length=500, description="Frontend URL"
    )

    # Security Settings
    session_timeout_minutes: Optional[int] = Field(
        30, ge=5, le=1440, description="Session timeout in minutes"
    )
    max_login_attempts: Optional[int] = Field(
        5, ge=1, le=20, description="Maximum login attempts"
    )

    # Feature Flags
    email_notifications_enabled: Optional[bool] = Field(
        True, description="Enable email notifications"
    )
    user_registration_enabled: Optional[bool] = Field(
        True, description="Enable user registration"
    )

    # LLM Configuration
    llm_provider: Optional[str] = Field(
        "openai", max_length=50, description="LLM provider"
    )
    llm_model: Optional[str] = Field(
        "gpt-4o-mini", max_length=100, description="LLM model"
    )
    llm_api_key: Optional[str] = Field(None, max_length=500, description="LLM API key")

    # Foundry Configuration
    foundry_url: Optional[str] = Field(
        None, max_length=500, description="Foundry instance URL"
    )
    foundry_confab_id: Optional[int] = Field(None, description="Confab ID to sync from")


class SystemSettingsCreate(SystemSettingsBase):
    """Schema for creating system settings (initial configuration)."""

    # Admin user credentials (required for first-time setup, not stored in DB)
    admin_email: EmailStr = Field(..., description="Admin user email")
    admin_password: str = Field(..., min_length=8, description="Admin user password")

    class Config:
        extra = "allow"  # Allow extra fields for flexibility

    def dict(self, **kwargs):
        # Exclude admin credentials from dict
        exclude = {"admin_email", "admin_password"}
        return super().dict(**kwargs, exclude=exclude)

    @validator("app_name")
    def validate_app_name(cls, v, values):
        if not v or v.strip() == "":
            raise ValueError("Application name is required for initial configuration")
        return v.strip()

    @validator("from_email")
    def validate_from_email(cls, v, values):
        if not v:
            raise ValueError("From email is required for initial configuration")
        return v

    @validator("smtp_server")
    def validate_smtp_server(cls, v, values):
        if not v:
            raise ValueError("SMTP server is required for initial configuration")
        return v.strip()

    @validator("smtp_port")
    def validate_smtp_port(cls, v, values):
        if not v:
            raise ValueError("SMTP port is required for initial configuration")
        return v


class SystemSettingsUpdate(SystemSettingsBase):
    """Schema for updating system settings."""

    pass


class SystemSettingsResponse(SystemSettingsBase):
    """Schema for system settings response."""

    id: int
    is_configured: bool
    configured_at: Optional[datetime] = None
    configured_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ConfigStatusResponse(BaseModel):
    """Schema for configuration status response."""

    is_configured: bool
    needs_setup: bool
    configured_at: Optional[datetime] = None
    app_name: Optional[str] = None
