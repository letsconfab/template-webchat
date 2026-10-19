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

from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError

from backend.config import config
from backend.services import library
from backend.services.source_provenance import google_doc_url

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


_SYNC_INTERVAL = 60  # seconds between successful syncs
_MAX_BACKOFF = 1800  # cap transient-error backoff at 30 minutes


class DriveSyncService:
    """Sync files from a Google Drive folder to a local cache directory."""

    def __init__(self) -> None:
        self.cache_dir = Path(config.KB_CACHE_DIR) / "drive"
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self.last_sync: Optional[datetime] = None
        self.file_count: int = 0
        self.error: Optional[str] = None
        self.needs_reconnect: bool = False
        self.auth_error: Optional[str] = None
        self._consecutive_failures: int = 0
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
        self.needs_reconnect = False
        self.auth_error = None
        self._consecutive_failures = 0
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
            delay = _SYNC_INTERVAL
            try:
                credentials = self._build_credentials(refresh_token)
                await self._sync_all(credentials, None)
                self.last_sync = datetime.utcnow()
                self.error = None
                self._consecutive_failures = 0
            except asyncio.CancelledError:
                break
            except Exception as e:
                if isinstance(e, RefreshError) or "invalid_grant" in str(e):
                    self.needs_reconnect = True
                    self.auth_error = str(e)
                    self.error = "Google Drive authorization expired — reconnect required"
                    self._running = False
                    logger.error(
                        "Drive sync stopped: authorization expired (%s). "
                        "Reconnect Google Drive from the settings page.",
                        e,
                    )
                    break
                self.error = str(e)
                self._consecutive_failures += 1
                delay = min(_SYNC_INTERVAL * 2 ** self._consecutive_failures, _MAX_BACKOFF)
                logger.error("Drive sync error (retrying in %ss): %s", delay, e)
            await asyncio.sleep(delay)

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

            settings = await self._load_settings()
            folder_id = root_folder_id or (
                settings.google_drive_root_folder_id if settings else None
            )
            result: dict = {"status": "no_folder_configured"}
            if folder_id:
                result = await self._sync_root_folder(service, folder_id)

            manifest_id = settings.library_manifest_file_id if settings else None
            if manifest_id:
                result["library"] = await asyncio.to_thread(
                    sync_library_manifest, service, manifest_id
                )
            return result
        finally:
            self._sync_in_progress = False

    async def _load_settings(self):
        from backend.database import AsyncSessionLocal
        from sqlalchemy import select
        from backend.models.settings import SystemSettings

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(SystemSettings).limit(1))
            return result.scalar_one_or_none()

    async def _sync_root_folder(self, service, folder_id: str) -> dict:
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
                fields="nextPageToken, files(id, name, mimeType, md5Checksum, modifiedTime, size, webViewLink)",
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
                file_id = file_info.get("id")
                web_view = file_info.get("webViewLink")
                if not web_view and file_id:
                    web_view = google_doc_url(str(file_id))
                meta = {
                    "id": file_id,
                    "name": file_info.get("name"),
                    "mimeType": file_info.get("mimeType"),
                    "modifiedTime": file_info.get("modifiedTime"),
                    "md5Checksum": file_info.get("md5Checksum"),
                    "webViewLink": web_view,
                }
                self._meta_path(local_path).write_text(json.dumps(meta))
        except HttpError as e:
            logger.error("Failed to download %s: %s", file_id, e)

    def _cached_drive_id(self, local_path: Path) -> str:
        # Drive IDs may contain underscores, so the {id}_{name} filename is
        # ambiguous — trust the meta sidecar when present.
        meta_path = self._meta_path(local_path)
        if meta_path.exists():
            try:
                file_id = json.loads(meta_path.read_text()).get("id")
                if file_id:
                    return file_id
            except (json.JSONDecodeError, OSError):
                pass
        return local_path.name.split("_", 1)[0]

    async def _remove_stale(self, active_drive_ids: set[str]) -> None:
        if not self.cache_dir.exists():
            return
        for child in self.cache_dir.iterdir():
            if child.is_file() and child.name.endswith(".meta.json"):
                continue
            if child.is_file():
                if self._cached_drive_id(child) not in active_drive_ids:
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
            "needs_reconnect": self.needs_reconnect,
            "auth_error": self.auth_error,
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


