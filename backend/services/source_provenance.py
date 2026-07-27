"""Knowledge Source provenance helpers for indexing and retrieval citations."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional


def google_doc_url(file_id: str) -> str:
    """Canonical read-only Google Drive / Docs viewer URL for a file id."""
    return f"https://drive.google.com/file/d/{file_id}/view"


def load_drive_file_meta(cached_file: Path) -> dict[str, Any]:
    """Load the Drive sync sidecar next to a cached file, if present."""
    meta_path = cached_file.parent / f".{cached_file.name}.meta.json"
    if not meta_path.exists():
        return {}
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


def resolve_chunk_locator(full_document: str, chunk_text: str) -> Optional[str]:
    """Return the nearest preceding Markdown heading for a chunk, if any.

    When the source format does not expose a heading (or the chunk cannot be
    located), return None so callers do not invent a fine-grained locator.
    """
    if not full_document or not chunk_text:
        return None
    needle = chunk_text.strip()[:120]
    if not needle:
        return None
    idx = full_document.find(needle)
    if idx < 0:
        # Try a shorter unique prefix
        needle = chunk_text.strip()[:40]
        idx = full_document.find(needle) if needle else -1
    if idx < 0:
        return None

    preceding = full_document[:idx]
    headings = list(_HEADING_RE.finditer(preceding))
    if not headings:
        return None
    title = headings[-1].group(2).strip()
    return f"Heading: {title}" if title else None


def format_retrieval_source(
    *,
    title: str,
    passage: str,
    google_url: Optional[str],
    locator: Optional[str],
    modified_time: Optional[str],
    chunk_index: int,
    relevance: Optional[float] = None,
) -> str:
    """Format one retrieval hit for the model with claim-level citation fields."""
    score_str = (
        f" (relevance {relevance:.2f})"
        if isinstance(relevance, (int, float))
        else ""
    )
    meta_parts: list[str] = [f"chunk {chunk_index}"]
    if locator:
        meta_parts.insert(0, locator)
    if modified_time:
        meta_parts.append(f"revised {modified_time}")
    if google_url:
        meta_parts.append(f"url {google_url}")

    header = f"[Source: {title}{score_str} | {'; '.join(meta_parts)}]"
    return f"{header}\n{passage}"


def display_title_from_filename(filename: str) -> str:
    """Humanize a Drive-cache filename by stripping the file-id prefix."""
    source = filename
    if "_Copy of " in source:
        source = source.split("_Copy of ", 1)[1]
    elif "_" in source:
        source = source.split("_", 1)[1]
    # Drop extension for display when present
    return Path(source).stem if source else "unknown"
