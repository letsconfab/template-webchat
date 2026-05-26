"""Standalone markdown grounding service for the demo app."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import httpx
from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration
from langchain_core.language_models import BaseChatModel


class ChatSarvam(BaseChatModel):
    """Custom Chat model for Sarvam AI API."""

    model: str = "sarvam-m"
    api_key: str = ""
    base_url: str = "https://api.sarvam.ai"
    temperature: float = 0.7

    @property
    def _llm_type(self) -> str:
        return "sarvam"

    def _generate(
        self, messages: List[BaseMessage], stop: Optional[List[str]] = None, **kwargs
    ) -> "ChatGeneration":
        import asyncio
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(self._agenerate(messages, stop))

    async def _agenerate(
        self, messages: List[BaseMessage], stop: Optional[List[str]] = None, **kwargs
    ) -> "ChatGeneration":
        sarvam_messages = []
        for msg in messages:
            if msg.type == "human":
                sarvam_messages.append({"role": "user", "content": msg.content})
            elif msg.type == "ai":
                sarvam_messages.append({"role": "assistant", "content": msg.content})
            elif msg.type == "system":
                sarvam_messages.append({"role": "system", "content": msg.content})

        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {"model": self.model, "messages": sarvam_messages, "temperature": self.temperature}

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/v1/chat/completions",
                headers=headers,
                json=payload,
            )

        if response.status_code != 200:
            raise Exception(f"Sarvam API error: {response.status_code} - {response.text}")

        result = response.json()
        content = result["choices"][0]["message"]["content"]
        return ChatGeneration(message=HumanMessage(content=content))

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


class SyncConfigRequest(BaseModel):
    provider: str = Field(default="openai")
    model: str = Field(default="gpt-4o-mini")
    api_key: str = Field(default="")
    base_url: str = Field(default="https://api.openai.com/v1")
    embedding_model: str = Field(default="text")
    parser: str = Field(default="markdown")
    parse_method: str = Field(default="auto")


class QueryRequest(BaseModel):
    query_text: str
    mode: str = "hybrid"


class MarkdownIngestRequest(BaseModel):
    title: str
    content: str
    source_name: Optional[str] = None


class RAGRuntime:
    def __init__(self) -> None:
        self.workdir = Path(os.getenv("RAG_WORKDIR", "/data/rag")).resolve()
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.snapshot_dir = self.workdir / "snapshots"
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        self.initialized = False
        self.last_config: Dict[str, Any] = {}
        self.llm = None
        self.agent_llm = None
        self.capabilities = {
            "markdown_ingest": True,
            "document_ingest": False,
            "image_processing": False,
            "table_processing": False,
            "equation_processing": False,
            "multimodal_query": False,
            "agent_query": True,
        }

    def _create_llm(self, provider: str, model: str, api_key: str, base_url: str) -> Any:
        if provider == "groq":
            return ChatGroq(model=model, groq_api_key=api_key or "dummy", temperature=0.7)
        elif provider == "ollama":
            return ChatOllama(model=model, temperature=0.7)
        elif provider == "sarvam":
            return ChatSarvam(model=model or "sarvam-m", api_key=api_key or "", base_url=base_url, temperature=0.7)
        else:
            return ChatOpenAI(model=model, api_key=api_key or "dummy", base_url=base_url, temperature=0.7)

    def _snapshot_path(self, source_name: Optional[str], title: str) -> Path:
        name = source_name or f"{self._slugify(title)}.md"
        if not name.endswith(".md"):
            name = f"{name}.md"
        return self.snapshot_dir / name

    def _slugify(self, value: str) -> str:
        value = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
        return value or "untitled"

    def _build_base_url(self, provider: str, base_url: Optional[str]) -> str:
        if base_url:
            return base_url.rstrip("/")
        if provider == "groq":
            return "https://api.groq.com/openai/v1"
        if provider == "ollama":
            return "http://host.docker.internal:11434/v1"
        if provider == "sarvam":
            return "https://api.sarvam.ai"
        return "https://api.openai.com/v1"

    def _store_markdown(self, title: str, content: str, source_name: Optional[str]) -> Path:
        snapshot = self._snapshot_path(source_name, title)
        snapshot.write_text(content, encoding="utf-8")
        return snapshot

    def _load_corpus(self) -> List[Dict[str, str]]:
        docs: List[Dict[str, str]] = []
        for path in sorted(self.snapshot_dir.glob("*.md")):
            try:
                docs.append({"path": str(path), "text": path.read_text(encoding="utf-8")})
            except Exception as exc:
                logger.warning("Failed to read snapshot %s: %s", path, exc)
        return docs

    def _score(self, query: str, text: str) -> int:
        query_terms = [term for term in re.findall(r"\w+", query.lower()) if len(term) > 2]
        text_lower = text.lower()
        return sum(text_lower.count(term) for term in query_terms)

    def _extract_excerpt(self, text: str, query: str, width: int = 240) -> str:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return text[:width]

        query_terms = [term for term in re.findall(r"\w+", query.lower()) if len(term) > 2]
        for line in lines:
            lowered = line.lower()
            if any(term in lowered for term in query_terms):
                return line[:width]
        return lines[0][:width]

    async def sync_config(self, request: SyncConfigRequest) -> Dict[str, Any]:
        base_url = self._build_base_url(request.provider, request.base_url)
        logger.info(f"RAG sync_config: provider={request.provider}, model={request.model}, base_url={base_url[:50] if base_url else 'none'}...")
        self.initialized = True
        self.last_config = {
            "provider": request.provider,
            "model": request.model,
            "base_url": base_url,
            "api_key": request.api_key,
            "embedding_model": request.embedding_model,
            "parser": request.parser,
            "parse_method": request.parse_method,
        }
        self.llm = self._create_llm(
            request.provider, request.model, request.api_key, base_url
        )
        logger.info(f"RAG LLM created: {type(self.llm).__name__}")
        return {
            "initialized": True,
            "config": self.last_config,
            "working_dir": str(self.workdir),
        }

    async def ingest_markdown(
        self,
        title: str,
        content: str,
        source_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not content.strip():
            raise HTTPException(status_code=400, detail="Markdown content is empty")

        snapshot = self._store_markdown(title, content, source_name)
        self.initialized = True
        return {
            "success": True,
            "document_path": str(snapshot),
            "title": title,
            "source_name": source_name or snapshot.name,
        }

    async def query(self, query_text: str, mode: str = "hybrid") -> Dict[str, Any]:
        logger.info(f"RAG query: initialized={self.initialized}, has_llm={self.llm is not None}")
        if not self.initialized:
            raise HTTPException(status_code=503, detail="RAG service not initialized")

        docs = self._load_corpus()
        if not docs:
            return {
                "result": "",
                "raw_result": "",
                "mode": mode,
            }

        if not self.llm:
            logger.info("RAG query: falling back to keyword search (no LLM)")
            ranked = sorted(
                ((self._score(query_text, doc["text"]), doc) for doc in docs),
                key=lambda item: item[0],
                reverse=True,
            )
            best_score, best_doc = ranked[0]
            excerpt = self._extract_excerpt(best_doc["text"], query_text)
            return {
                "result": excerpt,
                "raw_result": {
                    "matched_documents": [
                        {"path": doc["path"], "score": score}
                        for score, doc in ranked[:5]
                        if score > 0
                    ],
                },
                "mode": mode,
            }

        logger.info("RAG query: using LLM agent")
        context_parts = []
        for doc in docs:
            excerpt = self._extract_excerpt(doc["text"], query_text, width=2000)
            context_parts.append(f"Document: {doc['path']}\n\n{excerpt}\n\n---")

        context = "\n".join(context_parts[:3])
        system_prompt = """You are a helpful AI assistant with access to a knowledge base.
