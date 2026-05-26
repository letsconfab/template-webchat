"""Google Drive OAuth and sync management endpoints."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import httpx
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import config
from backend.database import get_db
from backend.dependencies.auth import get_current_admin_user
from backend.models.settings import SystemSettings
from backend.models.user import User
from backend.services.drive_sync_service import drive_sync_service
from backend.services.cocoindex_manager import cocoindex_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/drive", tags=["drive"])

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


class FolderItem(BaseModel):
    id: str
    name: str


class FolderListResponse(BaseModel):
    folders: list[FolderItem]
    parent_id: Optional[str] = None


def _html_page(title: str, body: str, script: str = "") -> str:
    return f"""<!DOCTYPE html>
<html><head><title>{title}</title></head>
<body>{script}<p>{body}</p></body>
</html>"""


@router.get("/auth-url")
async def get_auth_url(
    current_user: User = Depends(get_current_admin_user),
):
    """Get the Google OAuth authorization URL."""
    if not config.GOOGLE_OAUTH_CLIENT_ID or not config.GOOGLE_OAUTH_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google OAuth is not configured.",
        )

    params = {
        "client_id": config.GOOGLE_OAUTH_CLIENT_ID,
        "redirect_uri": config.GOOGLE_OAUTH_REDIRECT_URI,
        "scope": " ".join(DRIVE_SCOPES),
        "response_type": "code",
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
    }
    import urllib.parse
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
    return {"url": url}


@router.get("/callback", response_class=HTMLResponse)
async def oauth_callback(
    request: Request,
    code: Optional[str] = None,
    error: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Handle the OAuth callback from Google."""
    logger.info("OAuth callback received: code=%s error=%s", "present" if code else None, error)

    if error:
        return _html_page("Error", f"Google OAuth error: {error}")

    if not code:
        return _html_page("Error", "Missing authorization code.")

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": config.GOOGLE_OAUTH_CLIENT_ID,
                    "client_secret": config.GOOGLE_OAUTH_CLIENT_SECRET,
                    "redirect_uri": config.GOOGLE_OAUTH_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
                timeout=15,
            )
            logger.info("Token endpoint status: %s", resp.status_code)
            if resp.status_code != 200:
                return _html_page("Error", f"Token exchange failed (HTTP {resp.status_code}): {resp.text}")

            token_data = resp.json()
            refresh_token = token_data.get("refresh_token")
            if not refresh_token:
                return _html_page("Error", "No refresh_token returned. Ensure access_type=offline and prompt=consent.")

        result = await db.execute(select(SystemSettings).limit(1))
        settings = result.scalar_one_or_none()

        if not settings:
            settings = SystemSettings()
            db.add(settings)

        settings.google_drive_refresh_token = refresh_token
        settings.google_drive_enabled = True
        settings.updated_at = datetime.utcnow()
        await db.commit()
        logger.info("Google Drive refresh token stored successfully")

        await drive_sync_service.start(refresh_token)

        return _html_page(
            "Connected",
            "Google Drive connected successfully.",
            script="""<script>
window.opener.postMessage({type: 'drive-connected', success: true}, '*');
window.close();
</script>""",
        )

    except Exception as e:
        logger.error("OAuth callback error: %s", e, exc_info=True)
        return _html_page("Error", f"OAuth callback failed: {str(e)}")


def _drive_service(refresh_token: str):
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=config.GOOGLE_OAUTH_CLIENT_ID,
        client_secret=config.GOOGLE_OAUTH_CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=DRIVE_SCOPES,
    )
    from google.auth.transport.requests import Request as GoogleRequest
    if creds.expired and creds.refresh_token:
        creds.refresh(GoogleRequest())
    return build("drive", "v3", credentials=creds, cache_discovery=False)


@router.get("/folders", response_model=FolderListResponse)
async def list_drive_folders(
    parent_id: Optional[str] = None,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """List Drive folders in a given parent (or root)."""
    result = await db.execute(select(SystemSettings).limit(1))
    settings = result.scalar_one_or_none()
    if not settings or not settings.google_drive_refresh_token:
        raise HTTPException(status_code=400, detail="Google Drive not connected")

    try:
        service = _drive_service(settings.google_drive_refresh_token)
        query = (
            f"'{parent_id or 'root'}' in parents "
            f"and trashed = false "
            f"and mimeType = 'application/vnd.google-apps.folder'"
        )
        response = service.files().list(
            q=query,
            spaces="drive",
            fields="files(id, name)",
            pageSize=100,
        ).execute()
        folders = [FolderItem(id=f["id"], name=f["name"]) for f in response.get("files", [])]
        return FolderListResponse(folders=folders, parent_id=parent_id)
    except Exception as e:
        logger.error("Failed to list folders: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_drive_status(
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the current sync status."""
    result = await db.execute(select(SystemSettings).limit(1))
    settings = result.scalar_one_or_none()

    sync_status = drive_sync_service.get_status()
    synced_files = drive_sync_service.get_synced_files()

    return {
        "connected": bool(settings and settings.google_drive_refresh_token),
        "root_folder_id": settings.google_drive_root_folder_id if settings else None,
        "sync": sync_status,
        "files": synced_files,
        "pipeline": cocoindex_manager.get_status(),
    }


@router.post("/sync-now")
async def sync_now(
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger an immediate sync."""
    result = await db.execute(select(SystemSettings).limit(1))
    settings = result.scalar_one_or_none()

    if not settings or not settings.google_drive_refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google Drive not connected",
        )

    refresh_token = settings.google_drive_refresh_token
    root_folder_id = settings.google_drive_root_folder_id or "root"

    result = await drive_sync_service.sync_once(refresh_token, root_folder_id)
    return result


@router.patch("/root-folder")
async def set_root_folder(
    folder_id: str,
    folder_name: Optional[str] = None,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Set the root Drive folder to sync."""
    result = await db.execute(select(SystemSettings).limit(1))
    settings = result.scalar_one_or_none()
    if not settings:
        raise HTTPException(status_code=404, detail="Settings not found")

    settings.google_drive_root_folder_id = folder_id
    settings.updated_at = datetime.utcnow()
    await db.commit()

    logger.info("Drive root folder set to %s (%s)", folder_id, folder_name or "?")

    # Trigger a sync immediately
    if settings.google_drive_refresh_token:
        await drive_sync_service.sync_once(settings.google_drive_refresh_token, folder_id)

    return {"status": "ok", "root_folder_id": folder_id}


@router.post("/disconnect")
async def disconnect_drive(
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Disconnect Google Drive and stop sync."""
    await drive_sync_service.stop()
    await cocoindex_manager.stop()

    result = await db.execute(select(SystemSettings).limit(1))
    settings = result.scalar_one_or_none()
    if settings:
        settings.google_drive_refresh_token = None
        settings.google_drive_enabled = False
        settings.google_drive_last_synced = None
        settings.updated_at = datetime.utcnow()
        await db.commit()

    return {"status": "disconnected"}
