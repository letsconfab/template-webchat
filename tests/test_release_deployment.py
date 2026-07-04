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


if __name__ == "__main__":
    unittest.main()
