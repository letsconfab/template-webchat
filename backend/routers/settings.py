"""Settings router for configuration wizard and admin settings."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# from database import get_db
from backend.database import get_db
from backend.dependencies.auth import get_current_admin_user
from backend.models.settings import SystemSettings
from backend.models.user import User
from backend.schemas.settings import (
    SystemSettingsCreate,
    SystemSettingsResponse,
    SystemSettingsUpdate,
)
from backend.services.auth import get_password_hash

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/config-status", response_model=dict)
async def get_config_status(db: AsyncSession = Depends(get_db)):
    """Check if the system has been configured.

    Returns:
        - needs_setup: true if no settings AND no admin user exist
        - state: "partial" if settings or admin exists but not fully configured
        - is_configured: true only if both settings.is_configured AND admin exists
    """
    # Check if system settings exist and are configured
    result = await db.execute(select(SystemSettings).limit(1))
    settings = result.scalar_one_or_none()

    # Check if admin user exists
    result = await db.execute(select(User).where(User.role == "admin"))
    admin_user = result.scalar_one_or_none()

    if not settings and not admin_user:
        # Nothing exists - fresh install
        return {"is_configured": False, "needs_setup": True}

    if not settings and admin_user:
        # Admin exists but no settings - partial configuration
        return {
            "is_configured": False,
            "needs_setup": False,
            "state": "partial",
            "admin_exists": True,
            "message": "Admin account exists but system settings are incomplete.",
        }

    if settings and not admin_user:
        # Settings exist but no admin - partial configuration
        return {
            "is_configured": False,
            "needs_setup": False,
            "state": "partial",
            "settings_exists": True,
            "message": "System settings exist but no admin account found.",
        }

    # Both exist - check if fully configured
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
    """Configure the system for the first time. Creates admin user + system settings.

    Handles partial configuration:
    - If admin exists but settings don't: create settings only
    - If settings exist but admin doesn't: create admin only
    - If both exist but not fully configured: update settings
    """
    # Check current state
    result = await db.execute(select(SystemSettings).limit(1))
    existing_settings = result.scalar_one_or_none()

    result = await db.execute(select(User).where(User.role == "admin"))
    existing_admin = result.scalar_one_or_none()

    # Fully configured - reject
    if existing_settings and existing_settings.is_configured and existing_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="System is already fully configured. Use admin login to access.",
        )

    # Handle partial configurations
    if existing_admin and not existing_settings:
        # Admin exists, just create settings
        pass
    elif existing_settings and not existing_admin:
        # Settings exist, create admin
        admin_user = User(
            email=settings_data.admin_email,
            password_hash=get_password_hash(settings_data.admin_password),
            role="admin",
            is_active=True,
        )
        db.add(admin_user)
    elif existing_admin and existing_settings:
        # Both exist but not fully configured - just update settings
        pass
    else:
        # Fresh install - create both
        admin_user = User(
            email=settings_data.admin_email,
            password_hash=get_password_hash(settings_data.admin_password),
            role="admin",
            is_active=True,
        )
        db.add(admin_user)

    # Prepare settings data (admin credentials excluded by schema)
    settings_dict = settings_data.dict()

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
    if not existing_admin:
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
