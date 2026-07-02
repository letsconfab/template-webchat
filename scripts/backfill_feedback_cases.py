#!/usr/bin/env python3
"""Run the resumable Feedback Case ownership/redaction backfill."""

import asyncio
import json

from backend.database import AsyncSessionLocal
from backend.services.feedback_backfill import run_feedback_backfill


async def main() -> None:
    counts = await run_feedback_backfill(AsyncSessionLocal)
    print(json.dumps(counts, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())

