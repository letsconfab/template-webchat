"""Black-box test for the standalone feedback backfill entry point."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MIGRATE = ROOT / "scripts" / "migrate.py"
BACKFILL = ROOT / "scripts" / "backfill_feedback_cases.py"


class BackfillScriptTests(unittest.TestCase):
    def test_script_runs_standalone_against_migrated_database(self) -> None:
        """The script must register all models itself; it once crashed with an
        unresolved 'User' relationship when imported without the app."""
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "backfill.db"
            env = os.environ.copy()
            env["DATABASE_URL"] = f"sqlite+aiosqlite:///{database}"

            migrate = subprocess.run(
                [sys.executable, str(MIGRATE), "upgrade"],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            result = subprocess.run(
                [sys.executable, str(BACKFILL)],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(migrate.returncode, 0, migrate.stderr)
            self.assertEqual(result.returncode, 0, result.stderr)
            counts = json.loads(result.stdout.strip().splitlines()[-1])
            self.assertEqual(counts.get("pending", 0), 0)


if __name__ == "__main__":
    unittest.main()
