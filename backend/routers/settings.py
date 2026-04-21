"""Settings router for configuration wizard and admin settings."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..dependencies.auth import get_current_admin_user
from ..models.settings import SystemSettings
from ..models.user import User
from ..schemas.settings import (
    SystemSettingsCreate,
    SystemSettingsResponse,
    SystemSettingsUpdate,
)
from ..services.auth import get_password_hash

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/config-status", response_model=dict)
async def get_config_status(db: AsyncSession = Depends(get_db)):
    """Check if the system has been configured."""
    result = await db.execute(select(SystemSettings).limit(1))
    settings = result.scalar_one_or_none()

    if not settings:
        return {"is_configured": False, "needs_setup": True}

    return {
        "is_configured": settings.is_configured,
        "needs_setup": not settings.is_configured,
        "configured_at": settings.configured_at,
        "app_name": settings.app_name,
    }


@router.post("/configure", response_model=SystemSettingsResponse)
async def configure_system(
    settings_data: SystemSettingsCreate, db: AsyncSession = Depends(get_db)
):
    """Configure the system for the first time. Creates admin user + system settings."""
    # Check if already configured
    result = await db.execute(select(SystemSettings).limit(1))
    existing_settings = result.scalar_one_or_none()

    if existing_settings and existing_settings.is_configured:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="System is already configured. Use admin settings to update configuration.",
        )

    # Check if admin user already exists (prevent duplicate)
    result = await db.execute(select(User).where(User.role == "admin"))
    existing_admin = result.scalar_one_or_none()

    if existing_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin user already exists. System is already configured.",
        )

    # Create admin user
    admin_user = User(
        email=settings_data.admin_email,
        password_hash=get_password_hash(settings_data.admin_password),
        role="admin",
        is_active=True,
    )
    db.add(admin_user)

    # Prepare settings data (exclude admin credentials)
    settings_dict = settings_data.dict(exclude={"admin_email", "admin_password"})

    # Create or update settings
    if existing_settings:
        settings = existing_settings
        for field, value in settings_dict.items():
            setattr(settings, field, value)
    else:
        settings = SystemSettings(**settings_dict)
        db.add(settings)

    # Mark as configured
    settings.is_configured = True
    settings.configured_at = datetime.utcnow()
    settings.configured_by = settings_data.admin_email

    await db.commit()
    await db.refresh(settings)
    await db.refresh(admin_user)

    return settings


@router.get("/current", response_model=SystemSettingsResponse)
async def get_current_settings(
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current system settings (admin only)."""
    result = await db.execute(select(SystemSettings).limit(1))
    settings = result.scalar_one_or_none()

    if not settings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="System settings not found. Please configure the system first.",
        )

    return settings


@router.put("/current", response_model=SystemSettingsResponse)
async def update_settings(
    settings_update: SystemSettingsUpdate,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Update system settings (admin only)."""
    result = await db.execute(select(SystemSettings).limit(1))
    settings = result.scalar_one_or_none()

    if not settings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="System settings not found. Please configure the system first.",
        )

    # Update fields
    update_data = settings_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(settings, field, value)

    settings.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(settings)

    return settings


@router.post("/reset-configuration")
async def reset_configuration(
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Reset system configuration (admin only - allows reconfiguration)."""
    result = await db.execute(select(SystemSettings).limit(1))
    settings = result.scalar_one_or_none()

    if not settings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="System settings not found."
        )

    settings.is_configured = False
    settings.configured_at = None
    settings.configured_by = None
    settings.updated_at = datetime.utcnow()

    await db.commit()

    return {
        "message": "System configuration reset. You can now reconfigure the system."
    }
