"""The Resource Library: what the Library Manifest includes.

The manifest sync writes ``LIBRARY_FILES_DIR/library.json``; the read helpers
here (``load_library``, ``get_document``, ``documents_for_system``,
``is_library_document``, ``is_browsable``) are the only way other code decides
what is in the library.
"""

from __future__ import annotations

import copy
import csv
import io
import json
import logging
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from backend.config import config

logger = logging.getLogger(__name__)

# The nine INTEGRATE Systems in canonical order: (slug, name).
SYSTEMS: list[tuple[str, str]] = [
    ("inspire", "Inspire"),
    ("nurture", "Nurture"),
    ("trust", "Trust"),
    ("embody", "Embody"),
    ("guide", "Guide"),
    ("regulate", "Regulate"),
    ("align", "Align"),
    ("transcend", "Transcend"),
    ("engage", "Engage"),
]
SYSTEM_NAMES: dict[str, str] = dict(SYSTEMS)

REFERENCE_TYPE = "Reference"
# Manifest Type values, matched case-insensitively → canonical spelling.
DOCUMENT_TYPES: dict[str, str] = {
    "lsp": "LSP",
    "field guide": "Field Guide",
    "reference": REFERENCE_TYPE,
}

# Directory under KB_CACHE_DIR holding indexed Library Document copies.
LIBRARY_SOURCE_DIR = "library"

_REQUIRED_COLUMNS = ("include", "title", "organization", "type", "file")


@dataclass
class ManifestRow:
    """One valid, included Library Manifest row."""

    row: int
    file_id: str
    title: str
    organization: str
    type: str
    systems: list[str] = field(default_factory=list)


# ── Parsing ───────────────────────────────────────────────────────────────

_PATH_ID_RE = re.compile(
    r"/(?:document|file|spreadsheets)(?:/u/\d+)?/d/([A-Za-z0-9_-]+)"
)
_BARE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,}$")


def extract_drive_file_id(link: str) -> Optional[str]:
    """Return the Drive file id from a Docs/Drive link, or None."""
    link = (link or "").strip()
    if not link:
        return None
    parsed = urlparse(link)
    if parsed.netloc.endswith(("docs.google.com", "drive.google.com")):
        match = _PATH_ID_RE.search(parsed.path)
        if match:
            return match.group(1)
        ids = parse_qs(parsed.query).get("id")
        if ids and _BARE_ID_RE.match(ids[0]):
            return ids[0]
    return None


def extract_sheet_id(value: str) -> Optional[str]:
    """Accept a Google Sheet URL or a bare file id."""
    value = (value or "").strip()
    if _BARE_ID_RE.match(value):
        return value
    return extract_drive_file_id(value)


def _checked(value: Optional[str]) -> bool:
    return (value or "").strip().upper() == "TRUE"


def parse_manifest_csv(text: str) -> tuple[list[ManifestRow], list[dict[str, Any]]]:
    """Parse the manifest's first tab exported as CSV.

    Returns the valid included rows and the issues for skipped rows. Raises
    ValueError when the header lacks a required column.
    """
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        raise ValueError("manifest is empty")
    columns = {name.strip().lower(): idx for idx, name in enumerate(header)}
    required = [*_REQUIRED_COLUMNS, *SYSTEM_NAMES]
    missing = [name for name in required if name not in columns]
    if missing:
        raise ValueError(f"manifest is missing columns: {', '.join(missing)}")

    def cell(values: list[str], name: str) -> str:
        idx = columns[name]
        return values[idx].strip() if idx < len(values) else ""

    rows: list[ManifestRow] = []
    issues: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row_number, values in enumerate(reader, start=2):
        if not _checked(cell(values, "include")):
            continue
        file_id = extract_drive_file_id(cell(values, "file"))
        title = cell(values, "title")
        if not file_id:
            issues.append(manifest_issue(row_number, None, "bad_link", "File link is not a Google Doc or Drive file link", title))
            continue
        if not title:
            issues.append(manifest_issue(row_number, file_id, "missing_title", "Title is empty"))
            continue
        doc_type = DOCUMENT_TYPES.get(cell(values, "type").lower())
        if not doc_type:
            issues.append(manifest_issue(row_number, file_id, "bad_type", "Type is not LSP, Field Guide, or Reference", title))
            continue
        systems = (
            []
            if doc_type == REFERENCE_TYPE
            else [slug for slug, _ in SYSTEMS if _checked(cell(values, slug))]
        )
        if doc_type != REFERENCE_TYPE and not systems:
            issues.append(manifest_issue(row_number, file_id, "no_system", "No INTEGRATE System is ticked", title))
            continue
        if file_id in seen:
            issues.append(manifest_issue(row_number, file_id, "duplicate_file", "File is already listed on another row", title))
            continue
        seen.add(file_id)
        rows.append(
            ManifestRow(
                row=row_number,
                file_id=file_id,
                title=title,
                organization=cell(values, "organization"),
                type=doc_type,
                systems=systems,
            )
        )
    return rows, issues


def manifest_issue(
    row: Optional[int],
    file_id: Optional[str],
    code: str,
    detail: str,
    title: Optional[str] = None,
) -> dict[str, Any]:
    issue: dict[str, Any] = {"row": row, "code": code, "detail": detail}
    if file_id:
        issue["file_id"] = file_id
    if title:
        issue["title"] = title
    return issue


