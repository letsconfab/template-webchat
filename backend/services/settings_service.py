"""Settings service for managing system configuration."""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# from database import get_db
from backend.database import get_db
from backend.models.settings import SystemSettings


class SettingsService:
    """Service for managing system settings."""
    
    @staticmethod
    async def get_settings(db: AsyncSession) -> Optional[SystemSettings]:
        """Get current system settings from database."""
        result = await db.execute(select(SystemSettings).limit(1))
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_email_config(db: AsyncSession):
        """Get email configuration from database settings."""
        settings = await SettingsService.get_settings(db)
        
        if not settings or not settings.is_configured:
            return None
            
        # Check if email configuration is complete
        if not all([
            settings.smtp_server,
            settings.smtp_port,
            settings.smtp_username,
            settings.smtp_password,
            settings.from_email
        ]):
            return None
            
        return {
            'smtp_server': settings.smtp_server,
            'smtp_port': settings.smtp_port,
            'smtp_username': settings.smtp_username,
            'smtp_password': settings.smtp_password,
            'from_email': settings.from_email,
            'use_tls': settings.use_tls if settings.use_tls is not None else True,
            'frontend_url': settings.frontend_url
        }


# Global settings service instance
settings_service = SettingsService()
