#!/usr/bin/env python3
"""Safely stamp the legacy current schema or upgrade a managed database."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from dotenv import load_dotenv
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine


ROOT = Path(__file__).resolve().parents[1]
ENV_FILE_VARIABLE = "MIGRATE_ENV_FILE"
LEGACY_BASELINE = "0001_current_schema"
CURRENT_SCHEMA_TABLES = {
    "users",
    "system_settings",
    "invites",
    "wiki_pages",
    "wiki_versions",
    "knowledge_insights",
    "chat_messages",
    "user_feedback",
}


def alembic_config() -> Config:
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "alembic"))
    return config


def database_url() -> str:
    """Resolve DATABASE_URL from the environment or the repository .env.

    Deployment entry points invoke this script directly, without the
    application settings module, so the checkout .env must be loaded here.
    An already-exported DATABASE_URL always wins over the file.
    """
    load_dotenv(os.environ.get(ENV_FILE_VARIABLE, ROOT / ".env"))
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            f"DATABASE_URL is not set in the environment or in {ROOT / '.env'}"
        )
    return url


async def get_table_names(database_url: str) -> set[str]:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            return set(
                await connection.run_sync(
                    lambda sync_connection: inspect(sync_connection).get_table_names()
                )
            )
    finally:
        await engine.dispose()


async def get_current_revision(database_url: str) -> str | None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            return await connection.run_sync(
                lambda sync_connection: MigrationContext.configure(
                    sync_connection
                ).get_current_revision()
            )
    finally:
        await engine.dispose()


def upgrade() -> None:
    url = database_url()
    tables = asyncio.run(get_table_names(url))
    config = alembic_config()

    if "alembic_version" in tables:
        command.upgrade(config, "head")
        return

    application_tables = tables.intersection(CURRENT_SCHEMA_TABLES)
    if not application_tables:
        command.upgrade(config, "head")
        return

    missing = CURRENT_SCHEMA_TABLES - tables
    if missing:
        names = ", ".join(sorted(missing))
        raise RuntimeError(
            "Database is neither empty nor the supported current schema; "
            f"missing tables: {names}"
        )

    print("Detected current pre-Alembic schema; stamping baseline without data changes.")
    command.stamp(config, LEGACY_BASELINE)
    command.upgrade(config, "head")


def current() -> None:
    config = alembic_config()
    expected_heads = set(ScriptDirectory.from_config(config).get_heads())
    revision = asyncio.run(get_current_revision(database_url()))
    if revision not in expected_heads:
        raise RuntimeError(
            f"Database revision {revision or 'none'} is not at head "
            f"({', '.join(sorted(expected_heads))})"
        )
    print(f"{revision} (head)")


def check() -> None:
    """Prove environment loading and database connectivity without mutating.

    Succeeds at any revision, including a pre-Alembic database, so it can run
    before the first upgrade to validate the full execution path.
    """
    config = alembic_config()
    heads = ", ".join(sorted(ScriptDirectory.from_config(config).get_heads()))
    revision = asyncio.run(get_current_revision(database_url()))
    print(f"database revision: {revision or 'none'}; script head: {heads}")


def main() -> int:
    if sys.version_info[:2] != (3, 13):
        print(
            f"Migration failed: Python 3.13 is required, got "
            f"{sys.version_info.major}.{sys.version_info.minor}",
            file=sys.stderr,
        )
        return 1

    action = sys.argv[1] if len(sys.argv) > 1 else "upgrade"
    try:
        if action == "upgrade":
            upgrade()
        elif action == "current":
            current()
        elif action == "check":
            check()
        else:
            raise ValueError(f"Unknown action: {action}")
    except Exception as error:
        print(f"Migration failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
