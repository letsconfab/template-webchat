"""Manages the CocoIndex pipeline lifecycle as a background task."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Optional

import cocoindex as coco

from backend.services.cocoindex_pipeline import build_pipeline

logger = logging.getLogger(__name__)


class CocoIndexManager:
    """Start/stop/monitor the CocoIndex indexing pipeline."""

    def __init__(self) -> None:
        self._app: Optional[coco.App] = None
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self.last_update: Optional[datetime] = None
        self.error: Optional[str] = None
        self.file_count: int = 0

    @property
    def is_running(self) -> bool:
        return self._running

    def configure(
        self,
        cache_dir: str,
        neo4j_uri: str,
        neo4j_user: str,
        neo4j_password: str,
        neo4j_database: str,
        qdrant_url: str,
        embedding_model: str,
        llm_provider: str,
        llm_model: str,
        llm_api_key: str,
    ) -> None:
        os.environ.setdefault("COCOINDEX_DB", os.path.join(cache_dir, "cocoindex_db"))
        self._app = build_pipeline(
            cache_dir=cache_dir,
            neo4j_uri=neo4j_uri,
            neo4j_user=neo4j_user,
            neo4j_password=neo4j_password,
            neo4j_database=neo4j_database,
            qdrant_url=qdrant_url,
            embedding_model=embedding_model,
            llm_provider=llm_provider,
            llm_model=llm_model,
            llm_api_key=llm_api_key,
        )

    async def start(self) -> None:
        if not self._app:
            logger.error("CocoIndexManager: pipeline not configured, call configure() first")
            return
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("CocoIndex pipeline started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("CocoIndex pipeline stopped")

    async def _run_loop(self) -> None:
        while self._running:
            try:
                await self._app.update()
                self.last_update = datetime.utcnow()
                self.error = None
                logger.debug("CocoIndex pipeline update complete")
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.error = str(e)
                logger.error("CocoIndex pipeline error: %s", e)
            await asyncio.sleep(30)

    def get_status(self) -> dict:
        return {
            "running": self._running,
            "last_update": self.last_update.isoformat() if self.last_update else None,
            "error": self.error,
        }


cocoindex_manager = CocoIndexManager()
