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
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine


ROOT = Path(__file__).resolve().parents[1]
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
    database_url = os.environ["DATABASE_URL"]
    tables = asyncio.run(get_table_names(database_url))
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
    command.stamp(config, "head")


def current() -> None:
    config = alembic_config()
    expected_heads = set(ScriptDirectory.from_config(config).get_heads())
    revision = asyncio.run(get_current_revision(os.environ["DATABASE_URL"]))
    if revision not in expected_heads:
        raise RuntimeError(
            f"Database revision {revision or 'none'} is not at head "
            f"({', '.join(sorted(expected_heads))})"
        )
    print(f"{revision} (head)")


def main() -> int:
    if sys.version_info[:2] != (3, 11):
        print(
            f"Migration failed: Python 3.11 is required, got "
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
        else:
            raise ValueError(f"Unknown action: {action}")
    except Exception as error:
        print(f"Migration failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