# ── Library Manifest sync ─────────────────────────────────────────────────

GOOGLE_DOC_MIME = "application/vnd.google-apps.document"
PDF_MIME = "application/pdf"
_LIBRARY_FILE_FIELDS = "id, name, mimeType, modifiedTime, md5Checksum, webViewLink"


def _safe_title(title: str) -> str:
    cleaned = "".join("_" if c in '/\\:\0' or ord(c) < 32 else c for c in title)
    return cleaned.strip(" .")[:120] or "untitled"


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.part"
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _remove_cache_copy(cache_path: Optional[str]) -> None:
    if not cache_path:
        return
    path = Path(cache_path)
    path.unlink(missing_ok=True)
    (path.parent / f".{path.name}.meta.json").unlink(missing_ok=True)


def _needs_download(prev: Optional[dict], meta: dict, cache_path: Path, pdf_path: Path) -> bool:
    if not prev or not cache_path.exists() or not pdf_path.exists():
        return True
    if meta.get("modifiedTime") != prev.get("modified_time"):
        return True
    return meta.get("md5Checksum") != prev.get("md5_checksum")


def sync_library_manifest(
    service,
    manifest_file_id: str,
    *,
    cache_dir: Optional[Path] = None,
    files_dir: Optional[Path] = None,
) -> dict:
    """Sync Library Documents from the Library Manifest (blocking Drive calls).

    Google Docs are exported as text (indexed, under ``cache_dir``) and as PDF
    (served, under ``files_dir``); PDFs are downloaded once and written to
    both. ``library.json`` in ``files_dir`` records documents and issues.
    """
    cache_dir = cache_dir or library.library_cache_dir()
    files_dir = files_dir or library.library_files_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    files_dir.mkdir(parents=True, exist_ok=True)
    previous = library.load_library()
    prev_docs = {d["file_id"]: d for d in previous.get("documents", []) if d.get("file_id")}
    synced_at = datetime.utcnow().isoformat()

    try:
        raw = service.files().export_media(fileId=manifest_file_id, mimeType="text/csv").execute()
        text = raw.decode("utf-8-sig") if isinstance(raw, bytes) else str(raw)
        rows, issues = library.parse_manifest_csv(text)
    except Exception as error:  # Drive failure or unusable header: change nothing.
        logger.error("Library Manifest unreadable: %s", type(error).__name__)
        library.write_library(
            {
                **previous,
                "manifest_file_id": manifest_file_id,
                "issues": [{
                    "row": None,
                    "code": "manifest_unreachable",
                    "detail": _error_detail(error),
                }],
                "synced_at": synced_at,
            },
            files_dir,
        )
        return {"status": "manifest_unreachable", "document_count": len(prev_docs)}

    documents: list[dict] = []
    for row in rows:
        prev = prev_docs.get(row.file_id)
        try:
            meta = service.files().get(
                fileId=row.file_id, fields=_LIBRARY_FILE_FIELDS, supportsAllDrives=True
            ).execute()
            mime = meta.get("mimeType")
            if mime not in (GOOGLE_DOC_MIME, PDF_MIME):
                issues.append(library._issue(
                    row.row, row.file_id, "unsupported_type",
                    "File must be a Google Doc or a PDF",
                ))
                continue
            ext = ".txt" if mime == GOOGLE_DOC_MIME else ".pdf"
            cache_path = cache_dir / f"{row.file_id}_{_safe_title(row.title)}{ext}"
            pdf_path = files_dir / f"{row.file_id}.pdf"
            if _needs_download(prev, meta, cache_path, pdf_path):
                _download_library_file(service, row.file_id, mime, cache_path, pdf_path)
                logger.info("Library Document downloaded: %s", row.file_id)
        except HttpError as error:
            issues.append(library._issue(row.row, row.file_id, "unreachable", _error_detail(error)))
            if prev:
                documents.append({**prev, "status": "unreachable"})
            continue

        _write_library_sidecar(cache_path, row.title, meta)
        if prev and prev.get("cache_path") and Path(prev["cache_path"]) != cache_path:
            _remove_cache_copy(prev["cache_path"])
        documents.append({
            "file_id": row.file_id,
            "title": row.title,
            "organization": row.organization,
            "type": row.type,
            "systems": row.systems,
            "modified_time": meta.get("modifiedTime"),
            "md5_checksum": meta.get("md5Checksum"),
            "pdf_path": str(pdf_path),
            "cache_path": str(cache_path),
            "status": "ok",
        })

    _remove_dropped(documents, prev_docs.values(), cache_dir, files_dir)
    issues.sort(key=lambda i: (i.get("row") or 0))
    library.write_library(
        {
            "manifest_file_id": manifest_file_id,
            "synced_at": synced_at,
            "documents": documents,
            "issues": issues,
        },
        files_dir,
    )
    return {"status": "ok", "document_count": len(documents), "issue_count": len(issues)}