# ── library.json ──────────────────────────────────────────────────────────


def library_files_dir() -> Path:
    return Path(config.LIBRARY_FILES_DIR)


def library_cache_dir() -> Path:
    """Where indexed copies of Library Documents live (under KB_CACHE_DIR)."""
    return Path(config.KB_CACHE_DIR) / LIBRARY_SOURCE_DIR


def library_json_path() -> Path:
    return library_files_dir() / "library.json"


def document_file_url(file_id: str) -> str:
    """The member-facing open link for a Library or Reference Document."""
    return f"/api/library/documents/{file_id}/file"


def citation(doc: dict[str, Any]) -> dict[str, Any]:
    """Citation payload for a Library or Reference Document."""
    return {
        "id": doc.get("file_id"),
        "title": doc.get("title"),
        "type": doc.get("type"),
        "systems": [] if doc.get("type") == REFERENCE_TYPE else list(doc.get("systems") or []),
        "url": document_file_url(str(doc.get("file_id"))),
    }


def _empty_library() -> dict[str, Any]:
    return {"documents": [], "issues": []}


_cache: dict[str, Any] = {"key": None, "data": None}


def load_library() -> dict[str, Any]:
    """Return the last synced library; empty when absent or unreadable."""
    path = library_json_path()
    try:
        stat = path.stat()
    except OSError:
        return _empty_library()
    key = (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
    if _cache["key"] == key:
        return copy.deepcopy(_cache["data"])
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        logger.warning("library.json unreadable: %s", type(error).__name__)
        return _empty_library()
    if not isinstance(data, dict) or not isinstance(data.get("documents"), list):
        return _empty_library()
    data.setdefault("issues", [])
    _cache.update(key=key, data=data)
    return copy.deepcopy(data)


def write_library(data: dict[str, Any], files_dir: Optional[Path] = None) -> None:
    """Atomically replace library.json (temp file + rename)."""
    target_dir = files_dir or library_files_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=target_dir, prefix=".library.", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
        os.replace(tmp_name, target_dir / "library.json")
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def get_document(file_id: str) -> Optional[dict[str, Any]]:
    for doc in load_library()["documents"]:
        if doc.get("file_id") == file_id:
            return doc
    return None


def is_library_document(file_id: Optional[str]) -> bool:
    """True for both Library and Reference Documents: the Librarian's corpus."""
    return bool(file_id) and get_document(file_id) is not None


def is_browsable(file_id: Optional[str]) -> bool:
    """True only for documents Members browse (Type other than Reference)."""
    doc = get_document(file_id) if file_id else None
    return doc is not None and doc.get("type") != REFERENCE_TYPE


def browsable_documents() -> list[dict[str, Any]]:
    return [d for d in load_library()["documents"] if d.get("type") != REFERENCE_TYPE]


def documents_for_system(slug: str) -> list[dict[str, Any]]:
    """Browsable documents spotlighting the System, sorted by title."""
    docs = [d for d in browsable_documents() if slug in (d.get("systems") or [])]
    return sorted(docs, key=lambda d: str(d.get("title", "")).casefold())


def served_pdf_path(doc: dict[str, Any]) -> Optional[Path]:
    """The document's served PDF, only if it resolves inside LIBRARY_FILES_DIR."""
    raw = doc.get("pdf_path")
    if not raw:
        return None
    root = library_files_dir().resolve()
    path = Path(raw).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return None
    return path


# ── Admin view ────────────────────────────────────────────────────────────

_ADMIN_DOCUMENT_FIELDS = ("file_id", "title", "organization", "type", "systems", "status")


def drive_file_url(file_id: str) -> str:
    """The Drive link an administrator follows to check a manifest row's file."""
    return f"https://drive.google.com/file/d/{file_id}/view"


def manifest_sheet_url(manifest_file_id: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{manifest_file_id}/edit"


def admin_view() -> dict[str, Any]:
    """The last synced library for administrators, without server paths.

    Issues keep their manifest row and code; each gains a Drive link when it
    names a file, and the document's title when the manifest row gave none.
    """
    data = load_library()
    titles = {d.get("file_id"): d.get("title") for d in data["documents"]}
    documents = [
        {
            **{key: doc.get(key) for key in _ADMIN_DOCUMENT_FIELDS},
            "link": drive_file_url(doc["file_id"]) if doc.get("file_id") else None,
        }
        for doc in data["documents"]
    ]
    issues = []
    for issue in data["issues"]:
        file_id = issue.get("file_id")
        issues.append({
            "row": issue.get("row"),
            "code": issue.get("code"),
            "detail": issue.get("detail"),
            "file_id": file_id,
            "title": issue.get("title") or titles.get(file_id),
            "link": drive_file_url(file_id) if file_id else None,
        })
    manifest_file_id = data.get("manifest_file_id")
    return {
        "manifest_file_id": manifest_file_id,
        "manifest_url": manifest_sheet_url(manifest_file_id) if manifest_file_id else None,
        "synced_at": data.get("synced_at"),
        "systems": [{"slug": slug, "name": name} for slug, name in SYSTEMS],
        "documents": documents,
        "issues": issues,
    }
