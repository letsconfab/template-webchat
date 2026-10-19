"""Library Manifest sync against a fake Google Drive client."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httplib2
from googleapiclient.errors import HttpError

from backend.config import config
from backend.services import library
from backend.services import drive_sync_service as drive_sync
from backend.services.drive_sync_service import sync_library_manifest

MANIFEST_ID = "sheet_manifest_01"
GDOC = "application/vnd.google-apps.document"
PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
HEADER = (
    "Include,Title,Organization,Type,File,"
    "Inspire,Nurture,Trust,Embody,Guide,Regulate,Align,Transcend,Engage,Notes"
)


def manifest_row(file_id: str, title: str, *, include="TRUE", doc_type="LSP", ticked=("Trust",)) -> str:
    flags = ["TRUE" if name in ticked else "FALSE" for _, name in library.SYSTEMS]
    link = f"https://drive.google.com/file/d/{file_id}/view"
    return ",".join([include, title, "Example Org", doc_type, link, *flags, ""])


def http_error(status: int) -> HttpError:
    return HttpError(httplib2.Response({"status": status}), b"error")


class _Request:
    def __init__(self, fn):
        self._fn = fn

    def execute(self):
        return self._fn()


class FakeDrive:
    """Minimal stand-in for ``build('drive', 'v3')``."""

    def __init__(self) -> None:
        self.manifest_csv = HEADER + "\n"
        self.manifest_error: int | None = None
        self.files_meta: dict[str, dict] = {}
        self.errors: dict[str, int] = {}
        self.downloads: list[tuple[str, str]] = []

    def add(self, file_id: str, mime: str, modified="2026-10-01T00:00:00Z", md5=None) -> None:
        self.files_meta[file_id] = {
            "id": file_id,
            "name": f"drive name {file_id}",
            "mimeType": mime,
            "modifiedTime": modified,
            "md5Checksum": md5,
        }

    def set_rows(self, *rows: str) -> None:
        self.manifest_csv = "\n".join([HEADER, *rows]) + "\n"

    def files(self):
        return self

    def get(self, fileId, fields=None, supportsAllDrives=None):
        def run():
            if fileId in self.errors:
                raise http_error(self.errors[fileId])
            return dict(self.files_meta[fileId])

        return _Request(run)

    def export_media(self, fileId, mimeType):
        def run():
            if fileId == MANIFEST_ID:
                if self.manifest_error:
                    raise http_error(self.manifest_error)
                return self.manifest_csv.encode()
            if fileId in self.errors:
                raise http_error(self.errors[fileId])
            self.downloads.append((fileId, mimeType))
            return f"{mimeType} of {fileId}".encode()

        return _Request(run)

    def get_media(self, fileId, supportsAllDrives=None):
        def run():
            if fileId in self.errors:
                raise http_error(self.errors[fileId])
            self.downloads.append((fileId, "media"))
            return b"%PDF-1.4 " + fileId.encode()

        return _Request(run)


class LibrarySyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.cache_dir = root / "kb_cache" / "library"
        self.files_dir = root / "library_files"
        patcher = patch.object(config, "LIBRARY_FILES_DIR", str(self.files_dir))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)
        self.drive = FakeDrive()

    def sync(self) -> dict:
        return sync_library_manifest(
            self.drive,
            MANIFEST_ID,
            cache_dir=self.cache_dir,
            files_dir=self.files_dir,
        )

    def library_json(self) -> dict:
        return json.loads((self.files_dir / "library.json").read_text())

    def test_google_doc_row_produces_indexed_text_and_served_pdf(self) -> None:
        self.drive.add("doc_aaaaaaaaaa", GDOC)
        self.drive.set_rows(manifest_row("doc_aaaaaaaaaa", "Sample Practice", ticked=("Engage", "Trust")))

        self.sync()

        text_copy = self.cache_dir / "doc_aaaaaaaaaa_Sample Practice.txt"
        self.assertEqual(text_copy.read_bytes(), b"text/plain of doc_aaaaaaaaaa")
        served = self.files_dir / "doc_aaaaaaaaaa.pdf"
        self.assertEqual(served.read_bytes(), b"application/pdf of doc_aaaaaaaaaa")
        sidecar = json.loads((self.cache_dir / ".doc_aaaaaaaaaa_Sample Practice.txt.meta.json").read_text())
        self.assertEqual(sidecar["id"], "doc_aaaaaaaaaa")
        self.assertEqual(sidecar["name"], "Sample Practice")

        doc = library.get_document("doc_aaaaaaaaaa")
        self.assertEqual(doc["title"], "Sample Practice")
        self.assertEqual(doc["organization"], "Example Org")
        self.assertEqual(doc["type"], "LSP")
        self.assertEqual(doc["systems"], ["trust", "engage"])
        self.assertEqual(doc["modified_time"], "2026-10-01T00:00:00Z")
        self.assertEqual(Path(doc["pdf_path"]), served)
        self.assertEqual(Path(doc["cache_path"]), text_copy)
        self.assertEqual(doc["status"], "ok")
        self.assertEqual(self.library_json()["issues"], [])

    def test_pdf_row_produces_indexed_and_served_copies(self) -> None:
        self.drive.add("pdf_bbbbbbbbbb", PDF, md5="m1")
        self.drive.set_rows(manifest_row("pdf_bbbbbbbbbb", "Field Notes"))

        self.sync()

        indexed = self.cache_dir / "pdf_bbbbbbbbbb_Field Notes.pdf"
        served = self.files_dir / "pdf_bbbbbbbbbb.pdf"
        self.assertTrue(indexed.read_bytes().startswith(b"%PDF"))
        self.assertEqual(indexed.read_bytes(), served.read_bytes())
        self.assertTrue(library.is_library_document("pdf_bbbbbbbbbb"))

    def test_docx_row_is_flagged_unsupported(self) -> None:
        self.drive.add("dcx_cccccccccc", DOCX)
        self.drive.set_rows(manifest_row("dcx_cccccccccc", "Draft"))

        self.sync()

        self.assertFalse(library.is_library_document("dcx_cccccccccc"))
        issues = self.library_json()["issues"]
        self.assertEqual([(i["code"], i["file_id"], i["row"]) for i in issues], [("unsupported_type", "dcx_cccccccccc", 2)])
        self.assertEqual(list(self.files_dir.glob("*.pdf")), [])

    def test_unchanged_files_are_not_downloaded_again(self) -> None:
        self.drive.add("doc_aaaaaaaaaa", GDOC)
        self.drive.add("pdf_bbbbbbbbbb", PDF, md5="m1")
        self.drive.set_rows(
            manifest_row("doc_aaaaaaaaaa", "Sample Practice"),
            manifest_row("pdf_bbbbbbbbbb", "Field Notes"),
        )
        self.sync()
        first = len(self.drive.downloads)

        self.sync()
        self.assertEqual(len(self.drive.downloads), first)

        self.drive.add("pdf_bbbbbbbbbb", PDF, md5="m2")
        self.sync()
        self.assertEqual(self.drive.downloads[first:], [("pdf_bbbbbbbbbb", "media")])

    def test_unchecking_a_row_removes_both_copies_and_entry(self) -> None:
        self.drive.add("doc_aaaaaaaaaa", GDOC)
        self.drive.set_rows(manifest_row("doc_aaaaaaaaaa", "Sample Practice"))
        self.sync()

        self.drive.set_rows(manifest_row("doc_aaaaaaaaaa", "Sample Practice", include="FALSE"))
        self.sync()

        self.assertIsNone(library.get_document("doc_aaaaaaaaaa"))
        self.assertEqual([p.name for p in self.cache_dir.iterdir()], [])
        self.assertFalse((self.files_dir / "doc_aaaaaaaaaa.pdf").exists())

    def test_deleted_row_removes_document(self) -> None:
        self.drive.add("doc_aaaaaaaaaa", GDOC)
        self.drive.set_rows(manifest_row("doc_aaaaaaaaaa", "Sample Practice"))
        self.sync()

        self.drive.set_rows()
        self.sync()

        self.assertEqual(library.load_library()["documents"], [])
        self.assertFalse((self.files_dir / "doc_aaaaaaaaaa.pdf").exists())

    def test_renamed_title_replaces_cached_copy(self) -> None:
        self.drive.add("doc_aaaaaaaaaa", GDOC)
        self.drive.set_rows(manifest_row("doc_aaaaaaaaaa", "Old Title"))
        self.sync()

        self.drive.set_rows(manifest_row("doc_aaaaaaaaaa", "New Title"))
        self.sync()

        names = sorted(p.name for p in self.cache_dir.iterdir())
        self.assertEqual(names, [".doc_aaaaaaaaaa_New Title.txt.meta.json", "doc_aaaaaaaaaa_New Title.txt"])
        self.assertEqual(library.get_document("doc_aaaaaaaaaa")["title"], "New Title")

    def test_unreachable_file_keeps_last_good_copy(self) -> None:
        self.drive.add("doc_aaaaaaaaaa", GDOC)
        self.drive.set_rows(manifest_row("doc_aaaaaaaaaa", "Sample Practice"))
        self.sync()

        for status in (403, 404):
            with self.subTest(status=status):
                self.drive.errors["doc_aaaaaaaaaa"] = status
                self.sync()

                doc = library.get_document("doc_aaaaaaaaaa")
                self.assertIsNotNone(doc)
                self.assertEqual(doc["status"], "unreachable")
                self.assertTrue(Path(doc["pdf_path"]).exists())
                self.assertTrue(Path(doc["cache_path"]).exists())
                issues = self.library_json()["issues"]
                self.assertEqual([(i["code"], i["file_id"]) for i in issues], [("unreachable", "doc_aaaaaaaaaa")])

    def test_unreachable_new_file_is_not_added(self) -> None:
        self.drive.errors["new_dddddddddd"] = 404
        self.drive.set_rows(manifest_row("new_dddddddddd", "Never Seen"))

        self.sync()

        self.assertIsNone(library.get_document("new_dddddddddd"))
        self.assertEqual(self.library_json()["issues"][0]["code"], "unreachable")

    def test_bad_rows_are_recorded_and_skipped(self) -> None:
        self.drive.add("doc_aaaaaaaaaa", GDOC)
        self.drive.set_rows(
            manifest_row("doc_aaaaaaaaaa", ""),
            manifest_row("doc_aaaaaaaaaa", "No Systems", ticked=()),
            "TRUE,Bad Link,Example Org,LSP,somewhere," + ",".join(["TRUE"] * 9) + ",",
            manifest_row("doc_aaaaaaaaaa", "Kept"),
            manifest_row("doc_aaaaaaaaaa", "Again"),
        )

        self.sync()

        codes = [i["code"] for i in self.library_json()["issues"]]
        self.assertEqual(codes, ["missing_title", "no_system", "bad_link", "duplicate_file"])
        self.assertEqual([d["title"] for d in library.load_library()["documents"]], ["Kept"])

    def test_local_write_failure_keeps_last_good_copy_and_other_rows(self) -> None:
        self.drive.add("doc_aaaaaaaaaa", GDOC)
        self.drive.add("pdf_bbbbbbbbbb", PDF, md5="m1")
        self.drive.set_rows(
            manifest_row("doc_aaaaaaaaaa", "Sample Practice"),
            manifest_row("pdf_bbbbbbbbbb", "Field Notes"),
        )
        self.sync()
        self.drive.add("doc_aaaaaaaaaa", GDOC, modified="2026-10-02T00:00:00Z")
        self.drive.add("pdf_bbbbbbbbbb", PDF, md5="m2")

        real_write = drive_sync._write_atomic

        def failing_write(path, data):
            if "doc_aaaaaaaaaa" in path.name:
                raise OSError("disk full")
            real_write(path, data)

        with patch.object(drive_sync, "_write_atomic", side_effect=failing_write):
            self.sync()

        doc = library.get_document("doc_aaaaaaaaaa")
        self.assertEqual(doc["modified_time"], "2026-10-01T00:00:00Z")
        self.assertTrue(Path(doc["pdf_path"]).exists())
        self.assertEqual(library.get_document("pdf_bbbbbbbbbb")["md5_checksum"], "m2")
        issues = self.library_json()["issues"]
        self.assertEqual([(i["code"], i["file_id"]) for i in issues], [("download_failed", "doc_aaaaaaaaaa")])

    def test_unreadable_manifest_changes_nothing(self) -> None:
        self.drive.add("doc_aaaaaaaaaa", GDOC)
        self.drive.set_rows(
            manifest_row("doc_aaaaaaaaaa", "Sample Practice"),
            manifest_row("doc_aaaaaaaaaa", ""),
        )
        self.sync()
        before = self.library_json()["documents"]

        self.drive.manifest_error = 404
        self.sync()

        data = self.library_json()
        self.assertEqual(data["documents"], before)
        self.assertEqual(
            [(i["code"], i["row"]) for i in data["issues"]],
            [("manifest_unreachable", None), ("missing_title", 3)],
        )
        self.assertTrue((self.files_dir / "doc_aaaaaaaaaa.pdf").exists())

    def test_manifest_without_required_columns_changes_nothing(self) -> None:
        self.drive.add("doc_aaaaaaaaaa", GDOC)
        self.drive.set_rows(manifest_row("doc_aaaaaaaaaa", "Sample Practice"))
        self.sync()

        self.drive.manifest_csv = "Title,File\nX,Y\n"
        self.sync()

        self.assertTrue(library.is_library_document("doc_aaaaaaaaaa"))
        self.assertEqual(self.library_json()["issues"][0]["code"], "manifest_unreachable")

    def test_reference_rows_are_synced_but_not_browsable(self) -> None:
        self.drive.add("ref_eeeeeeeeee", PDF, md5="r1")
        self.drive.add("doc_aaaaaaaaaa", GDOC)
        self.drive.set_rows(
            manifest_row("ref_eeeeeeeeee", "Sample Reference", doc_type="Reference", ticked=()),
            manifest_row("doc_aaaaaaaaaa", "Sample Practice", ticked=("Trust",)),
        )

        self.sync()

        self.assertTrue(library.is_library_document("ref_eeeeeeeeee"))
        self.assertFalse(library.is_browsable("ref_eeeeeeeeee"))
        self.assertTrue(library.is_browsable("doc_aaaaaaaaaa"))
        self.assertEqual(library.get_document("ref_eeeeeeeeee")["systems"], [])
        self.assertTrue((self.files_dir / "ref_eeeeeeeeee.pdf").exists())
        self.assertEqual(
            [d["file_id"] for d in library.documents_for_system("trust")],
            ["doc_aaaaaaaaaa"],
        )


class LoadLibraryTests(unittest.TestCase):
    def test_missing_or_corrupt_library_json_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(config, "LIBRARY_FILES_DIR", tmp):
                self.assertEqual(library.load_library()["documents"], [])
                Path(tmp, "library.json").write_text("{not json")
                self.assertEqual(library.load_library()["documents"], [])
                self.assertFalse(library.is_library_document("anything"))

    def test_callers_cannot_corrupt_the_loaded_library(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(config, "LIBRARY_FILES_DIR", tmp):
                library.write_library({"documents": [{"file_id": "a", "title": "T", "type": "LSP", "systems": ["trust"]}], "issues": []})
                library.load_library()["documents"].clear()
                library.get_document("a")["systems"].append("engage")

                self.assertEqual(library.get_document("a")["systems"], ["trust"])

    def test_stored_paths_are_absolute(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            drive = FakeDrive()
            drive.add("doc_aaaaaaaaaa", GDOC)
            drive.set_rows(manifest_row("doc_aaaaaaaaaa", "Sample Practice"))
            cwd = Path.cwd()
            os.chdir(tmp)
            try:
                with patch.object(config, "LIBRARY_FILES_DIR", "relative_files"):
                    sync_library_manifest(drive, MANIFEST_ID, cache_dir=Path("kb/library"), files_dir=Path("relative_files"))
                    doc = library.get_document("doc_aaaaaaaaaa")
            finally:
                os.chdir(cwd)
            self.assertTrue(Path(doc["pdf_path"]).is_absolute())
            self.assertTrue(Path(doc["cache_path"]).is_absolute())


if __name__ == "__main__":
    unittest.main()
