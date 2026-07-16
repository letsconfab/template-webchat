#!/usr/bin/env python3
"""Global bulk-invite SMTP worker (separate from the web process).

Exactly one consumer should run. The worker holds a process-local start_once()
guard and paces sends globally across all batches.

  .venv/bin/python scripts/invite_worker.py
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path

repo = str(Path(__file__).resolve().parents[1])
if repo not in sys.path:
    sys.path.insert(0, repo)

from backend.models import (  # noqa: F401
    bulk_invite,
    chat,
    diagnostics,
    feedback_case,
    invite,
    settings,
    user,
    wiki,
)
from backend.database import AsyncSessionLocal
from backend.services.bulk_invites import BulkInviteWorker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("invite_worker")


async def main() -> None:
    worker = BulkInviteWorker(AsyncSessionLocal)
    if not worker.start_once():
        logger.error("Worker already started in this process")
        sys.exit(1)

    loop = asyncio.get_running_loop()
    stop = asyncio.Event()

    def _request_stop() -> None:
        logger.info("Shutdown signal received; finishing in-flight work")
        stop.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:
            signal.signal(sig, lambda *_: _request_stop())

    logger.info("Bulk invite worker started id=%s", worker.worker_id)
    await stop.wait()
    await worker.stop()
    logger.info("Bulk invite worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
