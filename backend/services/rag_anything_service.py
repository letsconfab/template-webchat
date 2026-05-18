"""Client wrapper for the separate RAG-Anything service container."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class RAGAnythingService:
    """HTTP client for the external RAG-Anything service."""

    def __init__(self) -> None:
        self.base_url = os.getenv("RAG_SERVICE_URL", "http://localhost:8010").rstrip(
            "/"
        )
        self.timeout = float(os.getenv("RAG_SERVICE_TIMEOUT", "180"))
        self.is_initialized = False
        self._last_config: Dict[str, Any] = {}

    def _normalize_base_url(self, provider: str, base_url: Optional[str]) -> str:
        if base_url:
            return base_url.rstrip("/")
        if provider == "groq":
            return "https://api.groq.com/openai/v1"
        if provider == "ollama":
            return "http://host.docker.internal:11434/v1"
        if provider == "sarvam":
            return "https://api.sarvam.ai/v1"
        return "https://api.openai.com/v1"

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(timeout=timeout or self.timeout) as client:
            response = await client.request(
                method,
                url,
                json=json_data,
                files=files,
                data=data,
            )
        response.raise_for_status()
        if response.content:
            return response.json()
        return {}

    async def health(self) -> bool:
        try:
            data = await self._request("GET", "/health", timeout=5.0)
            return data.get("status") == "healthy" and data.get("ready", False)
        except Exception as exc:
            logger.debug("RAG-Anything health check failed: %s", exc)
            return False

    async def status(self) -> Dict[str, Any]:
        try:
            return await self._request("GET", "/status", timeout=5.0)
        except Exception as exc:
            logger.debug("RAG-Anything status check failed: %s", exc)
            return {
                "initialized": self.is_initialized,
                "base_url": self.base_url,
                "error": str(exc),
            }

    async def sync_from_settings(self, settings: Any) -> Dict[str, Any]:
        provider = getattr(settings, "rag_provider", None) or getattr(
            settings, "llm_provider", None
        ) or "openai"
        model = getattr(settings, "rag_model", None) or getattr(
            settings, "llm_model", None
        ) or "gpt-4o-mini"
        api_key = getattr(settings, "rag_api_key", None)
        if api_key is None:
            api_key = getattr(settings, "llm_api_key", None)
        base_url = getattr(settings, "rag_base_url", None)
        payload = {
            "provider": provider,
            "model": model,
            "api_key": api_key or "",
            "base_url": self._normalize_base_url(provider, base_url),
        }
        return await self.initialize(**payload)

    async def initialize(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        llm_model: str = "gpt-4o",
        embedding_model: str = "text-embedding-3-large",
        provider: str = "openai",
    ) -> Dict[str, Any]:
        """Sync the configured settings to the container."""
        return await self.sync_config(
            provider=provider,
            model=llm_model,
            api_key=api_key,
            base_url=base_url,
            embedding_model=embedding_model,
        )

    async def sync_config(
        self,
        *,
        provider: str,
        model: str,
        api_key: str,
        base_url: str,
        embedding_model: str = "fastembed",
    ) -> Dict[str, Any]:
        payload = {
            "provider": provider,
            "model": model,
            "api_key": api_key,
            "base_url": base_url,
            "embedding_model": embedding_model,
        }
        try:
            data = await self._request("POST", "/config/sync", json_data=payload)
            self._last_config = payload
            self.is_initialized = bool(data.get("initialized", False))
            return {"success": True, **data}
        except Exception as exc:
            self.is_initialized = False
            logger.error("Failed to sync RAG-Anything config: %s", exc)
            return {"success": False, "error": str(exc)}

    async def ingest_file(
        self,
        file_path: str,
        *,
        source_name: Optional[str] = None,
        parse_method: str = "auto",
    ) -> Dict[str, Any]:
        if not self.is_initialized:
            return {"success": False, "error": "RAG-Anything not initialized"}

        path = Path(file_path)
        try:
            content = await asyncio.to_thread(path.read_bytes)
            files = {
                "file": (
                    source_name or path.name,
                    content,
                    "application/octet-stream",
                )
            }
            data = {
                "parse_method": parse_method,
                "source_name": source_name or path.name,
            }
            result = await self._request(
                "POST",
                "/ingest",
                files=files,
                data=data,
            )
            return {"success": True, "result": result}
        except Exception as exc:
            logger.error("RAG-Anything ingest_file failed: %s", exc)
            return {"success": False, "error": str(exc)}

    async def ingest_markdown(
        self,
        title: str,
        content: str,
        *,
        source_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.is_initialized:
            return {"success": False, "error": "RAG-Anything not initialized"}

        payload = {
            "title": title,
            "content": content,
            "source_name": source_name or f"{title}.md",
        }
        try:
            result = await self._request("POST", "/ingest-markdown", json_data=payload)
            return {"success": True, "result": result}
        except Exception as exc:
            logger.error("RAG-Anything ingest_markdown failed: %s", exc)
            return {"success": False, "error": str(exc)}

    async def query(
        self,
        query_text: str,
        mode: str = "hybrid",
    ) -> Dict[str, Any]:
        if not self.is_initialized:
            return {"success": False, "error": "RAG-Anything not initialized"}

        try:
            result = await self._request(
                "POST",
                "/query",
                json_data={"query_text": query_text, "mode": mode},
            )
            answer = result.get("result")
            if answer is None:
                answer = result.get("answer", "")
            return {
                "success": True,
                "result": answer,
                "raw_result": result.get("raw_result", answer),
                "mode": result.get("mode", mode),
            }
        except Exception as exc:
            logger.error("RAG-Anything query failed: %s", exc)
            return {"success": False, "error": str(exc)}

    async def query_multimodal(
        self,
        query_text: str,
        multimodal_content: List[Dict[str, Any]],
        mode: str = "hybrid",
    ) -> Dict[str, Any]:
        if not self.is_initialized:
            return {"success": False, "error": "RAG-Anything not initialized"}

        try:
            result = await self._request(
                "POST",
                "/query-multimodal",
                json_data={
                    "query_text": query_text,
                    "multimodal_content": multimodal_content,
                    "mode": mode,
                },
            )
            answer = result.get("result")
            if answer is None:
                answer = result.get("answer", "")
            return {
                "success": True,
                "result": answer,
                "raw_result": result.get("raw_result", answer),
                "mode": result.get("mode", mode),
            }
        except Exception as exc:
            logger.error("RAG-Anything multimodal query failed: %s", exc)
            return {"success": False, "error": str(exc)}

    async def reindex_markdown(
        self,
        title: str,
        content: str,
        *,
        source_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.is_initialized:
            return {"success": False, "error": "RAG-Anything not initialized"}

        try:
            result = await self._request(
                "POST",
                "/reindex",
                json_data={
                    "title": title,
                    "content": content,
                    "source_name": source_name or f"{title}.md",
                },
            )
            return {"success": True, "result": result}
        except Exception as exc:
            logger.error("RAG-Anything reindex failed: %s", exc)
            return {"success": False, "error": str(exc)}

    async def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        result = await self.query(query, mode="hybrid")
        if result.get("success"):
            return [{"content": result.get("result", ""), "score": 1.0}]
        return []


rag_anything_service = RAGAnythingService()