def _error_detail(error: Exception) -> str:
    if isinstance(error, HttpError):
        return f"Google Drive returned HTTP {error.resp.status}"
    if isinstance(error, ValueError):
        return str(error)[:300]
    return type(error).__name__


def _download_library_file(service, file_id: str, mime: str, cache_path: Path, pdf_path: Path) -> None:
    files = service.files()
    if mime == GOOGLE_DOC_MIME:
        text = files.export_media(fileId=file_id, mimeType="text/plain").execute()
        pdf = files.export_media(fileId=file_id, mimeType=PDF_MIME).execute()
        _write_atomic(cache_path, text)
        _write_atomic(pdf_path, pdf)
    else:
        pdf = files.get_media(fileId=file_id, supportsAllDrives=True).execute()
        _write_atomic(cache_path, pdf)
        _write_atomic(pdf_path, pdf)


def _write_library_sidecar(cache_path: Path, title: str, meta: dict) -> None:
    file_id = meta.get("id")
    sidecar = {
        "id": file_id,
        "name": title,
        "mimeType": meta.get("mimeType"),
        "modifiedTime": meta.get("modifiedTime"),
        "md5Checksum": meta.get("md5Checksum"),
        "webViewLink": meta.get("webViewLink") or (google_doc_url(str(file_id)) if file_id else None),
    }
    (cache_path.parent / f".{cache_path.name}.meta.json").write_text(json.dumps(sidecar))


def _remove_dropped(documents: list[dict], previous, cache_dir: Path, files_dir: Path) -> None:
    """Delete copies of documents no longer in the library, plus orphans."""
    kept_ids = {d["file_id"] for d in documents}
    kept_cache = {Path(d["cache_path"]).name for d in documents if d.get("cache_path")}
    for prev in previous:
        if prev.get("file_id") not in kept_ids:
            _remove_cache_copy(prev.get("cache_path"))
            (files_dir / f"{prev['file_id']}.pdf").unlink(missing_ok=True)
            logger.info("Library Document removed: %s", prev.get("file_id"))
    for child in cache_dir.iterdir():
        if not child.is_file():
            continue
        name = child.name
        if name.startswith(".") and name.endswith(".meta.json"):
            name = name[1:-len(".meta.json")]
        if name not in kept_cache:
            child.unlink(missing_ok=True)
    for child in files_dir.glob("*.pdf"):
        if child.stem not in kept_ids:
            child.unlink(missing_ok=True)
