"""Member-facing Library API grouped by INTEGRATE System."""

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

SYSTEM_ORDER = [
    "inspire", "nurture", "trust", "embody", "guide",
    "regulate", "align", "transcend", "engage",
]


class LibraryApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        database = Path(cls.tempdir.name) / "library_api.db"
        cls.engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
        cls.sessions = async_sessionmaker(cls.engine, expire_on_commit=False)
        asyncio.run(cls._create_schema())

        async def override_db():
            async with cls.sessions() as session:
                yield session

        main.app.dependency_overrides[get_db] = override_db
        cls.client = TestClient(main.app)
        cls.member = {"Authorization": f"Bearer {create_access_token({'sub': '2'})}"}
        cls.inactive = {"Authorization": f"Bearer {create_access_token({'sub': '3'})}"}

    @classmethod
    async def _create_schema(cls) -> None:
        async with cls.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with cls.sessions() as session:
            session.add(User(id=2, email="member@example.test", password_hash="h", role="user", is_active=True))
            session.add(User(id=3, email="gone@example.test", password_hash="h", role="user", is_active=False))
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

    def write_library(self, *docs: dict) -> None:
        library.write_library({"documents": list(docs), "issues": []})

    def doc(self, file_id: str, title: str, systems: list[str], doc_type: str = "LSP", with_pdf: bool = True) -> dict:
        pdf_path = Path(self.files.name) / f"{file_id}.pdf"
        if with_pdf:
            pdf_path.write_bytes(b"%PDF-1.4 " + file_id.encode())
        return {
            "file_id": file_id,
            "title": title,
            "organization": "Example Org",
            "type": doc_type,
            "systems": systems,
            "modified_time": "2026-10-01T00:00:00Z",
            "pdf_path": str(pdf_path),
            "cache_path": f"/cache/{file_id}.txt",
            "status": "ok",
        }

    def test_every_endpoint_requires_authentication(self) -> None:
        for path in ("/api/library/systems", "/api/library/systems/trust", "/api/library/documents/abc/file"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 401)

    def test_inactive_users_are_refused(self) -> None:
        response = self.client.get("/api/library/systems", headers=self.inactive)
        self.assertIn(response.status_code, (400, 401, 403))

    def test_missing_library_lists_nine_systems_with_zero_counts(self) -> None:
        response = self.client.get("/api/library/systems", headers=self.member)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual([s["slug"] for s in body], SYSTEM_ORDER)
        self.assertEqual(body[0], {"slug": "inspire", "name": "Inspire", "document_count": 0})
        self.assertTrue(all(s["document_count"] == 0 for s in body))

    def test_document_appears_under_every_spotlighted_system(self) -> None:
        self.write_library(
            self.doc("doc_a", "Zeta Practice", ["trust", "engage"]),
            self.doc("doc_b", "Alpha Practice", ["trust"]),
        )

        counts = {s["slug"]: s["document_count"] for s in self.client.get("/api/library/systems", headers=self.member).json()}
        self.assertEqual(counts["trust"], 2)
        self.assertEqual(counts["engage"], 1)
        self.assertEqual(counts["inspire"], 0)

        trust = self.client.get("/api/library/systems/trust", headers=self.member).json()
        self.assertEqual(trust["slug"], "trust")
        self.assertEqual(trust["name"], "Trust")
        self.assertEqual([d["title"] for d in trust["documents"]], ["Alpha Practice", "Zeta Practice"])
        self.assertEqual(
            trust["documents"][1],
            {
                "id": "doc_a",
                "title": "Zeta Practice",
                "organization": "Example Org",
                "type": "LSP",
                "systems": ["trust", "engage"],
                "modified_time": "2026-10-01T00:00:00Z",
            },
        )
        engage = self.client.get("/api/library/systems/engage", headers=self.member).json()
        self.assertEqual([d["id"] for d in engage["documents"]], ["doc_a"])

    def test_unknown_system_is_404(self) -> None:
        response = self.client.get("/api/library/systems/wisdom", headers=self.member)
        self.assertEqual(response.status_code, 404)

    def test_file_streams_the_served_pdf_inline(self) -> None:
        self.write_library(self.doc("doc_a", "Zeta Practice", ["trust"]))

        response = self.client.get("/api/library/documents/doc_a/file", headers=self.member)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/pdf")
        self.assertEqual(response.headers["content-disposition"], 'inline; filename="Zeta Practice.pdf"')
        self.assertEqual(response.content, b"%PDF-1.4 doc_a")

    def test_file_for_unknown_id_or_missing_file_is_404(self) -> None:
        self.write_library(self.doc("doc_gone", "Gone", ["trust"], with_pdf=False))

        for file_id in ("not_in_library", "doc_gone"):
            with self.subTest(file_id=file_id):
                response = self.client.get(f"/api/library/documents/{file_id}/file", headers=self.member)
                self.assertEqual(response.status_code, 404)

    def test_paths_outside_the_library_are_never_served(self) -> None:
        outside = Path(self.tempdir.name) / "secret.pdf"
        outside.write_bytes(b"secret")
        tampered = self.doc("doc_evil", "Evil", ["trust"], with_pdf=False)
        tampered["pdf_path"] = str(outside)
        self.write_library(tampered)

        for path in (
            "/api/library/documents/doc_evil/file",
            "/api/library/documents/..%2F..%2Fsecret/file",
            "/api/library/documents/../../secret.pdf/file",
        ):
            with self.subTest(path=path):
                response = self.client.get(path, headers=self.member)
                self.assertEqual(response.status_code, 404)
                self.assertNotEqual(response.content, b"secret")

    def test_reference_documents_are_unlisted_but_openable(self) -> None:
        self.write_library(
            self.doc("ref_a", "Charter", [], doc_type="Reference"),
            self.doc("doc_a", "Zeta Practice", ["trust"]),
        )

        systems = self.client.get("/api/library/systems", headers=self.member).json()
        self.assertEqual(sum(s["document_count"] for s in systems), 1)
        for slug in SYSTEM_ORDER:
            ids = [d["id"] for d in self.client.get(f"/api/library/systems/{slug}", headers=self.member).json()["documents"]]
            self.assertNotIn("ref_a", ids)

        response = self.client.get("/api/library/documents/ref_a/file", headers=self.member)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"%PDF-1.4 ref_a")


if __name__ == "__main__":
    unittest.main()
