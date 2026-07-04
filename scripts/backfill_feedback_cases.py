#!/usr/bin/env python3
"""Run the resumable Feedback Case ownership/redaction backfill."""

import asyncio
import json
from pathlib import Path
import sys

repo = str(Path(__file__).resolve().parents[1])
if repo not in sys.path:
    sys.path.insert(0, repo)

# Import every model module so string relationship targets (e.g. "User")
# resolve before the first mapper is configured; importing the backfill
# service alone leaves the registry incomplete.
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
from backend.services.feedback_backfill import run_feedback_backfill


async def main() -> None:
    counts = await run_feedback_backfill(AsyncSessionLocal)
    print(json.dumps(counts, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())

