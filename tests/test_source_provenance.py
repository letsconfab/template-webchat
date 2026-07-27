"""Unit tests for Knowledge Source provenance formatting."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.services.source_provenance import (
    format_retrieval_source,
    google_doc_url,
    load_drive_file_meta,
    resolve_chunk_locator,
)


class GoogleDocUrlTests(unittest.TestCase):
    def test_builds_canonical_read_only_drive_url(self) -> None:
        self.assertEqual(
            google_doc_url("abc123XYZ"),
            "https://drive.google.com/file/d/abc123XYZ/view",
        )


class FormatRetrievalSourceTests(unittest.TestCase):
    def test_includes_title_url_locator_and_revision(self) -> None:
        text = format_retrieval_source(
            title="ALO Licensing Policy",
            passage="Licensing requires board approval.",
            google_url="https://drive.google.com/file/d/file1/view",
            locator="Heading: Licensing",
            modified_time="2026-07-01T12:00:00.000Z",
            chunk_index=2,
            relevance=0.91,
        )
        self.assertIn("[Source: ALO Licensing Policy", text)
        self.assertIn("https://drive.google.com/file/d/file1/view", text)
        self.assertIn("Heading: Licensing", text)
        self.assertIn("chunk 2", text)
        self.assertIn("revised 2026-07-01T12:00:00.000Z", text)
        self.assertIn("Licensing requires board approval.", text)

    def test_omits_invented_fine_locator_when_only_document_level(self) -> None:
        text = format_retrieval_source(
            title="Overview",
            passage="Overview text",
            google_url="https://drive.google.com/file/d/x/view",
            locator=None,
            modified_time=None,
            chunk_index=0,
            relevance=0.5,
        )
        self.assertIn("chunk 0", text)
        self.assertNotIn("Heading:", text)


class ResolveChunkLocatorTests(unittest.TestCase):
    def test_uses_nearest_markdown_heading_when_present(self) -> None:
        full = "# Intro\n\npara\n\n## Governance\n\nBoard rules apply.\n"
        chunk = "Board rules apply."
        self.assertEqual(resolve_chunk_locator(full, chunk), "Heading: Governance")

    def test_falls_back_to_none_when_no_heading(self) -> None:
        self.assertIsNone(resolve_chunk_locator("plain text only", "plain text only"))


class LoadDriveFileMetaTests(unittest.TestCase):
    def test_reads_sidecar_next_to_cached_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            cached = cache / "fileId_Doc.txt"
            cached.write_text("body")
            meta_path = cache / ".fileId_Doc.txt.meta.json"
            meta_path.write_text(
                json.dumps(
                    {
                        "id": "fileId",
                        "name": "Doc",
                        "mimeType": "application/vnd.google-apps.document",
                        "modifiedTime": "2026-07-01T00:00:00.000Z",
                        "webViewLink": "https://drive.google.com/file/d/fileId/view",
                    }
                )
            )
            meta = load_drive_file_meta(cached)
            self.assertEqual(meta["id"], "fileId")
            self.assertEqual(
                meta["webViewLink"],
                "https://drive.google.com/file/d/fileId/view",
            )


if __name__ == "__main__":
    unittest.main()
