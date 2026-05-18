"""Standalone RAG-Anything service container."""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


class SyncConfigRequest(BaseModel):
    provider: str = Field(default="openai")
    model: str = Field(default="gpt-4o-mini")
    api_key: str = Field(default="")
    base_url: str = Field(default="https://api.openai.com/v1")
    embedding_model: str = Field(default="fastembed")
    parser: str = Field(default="mineru")
    parse_method: str = Field(default="auto")


class QueryRequest(BaseModel):
    query_text: str
    mode: str = "hybrid"


class QueryMultimodalRequest(BaseModel):
    query_text: str
    multimodal_content: List[Dict[str, Any]]
    mode: str = "hybrid"


class MarkdownIngestRequest(BaseModel):
    title: str
    content: str
    source_name: Optional[str] = None


class RAGRuntime:
    def __init__(self) -> None:
        self.workdir = Path(os.getenv("RAG_WORKDIR", "/data/rag")).resolve()
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.upload_dir = self.workdir / "uploads"
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir = self.workdir / "tmp"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.initialized = False
        self.last_config: Dict[str, Any] = {}
        self.rag = None
        self.capabilities = {
            "image_processing": True,
            "table_processing": True,
            "equation_processing": True,
            "markdown_ingest": True,
            "document_ingest": True,
            "multimodal_query": True,
        }

    def _build_base_url(self, provider: str, base_url: Optional[str]) -> str:
        if base_url:
            return base_url.rstrip("/")
        if provider == "groq":
            return "https://api.groq.com/openai/v1"
        if provider == "ollama":
            return "http://host.docker.internal:11434/v1"
        if provider == "sarvam":
            return "https://api.sarvam.ai/v1"
        return "https://api.openai.com/v1"

    async def _create_runtime(
        self,
        provider: str,
        model: str,
        api_key: str,
        base_url: str,
        embedding_model: str,
        parser: str,
        parse_method: str,
    ) -> None:
        from langchain_community.embeddings import FastEmbedEmbeddings
        from raganything import RAGAnything, RAGAnythingConfig
        from lightrag.llm.openai import openai_complete_if_cache

        embed_dir = self.workdir / "embeddings"
        embed_dir.mkdir(parents=True, exist_ok=True)
        embedder = FastEmbedEmbeddings(cache_dir=str(embed_dir))

        config = RAGAnythingConfig(
            working_dir=str(self.workdir),
            parser=parser,
            parse_method=parse_method,
            enable_image_processing=True,
            enable_table_processing=True,
            enable_equation_processing=True,
        )

        def llm_model_func(
            prompt: str,
            system_prompt: Optional[str] = None,
            history_messages: Optional[List[Dict]] = None,
            **kwargs,
        ):
            return openai_complete_if_cache(
                model=model,
                api_key=api_key,
                base_url=base_url,
                prompt=prompt,
                system_prompt=system_prompt,
                history_messages=history_messages or [],
                **kwargs,
            )

        def vision_model_func(
            prompt: str,
            image_data: Optional[str] = None,
            system_prompt: Optional[str] = None,
            history_messages: Optional[List[Dict]] = None,
            **kwargs,
        ):
            return openai_complete_if_cache(
                model=model,
                api_key=api_key,
                base_url=base_url,
                prompt=prompt,
                system_prompt=system_prompt,
                history_messages=history_messages or [],
                **kwargs,
            )

        def embedding_func(input: List[str]) -> List[List[float]]:
            return embedder.embed_documents(input)

        self.rag = RAGAnything(
            config=config,
            llm_model_func=llm_model_func,
            vision_model_func=vision_model_func,
            embedding_func=embedding_func,
        )
        await self.rag.finalize_storages()
        self.initialized = True
        self.last_config = {
            "provider": provider,
            "model": model,
            "base_url": base_url,
            "embedding_model": embedding_model,
            "parser": parser,
            "parse_method": parse_method,
        }

    def _serialize_result(self, result: Any) -> Any:
        if isinstance(result, (dict, list, str, int, float, bool)) or result is None:
            return result
        if hasattr(result, "model_dump"):
            try:
                return result.model_dump()
            except Exception:
                pass
        if hasattr(result, "dict"):
            try:
                return result.dict()
            except Exception:
                pass
        return str(result)

    async def sync_config(self, request: SyncConfigRequest) -> Dict[str, Any]:
        base_url = self._build_base_url(request.provider, request.base_url)
        try:
            await self._create_runtime(
                provider=request.provider,
                model=request.model,
                api_key=request.api_key,
                base_url=base_url,
                embedding_model=request.embedding_model,
                parser=request.parser,
                parse_method=request.parse_method,
            )
            return {
                "initialized": True,
                "config": self.last_config,
                "working_dir": str(self.workdir),
            }
        except Exception as exc:
            self.initialized = False
            self.rag = None
            logger.exception("Failed to initialize RAG runtime")
            return {"initialized": False, "error": str(exc)}

    async def ingest_file(
        self,
        upload: UploadFile,
        parse_method: str = "auto",
        source_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.initialized or not self.rag:
            raise HTTPException(status_code=503, detail="RAG service not initialized")

        filename = source_name or upload.filename or f"document-{uuid4().hex}"
        suffix = Path(filename).suffix or ".bin"
        target = self.upload_dir / f"{uuid4().hex}{suffix}"

        content = await upload.read()
        await asyncio.to_thread(target.write_bytes, content)
        try:
            result = await self.rag.process_document_complete(
                file_path=str(target),
                output_dir=str(self.workdir),
                parse_method=parse_method,
            )
            return {
                "document_path": str(target),
                "result": self._serialize_result(result),
                "parse_method": parse_method,
            }
        except Exception as exc:
            logger.exception("Failed to ingest file")
            raise HTTPException(status_code=500, detail=str(exc))

    async def ingest_markdown(
        self, title: str, content: str, source_name: Optional[str] = None
    ) -> Dict[str, Any]:
        if not self.initialized or not self.rag:
            raise HTTPException(status_code=503, detail="RAG service not initialized")

        filename = source_name or f"{title}.md"
        target = self.temp_dir / f"{uuid4().hex}-{Path(filename).name}"
        await asyncio.to_thread(target.write_text, content, encoding="utf-8")
        try:
            result = await self.rag.process_document_complete(
                file_path=str(target),
                output_dir=str(self.workdir),
                parse_method="txt",
            )
            return {
                "document_path": str(target),
                "result": self._serialize_result(result),
                "parse_method": "txt",
            }
        except Exception as exc:
            logger.exception("Failed to ingest markdown")
            raise HTTPException(status_code=500, detail=str(exc))

    async def query(self, query_text: str, mode: str = "hybrid") -> Dict[str, Any]:
        if not self.initialized or not self.rag:
            raise HTTPException(status_code=503, detail="RAG service not initialized")

        try:
            result = await self.rag.aquery(query_text, mode=mode)
            serialized = self._serialize_result(result)
            return {"result": serialized, "raw_result": serialized, "mode": mode}
        except Exception as exc:
            logger.exception("Failed to query RAG runtime")
            raise HTTPException(status_code=500, detail=str(exc))

    async def query_multimodal(
        self,
        query_text: str,
        multimodal_content: List[Dict[str, Any]],
        mode: str = "hybrid",
    ) -> Dict[str, Any]:
        if not self.initialized or not self.rag:
            raise HTTPException(status_code=503, detail="RAG service not initialized")

        try:
            result = await self.rag.aquery_with_multimodal(
                query_text,
                multimodal_content=multimodal_content,
                mode=mode,
            )
            serialized = self._serialize_result(result)
            return {"result": serialized, "raw_result": serialized, "mode": mode}
        except Exception as exc:
            logger.exception("Failed to query RAG runtime with multimodal content")
            raise HTTPException(status_code=500, detail=str(exc))

    async def reindex(self, title: str, content: str, source_name: Optional[str]) -> Dict[str, Any]:
        return await self.ingest_markdown(title=title, content=content, source_name=source_name)

    async def status(self) -> Dict[str, Any]:
        return {
            "initialized": self.initialized,
            "ready": self.initialized,
            "working_dir": str(self.workdir),
            "last_config": self.last_config,
            "capabilities": self.capabilities,
        }


runtime = RAGRuntime()
app = FastAPI(title="RAG-Anything Service", version="1.0.0")


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {"status": "healthy", "initialized": runtime.initialized, "ready": runtime.initialized}


@app.get("/status")
async def status() -> Dict[str, Any]:
    return await runtime.status()


@app.post("/config/sync")
async def sync_config(request: SyncConfigRequest) -> Dict[str, Any]:
    return await runtime.sync_config(request)


@app.post("/ingest")
async def ingest(
    file: UploadFile = File(...),
    parse_method: str = Form("auto"),
    source_name: Optional[str] = Form(None),
) -> Dict[str, Any]:
    return await runtime.ingest_file(file, parse_method=parse_method, source_name=source_name)


@app.post("/ingest-markdown")
async def ingest_markdown(request: MarkdownIngestRequest) -> Dict[str, Any]:
    return await runtime.ingest_markdown(
        title=request.title,
        content=request.content,
        source_name=request.source_name,
    )


@app.post("/reindex")
async def reindex(request: MarkdownIngestRequest) -> Dict[str, Any]:
    return await runtime.reindex(
        title=request.title,
        content=request.content,
        source_name=request.source_name,
    )


@app.post("/query")
async def query(request: QueryRequest) -> Dict[str, Any]:
    return await runtime.query(request.query_text, mode=request.mode)


@app.post("/query-multimodal")
async def query_multimodal(request: QueryMultimodalRequest) -> Dict[str, Any]:
    return await runtime.query_multimodal(
        request.query_text,
        request.multimodal_content,
        mode=request.mode,
    )
