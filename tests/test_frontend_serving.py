"""The frontend catch-all serves the build folder and nothing outside it."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main


SECRET = b"SECRET_KEY=never-served"


class FrontendServingTests(unittest.TestCase):
    def setUp(self) -> None:
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        dist = root / "frontend" / "dist"
        (dist / "assets").mkdir(parents=True)
        (dist / "static").mkdir()
        (dist / "index.html").write_text("<!doctype html>app")
        (dist / "assets" / "app.js").write_text("console.log('app')")
        (dist / "static" / "logo.txt").write_text("logo")
        (root / ".env").write_bytes(SECRET)
        patcher = patch.object(main, "FRONTEND_DIST", dist)
        patcher.start()
        self.addCleanup(patcher.stop)
        # No context manager: the lifespan would mount the real build folder.
        self.client = TestClient(main.app)

    def test_build_files_are_served(self) -> None:
        for path, body in (
            ("/assets/app.js", b"console.log('app')"),
            ("/static/logo.txt", b"logo"),
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.content, body)

    def test_app_routes_fall_back_to_index(self) -> None:
        for path in ("/", "/login", "/library/some-doc", "/assets/missing.js"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn(b"app", response.content)

    def test_paths_outside_the_build_folder_are_refused(self) -> None:
        for prefix in ("assets", "static"):
            for tail in ("..%2F..%2F..%2F.env", "%2e%2e/%2e%2e/%2e%2e/.env"):
                path = f"/{prefix}/{tail}"
                with self.subTest(path=path):
                    response = self.client.get(path)
                    self.assertEqual(response.status_code, 404)
                    self.assertNotIn(SECRET, response.content)

    def test_a_directory_is_not_served_as_a_file(self) -> None:
        response = self.client.get("/assets/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"app", response.content)

    def test_unknown_api_paths_are_404_not_the_app_page(self) -> None:
        for path in ("/api/no-such-route", "/api"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 404)
                self.assertNotIn(b"<!doctype html>", response.content)


if __name__ == "__main__":
    unittest.main()
