"""Google Drive OAuth sync service — polls Drive API and caches files locally."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError

from backend.config import config

logger = logging.getLogger(__name__)

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# MIME types that can be exported as text
EXPORTABLE_MIMES = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.slides": "text/plain",
}

# File extensions by mime type
MIME_EXTENSIONS = {
    "text/plain": ".txt",
    "text/csv": ".csv",
    "application/pdf": ".pdf",
    "text/markdown": ".md",
    "text/html": ".html",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}


class DriveSyncService:
    """Sync files from a Google Drive folder to a local cache directory."""

    def __init__(self) -> None:
        self.cache_dir = Path(config.KB_CACHE_DIR) / "drive"
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self.last_sync: Optional[datetime] = None
        self.file_count: int = 0
        self.error: Optional[str] = None
        self._sync_in_progress = False

    @property
    def is_running(self) -> bool:
        return self._running

    def _build_credentials(self, refresh_token: str) -> Credentials:
        return Credentials(
            token=None,
            refresh_token=refresh_token,
            client_id=config.GOOGLE_OAUTH_CLIENT_ID,
            client_secret=config.GOOGLE_OAUTH_CLIENT_SECRET,
            token_uri="https://oauth2.googleapis.com/token",
            scopes=DRIVE_SCOPES,
        )

    async def start(self, refresh_token: str) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._running = True
        self._task = asyncio.create_task(self._sync_loop(refresh_token))
        logger.info("DriveSyncService started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("DriveSyncService stopped")

    async def sync_once(self, refresh_token: str, root_folder_id: str) -> dict:
        credentials = self._build_credentials(refresh_token)
        return await self._sync_all(credentials, root_folder_id)

    async def _sync_loop(self, refresh_token: str) -> None:
        while self._running:
            try:
                credentials = self._build_credentials(refresh_token)
                await self._sync_all(credentials, None)
                self.last_sync = datetime.utcnow()
                self.error = None
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.error = str(e)
                logger.error("Drive sync error: %s", e)
            await asyncio.sleep(60)

    async def _sync_all(
        self, credentials: Credentials, root_folder_id: Optional[str]
    ) -> dict:
        if self._sync_in_progress:
            return {"status": "already_syncing"}
        self._sync_in_progress = True
        try:
            # Refresh token if expired
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(GoogleRequest())

            service = build("drive", "v3", credentials=credentials, cache_discovery=False)

            # Get root folder ID from settings if not provided
            folder_id = root_folder_id
            if not folder_id:
                from backend.database import AsyncSessionLocal
                from sqlalchemy import select
                from backend.models.settings import SystemSettings
                async with AsyncSessionLocal() as db:
                    result = await db.execute(select(SystemSettings).limit(1))
                    settings = result.scalar_one_or_none()
                    if settings and settings.google_drive_root_folder_id:
                        folder_id = settings.google_drive_root_folder_id
                    else:
                        return {"status": "no_folder_configured"}

            files = await self._list_all_files(service, folder_id)
            drive_ids = set()

            for f in files:
                drive_ids.add(f["id"])
                local_path = self._local_path(f)
                local_path.parent.mkdir(parents=True, exist_ok=True)

                if await self._is_changed(f, local_path):
                    await self._download_file(service, f["id"], f["mimeType"], local_path, file_info=f)
                    logger.info("Downloaded: %s -> %s", f["name"], local_path)

            # Remove local files no longer in Drive
            await self._remove_stale(drive_ids)

            self.file_count = len(files)
            return {"status": "ok", "file_count": len(files)}
        finally:
            self._sync_in_progress = False

    async def _list_all_files(
        self, service, folder_id: str
    ) -> list[dict]:
        """Recursively list all files in a Drive folder (non-trash, not Google Apps folders)."""
        all_files = []
        query = (
            f"'{folder_id}' in parents "
            f"and trashed = false "
            f"and mimeType != 'application/vnd.google-apps.folder'"
        )

        page_token = None
        while True:
            request = service.files().list(
                q=query,
                spaces="drive",
                fields="nextPageToken, files(id, name, mimeType, md5Checksum, modifiedTime, size)",
                pageToken=page_token,
                pageSize=200,
            )
            response = request.execute()
            for f in response.get("files", []):
                all_files.append(f)

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return all_files

    def _local_path(self, file_info: dict) -> Path:
        ext = MIME_EXTENSIONS.get(file_info["mimeType"], "")
        if file_info["mimeType"] in EXPORTABLE_MIMES:
            target_mime = EXPORTABLE_MIMES[file_info["mimeType"]]
            ext = MIME_EXTENSIONS.get(target_mime, ".txt")
        if not ext:
            ext = Path(file_info["name"]).suffix or ".bin"
        safe_name = file_info["name"].replace("/", "_").replace("\\", "_")
        if not Path(safe_name).suffix:
            safe_name += ext
        return self.cache_dir / f"{file_info['id']}_{safe_name}"

    def _meta_path(self, local_path: Path) -> Path:
        return local_path.parent / f".{local_path.name}.meta.json"

    async def _is_changed(self, file_info: dict, local_path: Path) -> bool:
        if not local_path.exists():
            return True
        if local_path.stat().st_size == 0:
            return True
        meta_path = self._meta_path(local_path)
        if not meta_path.exists():
            return True
        try:
            meta = json.loads(meta_path.read_text())
            remote_modified = file_info.get("modifiedTime", "")
            if remote_modified and remote_modified != meta.get("modifiedTime"):
                return True
            remote_md5 = file_info.get("md5Checksum")
            if remote_md5 and remote_md5 != meta.get("md5Checksum"):
                return True
        except (json.JSONDecodeError, OSError):
            return True
        return False

    async def _download_file(
        self, service, file_id: str, mime_type: str, local_path: Path,
        file_info: Optional[dict] = None,
    ) -> None:
        try:
            if mime_type in EXPORTABLE_MIMES:
                target_mime = EXPORTABLE_MIMES[mime_type]
                request = service.files().export_media(fileId=file_id, mimeType=target_mime)
            else:
                request = service.files().get_media(fileId=file_id)

            import io
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()

            fh.seek(0)
            local_path.write_bytes(fh.getvalue())

            if file_info:
                meta = {
                    "modifiedTime": file_info.get("modifiedTime"),
                    "md5Checksum": file_info.get("md5Checksum"),
                }
                self._meta_path(local_path).write_text(json.dumps(meta))
        except HttpError as e:
            logger.error("Failed to download %s: %s", file_id, e)

    async def _remove_stale(self, active_drive_ids: set[str]) -> None:
        if not self.cache_dir.exists():
            return
        for child in self.cache_dir.iterdir():
            if child.is_file() and child.name.endswith(".meta.json"):
                continue
            if child.is_file():
                file_id = child.name.split("_", 1)[0]
                if file_id not in active_drive_ids:
                    meta = self._meta_path(child)
                    if meta.exists():
                        meta.unlink()
                    child.unlink()
                    logger.info("Removed stale: %s", child.name)

    def get_status(self) -> dict:
        return {
            "running": self._sync_in_progress,
            "last_sync": self.last_sync.isoformat() if self.last_sync else None,
            "file_count": self.file_count,
            "error": self.error,
            "cache_dir": str(self.cache_dir),
        }

    def get_synced_files(self) -> list[dict]:
        if not self.cache_dir.exists():
            return []
        files = []
        for child in sorted(self.cache_dir.iterdir()):
            if child.is_file() and not child.name.endswith(".meta.json"):
                stat = child.stat()
                files.append({
                    "filename": child.name,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })
        return files


drive_sync_service = DriveSyncService()
