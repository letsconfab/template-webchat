"""Black-box tests for tracked production release helpers."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFY_RELEASE = REPO_ROOT / "scripts" / "verify_release.py"
RENDER_SERVICE = REPO_ROOT / "scripts" / "render_webchat_service.py"
MANAGE_ENVIRONMENT = REPO_ROOT / "scripts" / "manage_release_environment.py"
SERVICE_TEMPLATE = REPO_ROOT / "scripts" / "webchat.service"


class ReleaseVerificationTests(unittest.TestCase):
    def test_model_check_uses_cpu_and_expected_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture_dir = Path(tmp)
            cache_dir = fixture_dir / "cache"
            (fixture_dir / "sentence_transformers.py").write_text(
                """
import os

class _Device:
    type = "cpu"

class _Embedding:
    shape = (1, 384)

class SentenceTransformer:
    def __init__(self, model, device):
        assert model == "sentence-transformers/all-MiniLM-L6-v2"
        assert device == "cpu"
        assert os.environ["HF_HOME"] == os.environ["EXPECTED_HF_HOME"]
        self.device = _Device()

    def encode(self, values):
        assert values == ["production CPU smoke test"]
        return _Embedding()
""",
                encoding="utf-8",
            )
            env = os.environ.copy()
            env["PYTHONPATH"] = str(fixture_dir)
            env["EXPECTED_HF_HOME"] = str(cache_dir.resolve())

            result = subprocess.run(
                [
                    sys.executable,
                    str(VERIFY_RELEASE),
                    "model",
                    "--cache-dir",
                    str(cache_dir),
                ],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("CPU model verification passed", result.stdout)

    def test_backend_import_check_imports_requested_module(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture_dir = Path(tmp)
            (fixture_dir / "verification_fixture.py").write_text(
                "VERIFIED = True\n", encoding="utf-8"
            )
            env = os.environ.copy()
            env["PYTHONPATH"] = str(fixture_dir)

            result = subprocess.run(
                [
                    sys.executable,
                    str(VERIFY_RELEASE),
                    "backend-import",
                    "--module",
                    "verification_fixture",
                ],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("verification_fixture", result.stdout)

    def _run_frontend_entry(self, html: str, expected: str) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as tmp:
            index = Path(tmp) / "index.html"
            index.write_text(html, encoding="utf-8")
            return subprocess.run(
                [
                    sys.executable,
                    str(VERIFY_RELEASE),
                    "frontend-entry",
                    "--url",
                    index.resolve().as_uri(),
                    "--expected-script",
                    expected,
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

    def test_frontend_entry_accepts_page_referencing_expected_bundle(self) -> None:
        result = self._run_frontend_entry(
            '<script type="module" crossorigin src="/assets/index-JNY7hdXb.js"></script>',
            "index-JNY7hdXb.js",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("index-JNY7hdXb.js", result.stdout)

    def test_frontend_entry_rejects_stale_bundle(self) -> None:
        result = self._run_frontend_entry(
            '<script type="module" crossorigin src="/assets/index-CuA7AIXC.js"></script>',
            "index-JNY7hdXb.js",
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("index-CuA7AIXC.js", result.stderr)


class ServiceRendererTests(unittest.TestCase):
    def test_renders_validated_service_unit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "webchat.service"

            result = subprocess.run(
                [
                    sys.executable,
                    str(RENDER_SERVICE),
                    "--template",
                    str(SERVICE_TEMPLATE),
                    "--output",
                    str(output),
                    "--deploy-user",
                    "admin",
                    "--deploy-dir",
                    "/home/admin/deployments/template-webchat",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            rendered = output.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("User=admin", rendered)
        self.assertIn(
            "WorkingDirectory=/home/admin/deployments/template-webchat", rendered
        )
        self.assertNotIn("<deploy-", rendered)

    def test_unit_executes_only_the_rename_safe_interpreter(self) -> None:
        template = SERVICE_TEMPLATE.read_text(encoding="utf-8")

        exec_lines = [
            line
            for line in template.splitlines()
            if line.startswith(("ExecStart", "ExecStop", "ExecReload"))
        ]

        self.assertTrue(exec_lines)
        for line in exec_lines:
            command = line.split("=", 1)[1].strip().lstrip("-@:+!")
            self.assertTrue(
                command.startswith("<deploy-dir>/.venv/bin/python"),
                "Unit must exec .venv/bin/python (a rename-safe symlink); "
                "console scripts break after transactional activation "
                f"renames the release environment: {line}",
            )

    def test_rejects_relative_deploy_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [
                    sys.executable,
                    str(RENDER_SERVICE),
                    "--template",
                    str(SERVICE_TEMPLATE),
                    "--output",
                    str(Path(tmp) / "webchat.service"),
                    "--deploy-user",
                    "admin",
                    "--deploy-dir",
                    "relative/path",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("absolute", result.stderr)


class ReleaseEnvironmentTests(unittest.TestCase):
    def test_activate_then_rollback_restores_previous_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            active = root / ".venv"
            release = root / ".venv.release-new"
            rollback = root / ".venv.rollback-old"
            failed = root / ".venv.failed-new"
            active.mkdir()
            release.mkdir()
            (active / "identity").write_text("old", encoding="utf-8")
            (release / "identity").write_text("new", encoding="utf-8")

            activate = subprocess.run(
                [
                    sys.executable,
                    str(MANAGE_ENVIRONMENT),
                    "activate",
                    "--active",
                    str(active),
                    "--release",
                    str(release),
                    "--rollback",
                    str(rollback),
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            restore = subprocess.run(
                [
                    sys.executable,
                    str(MANAGE_ENVIRONMENT),
                    "rollback",
                    "--active",
                    str(active),
                    "--rollback",
                    str(rollback),
                    "--failed",
                    str(failed),
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            active_identity = (active / "identity").read_text(encoding="utf-8")
            failed_identity = (failed / "identity").read_text(encoding="utf-8")

        self.assertEqual(activate.returncode, 0, activate.stderr)
        self.assertEqual(restore.returncode, 0, restore.stderr)
        self.assertEqual(active_identity, "old")
        self.assertEqual(failed_identity, "new")

    def test_rollback_before_activation_is_safe_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            active = root / ".venv"
            active.mkdir()
            (active / "identity").write_text("old", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(MANAGE_ENVIRONMENT),
                    "rollback",
                    "--active",
                    str(active),
                    "--rollback",
                    str(root / ".venv.rollback-old"),
                    "--failed",
                    str(root / ".venv.failed-new"),
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            identity = (active / "identity").read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(identity, "old")
        self.assertIn("nothing to restore", result.stdout)


class PruneEnvironmentTests(unittest.TestCase):
    def _venv(self, root: Path, name: str, created: int) -> Path:
        path = root / name
        path.mkdir()
        cfg = path / "pyvenv.cfg"
        cfg.write_text("home = /usr/bin\n", encoding="utf-8")
        os.utime(cfg, (created, created))
        return path

    def _prune(self, root: Path, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                sys.executable,
                str(MANAGE_ENVIRONMENT),
                "prune",
                "--active",
                str(root / ".venv"),
                "--keep-rollback",
                "1",
                *extra,
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def _layout(self, root: Path) -> None:
        self._venv(root, ".venv", 500)
        self._venv(root, ".venv.rollback-oldest", 100)
        self._venv(root, ".venv.rollback-middle", 200)
        self._venv(root, ".venv.rollback-newest", 300)
        self._venv(root, ".venv.failed-bad", 400)
        self._venv(root, ".venv.release-inflight", 600)
        (root / ".venv.rollback-link").symlink_to(root / ".venv")

    def test_prune_keeps_newest_rollback_and_protected_environments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._layout(root)

            result = self._prune(root)
            remaining = sorted(p.name for p in root.iterdir())

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            remaining,
            [
                ".venv",
                ".venv.release-inflight",
                ".venv.rollback-link",
                ".venv.rollback-newest",
            ],
        )
        self.assertIn(".venv.rollback-oldest", result.stdout)

    def test_prune_dry_run_deletes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._layout(root)
            before = sorted(p.name for p in root.iterdir())

            result = self._prune(root, "--dry-run")
            after = sorted(p.name for p in root.iterdir())

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(before, after)
        self.assertIn("would delete", result.stdout)
        self.assertIn(".venv.failed-bad", result.stdout)

    def test_prune_requires_active_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._venv(root, ".venv.rollback-only", 100)

            result = self._prune(root)
            still_there = (root / ".venv.rollback-only").is_dir()

        self.assertEqual(result.returncode, 1)
        self.assertTrue(still_there)


if __name__ == "__main__":
    unittest.main()
