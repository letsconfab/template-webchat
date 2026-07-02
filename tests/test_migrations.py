"""Black-box tests for the supported database migration command."""

from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MIGRATE = ROOT / "scripts" / "migrate.py"
EXPECTED_HEAD = "0007_rollout_flags"


class MigrationCommandTests(unittest.TestCase):
    def run_migrate(self, database: Path) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["DATABASE_URL"] = f"sqlite+aiosqlite:///{database}"
        return subprocess.run(
            [sys.executable, str(MIGRATE), "upgrade"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    @staticmethod
    def revision(database: Path) -> str | None:
        with sqlite3.connect(database) as connection:
            row = connection.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone()
        return row[0] if row else None

    def test_fresh_database_upgrades_to_head(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "fresh.db"

            result = self.run_migrate(database)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.revision(database), EXPECTED_HEAD)

    def test_existing_current_schema_is_stamped_without_data_loss(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "existing.db"
            env = os.environ.copy()
            env["DATABASE_URL"] = f"sqlite+aiosqlite:///{database}"
            baseline = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "alembic",
                    "upgrade",
                    "0001_current_schema",
                ],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(baseline.returncode, 0, baseline.stderr)
            with sqlite3.connect(database) as connection:
                connection.execute("DROP TABLE alembic_version")
                connection.execute(
                    """
                    INSERT INTO users (
                        email, password_hash, role, is_active, created_at, updated_at
                    ) VALUES (
                        'kept@example.test', 'hash', 'user', 1,
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                )

            result = self.run_migrate(database)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.revision(database), EXPECTED_HEAD)
            with sqlite3.connect(database) as connection:
                email = connection.execute("SELECT email FROM users").fetchone()[0]
                chat_sessions = connection.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'table' AND name = 'chat_sessions'"
                ).fetchone()
            self.assertEqual(email, "kept@example.test")
            self.assertIsNotNone(chat_sessions)

    def test_upgrade_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "repeat.db"

            first = self.run_migrate(database)
            second = self.run_migrate(database)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(self.revision(database), EXPECTED_HEAD)

    def test_migration_failure_is_reported(self) -> None:
        env = os.environ.copy()
        env["DATABASE_URL"] = "not-a-database-url"

        result = subprocess.run(
            [sys.executable, str(MIGRATE), "upgrade"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Migration failed", result.stderr)


if __name__ == "__main__":
    unittest.main()
