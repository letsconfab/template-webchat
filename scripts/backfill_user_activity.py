#!/usr/bin/env python3
"""Run the resumable inferred_last_activity_at backfill."""

import asyncio
import json
from pathlib import Path
import sys

repo = str(Path(__file__).resolve().parents[1])
if repo not in sys.path:
    sys.path.insert(0, repo)

# Import every model module so string relationship targets resolve before the
# first mapper is configured.
from backend.models import (  # noqa: F401
    chat,
    diagnostics,
    feedback_case,
    invite,
    settings,
    user,
    wiki,
)

from backend.database import AsyncSessionLocal
from backend.services.user_activity_backfill import run_user_activity_backfill


async def main() -> None:
    counts = await run_user_activity_backfill(AsyncSessionLocal)
    print(json.dumps(counts, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