Your goal is to answer the user's question based on the provided context from the knowledge base.

Instructions:
1. Carefully read through the provided context documents
2. Answer the user's question based ONLY on information from the context
3. If the context doesn't contain enough information to fully answer the question, acknowledge what you know and what you cannot determine
4. Be concise but thorough - provide enough detail to be helpful
5. If you're unsure or cannot find relevant information, say so clearly
6. Do not make up information that isn't in the context

Context from knowledge base:
{context}

User question: {question}

Your answer:"""

        try:
            prompt = ChatPromptTemplate.from_template(system_prompt)
            chain = prompt | self.llm | StrOutputParser()
            logger.info(f"Invoking LLM with query: {query_text[:50]}...")
            answer = await chain.ainvoke({"context": context, "question": query_text})
            logger.info(f"LLM response: {answer[:100] if answer else 'empty'}...")
            answer = answer.strip() if answer else "I couldn't find a relevant answer in the knowledge base."
        except Exception as e:
            import traceback
            logger.error(f"Agent query failed: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            ranked = sorted(
                ((self._score(query_text, doc["text"]), doc) for doc in docs),
                key=lambda item: item[0],
                reverse=True,
            )
            best_doc = ranked[0][1]
            answer = self._extract_excerpt(best_doc["text"], query_text)

        return {
            "result": answer,
            "raw_result": {
                "agent_mode": True,
                "matched_documents": [
                    {"path": doc["path"], "excerpt": self._extract_excerpt(doc["text"], query_text, width=500)}
                    for doc in docs[:3]
                ],
            },
            "mode": mode,
        }

    async def ingest_file(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        raise HTTPException(
            status_code=501,
            detail="File ingestion is not enabled in the lightweight markdown service.",
        )

    async def query_multimodal(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        raise HTTPException(
            status_code=501,
            detail="Multimodal queries are not enabled in the lightweight markdown service.",
        )

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
app = FastAPI(title="RAG Markdown Service", version="1.0.0")


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {"status": "healthy", "initialized": runtime.initialized, "ready": runtime.initialized}


@app.get("/status")
async def status() -> Dict[str, Any]:
    return await runtime.status()


@app.post("/config/sync")
async def sync_config(request: SyncConfigRequest) -> Dict[str, Any]:
    return await runtime.sync_config(request)


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


@app.post("/ingest")
async def ingest(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    raise HTTPException(
        status_code=501,
        detail="Raw file ingestion is not enabled in the lightweight markdown service.",
    )


@app.post("/query-multimodal")
async def query_multimodal(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    raise HTTPException(
        status_code=501,
        detail="Multimodal queries are not enabled in the lightweight markdown service.",
    )
