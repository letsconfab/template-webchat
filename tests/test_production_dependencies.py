"""Black-box tests for the production dependency preflight."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts import check_production_dependencies

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER = REPO_ROOT / "scripts" / "check_production_dependencies.py"


class ProductionDependencyCheckTests(unittest.TestCase):
    def _wheel(self, directory: Path, name: str, installed_bytes: int = 16) -> None:
        with zipfile.ZipFile(directory / name, "w") as wheel:
            wheel.writestr("package/payload.bin", b"x" * installed_bytes)

    def _run(self, wheel_dir: Path, budget_bytes: int = 1024) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(CHECKER),
                "--wheel-dir",
                str(wheel_dir),
                "--budget-bytes",
                str(budget_bytes),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_accepts_cpu_only_torch_within_storage_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wheel_dir = Path(tmp)
            self._wheel(wheel_dir, "torch-2.10.0+cpu-cp313-cp313-manylinux_2_28_x86_64.whl")
            self._wheel(wheel_dir, "sentence_transformers-5.2.2-py3-none-any.whl")

            result = self._run(wheel_dir)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("CPU-only Torch", result.stdout)

    def test_resolution_bootstraps_pip_in_disposable_virtualenv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wheel_dir = Path(tmp) / "wheels"
            with patch.object(
                check_production_dependencies.subprocess, "run"
            ) as run:
                check_production_dependencies.resolve_wheels(wheel_dir)

        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(commands[0][:3], [sys.executable, "-m", "venv"])
        self.assertNotEqual(commands[1][0], sys.executable)
        self.assertEqual(commands[1][1:4], ["-m", "pip", "download"])

    def test_rejects_gpu_runtime_packages_with_actionable_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wheel_dir = Path(tmp)
            self._wheel(wheel_dir, "torch-2.10.0+cpu-cp313-cp313-manylinux_2_28_x86_64.whl")
            self._wheel(wheel_dir, "nvidia_cublas_cu12-12.8.4.1-py3-none-manylinux.whl")

            result = self._run(wheel_dir)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("GPU runtime packages", result.stderr)
        self.assertIn("nvidia-cublas-cu12", result.stderr)

    def test_rejects_resolved_install_larger_than_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wheel_dir = Path(tmp)
            self._wheel(
                wheel_dir,
                "torch-2.10.0+cpu-cp313-cp313-manylinux_2_28_x86_64.whl",
                installed_bytes=2048,
            )

            result = self._run(wheel_dir, budget_bytes=1024)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exceeds the production dependency budget", result.stderr)


if __name__ == "__main__":
    unittest.main()
