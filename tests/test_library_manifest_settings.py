"""Library Manifest configuration: startup guard, admin endpoint, sync hook."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.config import Config, validate_config
from backend.database import Base, get_db
from backend.models.settings import SystemSettings
from backend.models.user import User
from backend.services.auth import create_access_token
from backend.services.drive_sync_service import DriveSyncService
import backend.main as main


def _cfg(kb: str, files: str) -> Config:
    cfg = Config()
    cfg.SECRET_KEY = "x" * 40
    cfg.NEO4J_PASSWORD = "not-the-default"
    cfg.KB_CACHE_DIR = kb
    cfg.LIBRARY_FILES_DIR = files
    return cfg


class LibraryFilesDirGuardTests(unittest.TestCase):
    def test_library_files_dir_inside_kb_cache_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for files in (f"{tmp}/kb_cache/library_files", f"{tmp}/kb_cache"):
                with self.subTest(files=files):
                    with self.assertRaisesRegex(RuntimeError, "LIBRARY_FILES_DIR"):
                        validate_config(_cfg(f"{tmp}/kb_cache", files))

    def test_relative_paths_are_compared_after_resolving(self) -> None:
        with self.assertRaises(RuntimeError):
            validate_config(_cfg("./kb_cache", "kb_cache/../kb_cache/served"))

    def test_sibling_directories_are_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            validate_config(_cfg(f"{tmp}/kb_cache", f"{tmp}/kb_cache_files"))
            validate_config(_cfg(f"{tmp}/kb_cache", f"{tmp}/library_files"))


class LibraryManifestEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        database = Path(cls.tempdir.name) / "manifest.db"
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
            session.add(SystemSettings(is_configured=True))
            session.add(User(id=1, email="admin@example.test", password_hash="h", role="admin", is_active=True))
            session.add(User(id=2, email="member@example.test", password_hash="h", role="user", is_active=True))
            await session.commit()

    @classmethod
    def tearDownClass(cls) -> None:
        main.app.dependency_overrides.clear()
        asyncio.run(cls.engine.dispose())
        cls.tempdir.cleanup()

    async def _stored(self):
        async with self.sessions() as session:
            row = (await session.execute(select(SystemSettings).limit(1))).scalar_one()
            return row.library_manifest_file_id

    def test_admin_stores_sheet_id_from_url(self) -> None:
        response = self.client.patch(
            "/api/drive/library-manifest",
            headers=self.admin,
            json={"manifest": "https://docs.google.com/spreadsheets/d/sheet_abcdefghij/edit#gid=0"},
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["library_manifest_file_id"], "sheet_abcdefghij")
        self.assertEqual(asyncio.run(self._stored()), "sheet_abcdefghij")

    def test_admin_stores_bare_id_and_can_clear(self) -> None:
        ok = self.client.patch("/api/drive/library-manifest", headers=self.admin, json={"manifest": "sheet_0123456789"})
        self.assertEqual(ok.json()["library_manifest_file_id"], "sheet_0123456789")

        cleared = self.client.patch("/api/drive/library-manifest", headers=self.admin, json={"manifest": ""})
        self.assertEqual(cleared.status_code, 200)
        self.assertIsNone(asyncio.run(self._stored()))

    def test_unparseable_value_is_rejected(self) -> None:
        response = self.client.patch("/api/drive/library-manifest", headers=self.admin, json={"manifest": "not a sheet"})
        self.assertEqual(response.status_code, 422)

    def test_members_cannot_set_the_manifest(self) -> None:
        response = self.client.patch("/api/drive/library-manifest", headers=self.member, json={"manifest": "sheet_0123456789"})
        self.assertIn(response.status_code, (401, 403))


class SyncLoopHookTests(unittest.IsolatedAsyncioTestCase):
    async def _run(self, settings) -> tuple[DriveSyncService, list]:
        service = DriveSyncService()
        calls: list = []
        drive = object()

        def fake_sync(svc, manifest_id, **kwargs):
            calls.append((svc, manifest_id))
            return {"status": "ok"}

        with (
            patch("backend.services.drive_sync_service.build", return_value=drive),
            patch.object(service, "_load_settings", new=AsyncMock(return_value=settings)),
            patch.object(service, "_list_all_files", new=AsyncMock(return_value=[])),
            patch("backend.services.drive_sync_service.sync_library_manifest", side_effect=fake_sync),
        ):
            creds = SimpleNamespace(expired=False, refresh_token="t")
            result = await service._sync_all(creds, None)
        return result, calls, drive

    async def test_manifest_sync_runs_after_root_folder_sync(self) -> None:
        settings = SimpleNamespace(google_drive_root_folder_id="folder", library_manifest_file_id="sheet_1")
        result, calls, drive = await self._run(settings)
        self.assertEqual(calls, [(drive, "sheet_1")])
        self.assertEqual(result["library"], {"status": "ok"})

    async def test_manifest_sync_runs_without_root_folder(self) -> None:
        settings = SimpleNamespace(google_drive_root_folder_id=None, library_manifest_file_id="sheet_1")
        _, calls, _ = await self._run(settings)
        self.assertEqual(len(calls), 1)

    async def test_skipped_when_no_manifest_configured(self) -> None:
        settings = SimpleNamespace(google_drive_root_folder_id="folder", library_manifest_file_id=None)
        _, calls, _ = await self._run(settings)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
