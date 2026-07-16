#!/usr/bin/env python3
"""Report email_canonical collisions before migration 0009.

Run this before upgrading. Collisions must be resolved by hand; the migration
refuses to proceed rather than silently picking a winner.

Exit codes:
  0 — no collisions
  1 — collisions found (or query failure)
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import text

repo = str(Path(__file__).resolve().parents[1])
if repo not in sys.path:
    sys.path.insert(0, repo)

from backend.database import engine  # noqa: E402


def _collision_sql(table: str, *, pending_only: bool, dialect: str) -> str:
    id_agg = "string_agg(id::text, ',')" if dialect == "postgresql" else "GROUP_CONCAT(id)"
    email_agg = (
        "string_agg(email, ',')" if dialect == "postgresql" else "GROUP_CONCAT(email)"
    )
    where = "WHERE status = 'pending'" if pending_only else ""
    return f"""
        SELECT lower(trim(email)) AS canonical,
               COUNT(*) AS n,
               {id_agg} AS ids,
               {email_agg} AS emails
        FROM {table}
        {where}
        GROUP BY lower(trim(email))
        HAVING COUNT(*) > 1
    """


async def find_collisions() -> dict:
    """Return collision groups for users and pending invites."""
    async with engine.connect() as conn:
        dialect = conn.dialect.name
        users = (
            await conn.execute(
                text(_collision_sql("users", pending_only=False, dialect=dialect))
            )
        ).mappings().all()
        pending = (
            await conn.execute(
                text(
                    _collision_sql("invites", pending_only=True, dialect=dialect)
                )
            )
        ).mappings().all()

    return {
        "user_collisions": [dict(row) for row in users],
        "pending_invite_collisions": [dict(row) for row in pending],
    }


async def main() -> int:
    report = await find_collisions()
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["user_collisions"] or report["pending_invite_collisions"]:
        print(
            "Collisions found. Resolve by hand before running migration 0009.",
            file=sys.stderr,
        )
        return 1
    print("No email_canonical collisions.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
