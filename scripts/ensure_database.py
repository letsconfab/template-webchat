#!/usr/bin/env python3
"""Create the configured Postgres database if it does not already exist."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import asyncpg


def load_dotenv_like(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


def database_url() -> str:
    load_dotenv_like(Path(".env"))
    return os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/webchat_db",
    )


def parse_database_url(raw_url: str) -> tuple[str, str, str, str, int]:
    parsed = urlparse(raw_url)
    if parsed.scheme.startswith("postgresql+"):
        scheme = "postgresql"
    else:
        scheme = parsed.scheme

    if scheme not in {"postgresql", "postgres"}:
        raise ValueError(f"Unsupported DATABASE_URL scheme: {parsed.scheme}")

    if not parsed.hostname:
        raise ValueError("DATABASE_URL is missing a host")

    if not parsed.path or parsed.path == "/":
        raise ValueError("DATABASE_URL is missing a database name")

    db_name = parsed.path.lstrip("/")
    port = parsed.port or 5432
    user = parsed.username or "postgres"
    password = parsed.password or ""
    return parsed.hostname, user, password, db_name, port


async def ensure_database_exists(
    host: str,
    port: int,
    user: str,
    password: str,
    db_name: str,
) -> None:
    conn = await asyncpg.connect(
        host=host,
        port=port,
        user=user,
        password=password or None,
        database="postgres",
    )
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            db_name,
        )
        if exists:
            print(f"Database '{db_name}' already exists on {host}:{port}.")
            return

        quoted_db_name = db_name.replace('"', '""')
        await conn.execute(f'CREATE DATABASE "{quoted_db_name}"')
        print(f"Created database '{db_name}' on {host}:{port}.")
    finally:
        await conn.close()


def main() -> int:
    raw_url = database_url()
    host, user, password, db_name, port = parse_database_url(raw_url)
    try:
        asyncio.run(ensure_database_exists(host, port, user, password, db_name))
        return 0
    except (OSError, asyncpg.PostgresError) as exc:
        print(
            f"Failed to create database '{db_name}' on {host}:{port}.\n{exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
