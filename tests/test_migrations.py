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
    def run_migrate(
        self,
        database: Path,
        action: str = "upgrade",
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["DATABASE_URL"] = f"sqlite+aiosqlite:///{database}"
        return subprocess.run(
            [sys.executable, str(MIGRATE), action],
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

    def test_current_reports_head_after_upgrade(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "current.db"
            upgrade = self.run_migrate(database)

            current = self.run_migrate(database, "current")

            self.assertEqual(upgrade.returncode, 0, upgrade.stderr)
            self.assertEqual(current.returncode, 0, current.stderr)
            self.assertIn(f"{EXPECTED_HEAD} (head)", current.stdout)

    def run_migrate_with_env(
        self,
        env: dict[str, str],
        action: str = "upgrade",
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(MIGRATE), action],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_upgrade_loads_database_url_from_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "dotenv.db"
            env_file = Path(directory) / ".env"
            env_file.write_text(
                f"DATABASE_URL=sqlite+aiosqlite:///{database}\n",
                encoding="utf-8",
            )
            env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
            env["MIGRATE_ENV_FILE"] = str(env_file)

            result = self.run_migrate_with_env(env)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.revision(database), EXPECTED_HEAD)

    def test_environment_variable_overrides_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            exported = Path(directory) / "exported.db"
            from_file = Path(directory) / "from-file.db"
            env_file = Path(directory) / ".env"
            env_file.write_text(
                f"DATABASE_URL=sqlite+aiosqlite:///{from_file}\n",
                encoding="utf-8",
            )
            env = os.environ.copy()
            env["DATABASE_URL"] = f"sqlite+aiosqlite:///{exported}"
            env["MIGRATE_ENV_FILE"] = str(env_file)

            result = self.run_migrate_with_env(env)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.revision(exported), EXPECTED_HEAD)
            self.assertFalse(from_file.exists())

    def test_missing_database_url_reports_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
            env["MIGRATE_ENV_FILE"] = str(Path(directory) / "absent.env")

            result = self.run_migrate_with_env(env)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("DATABASE_URL is not set", result.stderr)

    def test_check_succeeds_before_and_after_upgrade(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "check.db"

            before = self.run_migrate(database, "check")
            upgrade = self.run_migrate(database)
            after = self.run_migrate(database, "check")

            self.assertEqual(before.returncode, 0, before.stderr)
            self.assertIn("database revision: none", before.stdout)
            self.assertEqual(upgrade.returncode, 0, upgrade.stderr)
            self.assertEqual(after.returncode, 0, after.stderr)
            self.assertIn(f"database revision: {EXPECTED_HEAD}", after.stdout)

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
