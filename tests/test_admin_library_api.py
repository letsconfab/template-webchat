"""Admin view of the synced Resource Library: ``GET /api/admin/library``."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.config import config
from backend.database import Base, get_db
from backend.models.user import User
from backend.services import library
from backend.services.auth import create_access_token
import backend.main as main


class AdminLibraryApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        database = Path(cls.tempdir.name) / "admin_library.db"
        cls.engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
        cls.sessions = async_sessionmaker(cls.engine, expire_on_commit=False)
        asyncio.run(cls._create_schema())

        async def override_db():
            async with cls.sessions() as session:
                yield session

        main.app.dependency_overrides[get_db] = override_db
        cls.client = TestClient(main.app)
        cls.admin = {"Authorization": f"Bearer {create_access_token({'sub': '1'})}"}
        cls.member = {"Authorization": f"Bearer {create_access_token({'sub': '2'})}"}

    @classmethod
    async def _create_schema(cls) -> None:
        async with cls.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with cls.sessions() as session:
            session.add(User(id=1, email="admin@example.test", password_hash="h", role="admin", is_active=True))
            session.add(User(id=2, email="member@example.test", password_hash="h", role="user", is_active=True))
            await session.commit()

    @classmethod
    def tearDownClass(cls) -> None:
        main.app.dependency_overrides.clear()
        asyncio.run(cls.engine.dispose())
        cls.tempdir.cleanup()

    def setUp(self) -> None:
        self.files = tempfile.TemporaryDirectory()
        self.addCleanup(self.files.cleanup)
        patcher = patch.object(config, "LIBRARY_FILES_DIR", self.files.name)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_synced_library(self) -> None:
        library.write_library({
            "manifest_file_id": "sheet_0123456789",
            "synced_at": "2026-10-01T00:00:00",
            "documents": [
                {
                    "file_id": "doc_aaaaaaaaaa",
                    "title": "Sample Practice One",
                    "organization": "Example Org",
                    "type": "LSP",
                    "systems": ["trust", "inspire"],
                    "status": "ok",
                    "pdf_path": f"{self.files.name}/doc_aaaaaaaaaa.pdf",
                    "cache_path": "/srv/kb_cache/library/doc_aaaaaaaaaa.txt",
                },
                {
                    "file_id": "ref_bbbbbbbbbb",
                    "title": "Sample Reference",
                    "organization": "Example Org",
                    "type": "Reference",
                    "systems": [],
                    "status": "unreachable",
                },
            ],
            "issues": [
                {"row": None, "code": "manifest_unreachable", "detail": "HttpError"},
                {"row": 3, "code": "bad_link", "detail": "File link is not a Google Doc or Drive file link"},
                {"row": 5, "code": "unreachable", "detail": "HttpError", "file_id": "ref_bbbbbbbbbb"},
                {"row": 7, "code": "bad_type", "detail": "Type is not LSP, Field Guide, or Reference",
                 "file_id": "doc_cccccccccc", "title": "Sample Practice Two"},
            ],
        })

    def test_members_cannot_read_the_admin_library(self) -> None:
        self.write_synced_library()
        self.assertIn(self.client.get("/api/admin/library", headers=self.member).status_code, (401, 403))
        self.assertIn(self.client.get("/api/admin/library").status_code, (401, 403))

    def test_admin_sees_documents_with_systems_and_status(self) -> None:
        self.write_synced_library()

        response = self.client.get("/api/admin/library", headers=self.admin)

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["synced_at"], "2026-10-01T00:00:00")
        self.assertEqual(body["manifest_url"], "https://docs.google.com/spreadsheets/d/sheet_0123456789/edit")
        self.assertEqual(
            [s["slug"] for s in body["systems"]],
            ["inspire", "nurture", "trust", "embody", "guide", "regulate", "align", "transcend", "engage"],
        )
        docs = {d["file_id"]: d for d in body["documents"]}
        self.assertEqual(docs["doc_aaaaaaaaaa"]["systems"], ["trust", "inspire"])
        self.assertEqual(docs["doc_aaaaaaaaaa"]["status"], "ok")
        self.assertEqual(docs["ref_bbbbbbbbbb"]["type"], "Reference")
        self.assertEqual(docs["ref_bbbbbbbbbb"]["status"], "unreachable")

    def test_server_paths_are_not_exposed(self) -> None:
        self.write_synced_library()

        body = self.client.get("/api/admin/library", headers=self.admin).text

        self.assertNotIn("pdf_path", body)
        self.assertNotIn("cache_path", body)

    def test_issues_pass_through_with_row_title_and_link(self) -> None:
        self.write_synced_library()

        issues = self.client.get("/api/admin/library", headers=self.admin).json()["issues"]

        self.assertEqual(
            [(i["row"], i["code"]) for i in issues],
            [(None, "manifest_unreachable"), (3, "bad_link"), (5, "unreachable"), (7, "bad_type")],
        )
        by_row = {i["row"]: i for i in issues}
        self.assertIsNone(by_row[3].get("link"))
        # A document already in the library lends its title to its issue.
        self.assertEqual(by_row[5]["title"], "Sample Reference")
        self.assertEqual(by_row[5]["link"], "https://drive.google.com/file/d/ref_bbbbbbbbbb/view")
        self.assertEqual(by_row[7]["title"], "Sample Practice Two")

    def test_never_synced_library_is_empty(self) -> None:
        response = self.client.get("/api/admin/library", headers=self.admin)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["documents"], [])
        self.assertEqual(body["issues"], [])
        self.assertIsNone(body["synced_at"])
        self.assertIsNone(body["manifest_url"])


if __name__ == "__main__":
    unittest.main()
