"""FastAPI application for AI Copilot with GraphRAG knowledge base."""

import logging
import re
import asyncio
import time
from typing import List, Optional, Dict
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime
from uuid import UUID

from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import config, validate_config
from backend.database import init_db, close_db, AsyncSessionLocal
from backend.routers import (
    auth,
    admin_analytics,
    admin_feedback_cases,
    bulk_invites,
    case_notifications,
    drive,
    feedback,
    feedback_cases,
    insights,
    invites,
    settings,
    users,
    wiki,
)
from backend.llm_providers import LLMProvider, validate_api_key, get_available_models
from backend.services.langfuse_service import langfuse_service
from backend.services.cocoindex_manager import cocoindex_manager
from backend.services.graphrag_service import graphrag_service
from backend.services.drive_sync_service import drive_sync_service
from backend.models.settings import SystemSettings
from backend.models.chat import ChatSession
from backend.models.user import User
from backend.models.wiki import ChatMessage as ChatMessageDB
from backend.database import get_db
from backend.dependencies.auth import get_current_active_user
from backend.services.auth import verify_token
from backend.services.execution_traces import persist_trace
from backend.services.redaction import project_text, redactor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


class SettingsRequest(BaseModel):
    provider: str
    model: str
    api_key: str


class ChatMessage(BaseModel):
    id: Optional[int] = None
    role: str
    content: str


class ModelsResponse(BaseModel):
    models: List[str]


user_sessions = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_config(config)
    logger.info("Starting FastAPI application...")
    await init_db()

    try:
        from backend.services.cocoindex_pipeline import ensure_qdrant_collection
        await ensure_qdrant_collection(config.QDRANT_URL)
    except Exception as e:
        logger.warning("Qdrant collection init failed (will retry lazily): %s", e)

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(SystemSettings).limit(1))
        settings = result.scalar_one_or_none()

        if settings:
            neo4j_uri = settings.neo4j_url or config.NEO4J_URI
            neo4j_user = settings.neo4j_user or config.NEO4J_USER
            neo4j_password = settings.neo4j_password or config.NEO4J_PASSWORD
            neo4j_database = settings.neo4j_database or "neo4j"

            await graphrag_service.initialize(
                neo4j_uri=neo4j_uri,
                neo4j_user=neo4j_user,
                neo4j_password=neo4j_password,
                neo4j_database=neo4j_database,
                qdrant_url=config.QDRANT_URL,
            )

            if settings.llm_provider and settings.llm_model and settings.llm_api_key:
                cache_dir = str(Path(getattr(config, "KB_CACHE_DIR", "./kb_cache")) / "drive")
                cocoindex_manager.configure(
                    cache_dir=cache_dir,
                    neo4j_uri=neo4j_uri,
                    neo4j_user=neo4j_user,
                    neo4j_password=neo4j_password,
                    neo4j_database=neo4j_database,
                    qdrant_url=config.QDRANT_URL,
                    embedding_model=settings.cocoindex_embedding_model or "sentence-transformers/all-MiniLM-L6-v2",
                    llm_provider=settings.llm_provider,
                    llm_model=settings.llm_model,
                    llm_api_key=settings.llm_api_key or "",
                )
                await cocoindex_manager.start()

            if settings.google_drive_refresh_token:
                await drive_sync_service.start(settings.google_drive_refresh_token)

    frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
    if frontend_dist.exists():
        assets_dir = frontend_dist / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
        static_dir = frontend_dist / "static"
        if static_dir.exists():
            app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    yield

    logger.info("Shutting down...")
    await drive_sync_service.stop()
    await cocoindex_manager.stop()
    await graphrag_service.close()
    await close_db()


app = FastAPI(
    title="AI Copilot API",
    description="Multi-tenant AI copilot with GraphRAG capabilities",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(invites.router)
app.include_router(bulk_invites.router)
app.include_router(settings.router)
app.include_router(feedback.router)
app.include_router(feedback_cases.router)
app.include_router(admin_feedback_cases.router)
app.include_router(admin_analytics.router)
app.include_router(case_notifications.router)
app.include_router(insights.router)
app.include_router(wiki.router)
app.include_router(drive.router)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.get("/api/providers")
async def get_providers():
    return {
        "providers": [
            {"id": "openai", "name": "OpenAI", "requires_api_key": True},
            {"id": "groq", "name": "Groq", "requires_api_key": True},
            {"id": "ollama", "name": "Ollama", "requires_api_key": False},
            {"id": "sarvam", "name": "Sarvam", "requires_api_key": True},
        ]
    }


@app.post("/api/models")
async def get_models(request: SettingsRequest):
    try:
        models = await get_available_models(request.provider, request.api_key)
        return ModelsResponse(models=models)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/validate-key")
async def validate_key(request: SettingsRequest):
    is_valid = await validate_api_key(request.provider, request.api_key)
    return {"valid": is_valid}


@app.post("/api/settings")
async def update_settings(settings: SettingsRequest):
    user_sessions["default"] = {
        "provider": settings.provider,
        "model": settings.model,
        "api_key": settings.api_key,
    }
    return {"status": "success"}


async def _owned_chat_session(
    db: AsyncSession,
    session_id: str,
    user_id: int,
) -> ChatSession:
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.client_uuid == session_id,
            ChatSession.user_id == user_id,
            ChatSession.ownership_state == "owned",
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Chat Session not found")
    return session


@app.get("/api/chat-history")
async def get_chat_history(
    session_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    chat_session = await _owned_chat_session(db, session_id, current_user.id)
    result = await db.execute(
        select(ChatMessageDB)
        .where(ChatMessageDB.chat_session_id == chat_session.id)
        .order_by(ChatMessageDB.created_at, ChatMessageDB.id)
    )
    return {
        "messages": [
            ChatMessage(id=row.id, role=row.role, content=row.content).model_dump()
            for row in result.scalars()
        ]
    }


@app.delete("/api/chat-history")
async def clear_chat_history(
    session_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    chat_session = await _owned_chat_session(db, session_id, current_user.id)
    await db.execute(
        delete(ChatMessageDB).where(
            ChatMessageDB.chat_session_id == chat_session.id
        )
    )
    await db.commit()
    return {"status": "success"}


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def send_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)


manager = ConnectionManager()


async def _persist_chat_message(
    chat_session: ChatSession,
    role: str,
    content: str,
    metadata: Optional[dict] = None,
) -> Optional[int]:
    """Persist a chat message to the database. Returns the row id, or None on failure.

    DB failures must never break the streaming path, so all exceptions are
    swallowed and logged.
    """
    try:
        async with AsyncSessionLocal() as db:
            row = ChatMessageDB(
                chat_session_id=chat_session.id,
                session_id=chat_session.client_uuid,
                role=role,
                content=content,
                msg_metadata=metadata,
            )
            db.add(row)
            await db.flush()
            await project_text(
                db,
                content_type="chat_message",
                content_id=row.id,
                source_field="content",
                raw_text=content,
            )
            await db.commit()
            await db.refresh(row)
            return row.id
    except Exception as e:
        logger.warning(
            "Failed to persist chat message (session=%s): %s",
            chat_session.client_uuid,
            e,
        )
        return None


async def _persist_execution_trace(
    message_id: int,
    events: list[dict],
) -> None:
    """Persist a bounded trace without allowing capture failure to break chat."""
    try:
        async with AsyncSessionLocal() as db:
            try:
                await persist_trace(
                    db,
                    chat_message_id=message_id,
                    events=events,
                )
                await db.commit()
            except Exception:
                await db.rollback()
                await persist_trace(
                    db,
                    chat_message_id=message_id,
                    events=[],
                    capture_failed=True,
                )
                await db.commit()
    except Exception as error:
        logger.warning(
            "Failed to persist execution trace (message=%s): %s",
            message_id,
            error,
        )


async def _redacted_source_identifiers(output: str) -> list[str]:
    identifiers = re.findall(r"\[Source:\s*([^\]\n]+)", output)[:20]
    try:
        return [
            (await asyncio.to_thread(redactor.redact, identifier))[:200]
            for identifier in identifiers
        ]
    except Exception:
        return []


async def _load_session_history(chat_session_id: int) -> List[ChatMessage]:
    """Load persisted chat history for a session (oldest first, up to 100 rows)."""
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(ChatMessageDB)
                .where(ChatMessageDB.chat_session_id == chat_session_id)
                .order_by(ChatMessageDB.created_at, ChatMessageDB.id)
            )
            rows = result.scalars().all()
            return [
                ChatMessage(id=row.id, role=row.role, content=row.content)
                for row in rows
            ]
    except Exception as e:
        logger.warning(
            "Failed to load chat history (chat_session_id=%s): %s",
            chat_session_id,
            e,
        )
        return []


def _build_system_prompt(has_kb: bool, provider: str, model: str) -> str:
    kb_note = (
        "\n\nYou have access to a knowledge base. "
        "Call the `retrieve_knowledge` tool once (at most twice) to look up relevant "
        "information, then write a single complete answer grounded in what it returns. "
        "If the knowledge base returns empty results, answer from your own knowledge. "
        "Do not make a plan, do not repeat yourself, and do not call the tool in a loop."
        if has_kb
        else ""
    )
    return f"""You are an AI assistant helping users with their questions.
Be concise, accurate, and helpful.{kb_note}"""


async def _settings_status_message(settings) -> str:
    if not settings:
        return "System not configured."
    parts = []
    neo4j_ok = await graphrag_service.is_ready()
    parts.append("Knowledge graph is connected." if neo4j_ok else "Knowledge graph is not connected.")
    sync = drive_sync_service.get_status()
    if sync.get("last_sync"):
        parts.append(f"Last Drive sync: {sync['last_sync']}")
    if sync.get("file_count", 0) > 0:
        parts.append(f"Files cached: {sync['file_count']}")
    pipeline = cocoindex_manager.get_status()
    if pipeline.get("last_update"):
        parts.append(f"Last index update: {pipeline['last_update']}")
    if pipeline.get("running"):
        parts.append("Index pipeline is running.")
    return " | ".join(parts)


async def _query_with_knowledge(
    llm,
    user_message: str,
    history: List[ChatMessage],
    chat_session: ChatSession,
    websocket: WebSocket,
    provider: str = "unknown",
    model: str = "unknown",
):
    full_response = ""
    had_error = False
    thought_count = 0
    trace_events: list[dict] = []
    tool_started_at: dict[str, float] = {}
    start_time = time.monotonic()
    try:
        from langgraph.prebuilt import create_react_agent
        from langchain_core.tools import tool

        if await graphrag_service.is_ready():
            @tool
            async def retrieve_knowledge(query: str) -> str:
                """Search the knowledge base for information relevant to the query."""
                return await graphrag_service.retrieve_knowledge(query)

            tools = [retrieve_knowledge]
        else:
            tools = []

        # A ReAct agent (retrieve -> answer) converges in a few steps. The older
        # deepagents planner tended to loop on its own planning/todo tools until it
        # hit LangGraph's recursion limit, so it is intentionally not used here.
        agent = create_react_agent(
            model=llm,
            tools=tools,
            prompt=_build_system_prompt(
                has_kb=len(tools) > 0,
                provider=getattr(llm, "model", "unknown"),
                model=getattr(llm, "model_name", "unknown"),
            ),
        )

        messages = [HumanMessage(content=user_message)]

        await websocket.send_json({"type": "start"})
        think_buf = ""

        # recursion_limit is a hard backstop: a healthy RAG turn needs only a few
        # super-steps, so a low cap fails fast instead of looping for pages.
        async for event in agent.astream_events(
            {"messages": messages}, version="v2", config={"recursion_limit": 12}
        ):
            kind = event["event"]

            if kind == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                if not chunk:
                    continue

                reasoning = chunk.additional_kwargs.get("reasoning_content", "")
                if reasoning:
                    think_buf += reasoning
                    if reasoning.endswith((".", "?", "!", "\n")):
                        thought_count += 1
                        await websocket.send_json({
                            "type": "think",
                            "content": think_buf.strip(),
                        })
                        think_buf = ""

                content = getattr(chunk, "content", "") or ""
                if content:
                    full_response += content
                    await websocket.send_json({
                        "type": "chunk",
                        "content": content,
                    })

            elif kind == "on_tool_start":
                input_data = event["data"].get("input", {})
                run_id = str(event.get("run_id", len(trace_events)))
                tool_name = str(event.get("name", "unknown"))[:100]
                tool_started_at[run_id] = time.monotonic()
                trace_events.append(
                    {
                        "sequence": len(trace_events),
                        "timestamp": datetime.utcnow().isoformat(),
                        "event_type": "tool_started",
                        "tool_name": tool_name,
                    }
                )
                thought_count += 1
                await websocket.send_json({
                    "type": "think",
                    "content": f"Searching knowledge base: {str(input_data)[:120]}",
                })

            elif kind == "on_tool_end":
                raw_output = str(event["data"].get("output", ""))
                output = raw_output[:200]
                run_id = str(event.get("run_id", ""))
                started = tool_started_at.pop(run_id, None)
                sources = await _redacted_source_identifiers(raw_output)
                trace_events.append(
                    {
                        "sequence": len(trace_events),
                        "timestamp": datetime.utcnow().isoformat(),
                        "event_type": "tool_completed",
                        "tool_name": str(event.get("name", "unknown"))[:100],
                        "duration_ms": (
                            int((time.monotonic() - started) * 1000)
                            if started is not None
                            else None
                        ),
                        "source_identifiers": sources,
                        "result_count": len(sources),
                        "summary": "Tool completed with redacted results.",
                    }
                )
                thought_count += 1
                await websocket.send_json({
                    "type": "think",
                    "content": output[:200],
                })

            elif kind == "on_tool_error":
                run_id = str(event.get("run_id", ""))
                started = tool_started_at.pop(run_id, None)
                trace_events.append(
                    {
                        "sequence": len(trace_events),
                        "timestamp": datetime.utcnow().isoformat(),
                        "event_type": "tool_failed",
                        "tool_name": str(event.get("name", "unknown"))[:100],
                        "duration_ms": (
                            int((time.monotonic() - started) * 1000)
                            if started is not None
                            else None
                        ),
                        "safe_error_category": "tool_error",
                    }
                )

    except ImportError:
        logger.warning("deepagents not installed, falling back to simple LLM call")
        result = await llm.ainvoke([HumanMessage(content=user_message)])
        full_response = (
            result.content if hasattr(result, "content") else str(result)
        )
        await websocket.send_json({"type": "start"})
        if full_response:
            await websocket.send_json({"type": "chunk", "content": full_response})
    except Exception as e:
        logger.error("Agent query error: %s", e, exc_info=True)
        had_error = True
        error_msg = f"An error occurred: {str(e)}"
        full_response = full_response or error_msg
        try:
            await websocket.send_json({"type": "start"})
            await websocket.send_json({"type": "chunk", "content": error_msg})
        except Exception:
            pass

    message_id: Optional[int] = None
    if full_response:
        duration_ms = int((time.monotonic() - start_time) * 1000)
        message_id = await _persist_chat_message(
            chat_session=chat_session,
            role="assistant",
            content=full_response,
            metadata={
                "provider": provider,
                "model": model,
                "thought_count": thought_count,
                "duration_ms": duration_ms,
                "error": had_error,
            },
        )
        history.append(
            ChatMessage(id=message_id, role="assistant", content=full_response)
        )
        if message_id is not None:
            await _persist_execution_trace(message_id, trace_events)
    try:
        await websocket.send_json({"type": "end", "message_id": message_id})
    except Exception:
        pass


async def _bind_chat_session(user: User, session_id: str) -> ChatSession:
    """Atomically bind a client UUID or return its existing owned session."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ChatSession).where(ChatSession.client_uuid == session_id)
        )
        chat_session = result.scalar_one_or_none()
        if chat_session is None:
            candidate = ChatSession(
                client_uuid=session_id,
                user_id=user.id,
                ownership_state="owned",
            )
            db.add(candidate)
            try:
                await db.commit()
                await db.refresh(candidate)
                chat_session = candidate
            except IntegrityError:
                await db.rollback()
                result = await db.execute(
                    select(ChatSession).where(
                        ChatSession.client_uuid == session_id
                    )
                )
                chat_session = result.scalar_one_or_none()

        if (
            chat_session is None
            or chat_session.ownership_state != "owned"
            or chat_session.user_id != user.id
        ):
            raise PermissionError("Chat Session is unavailable")
        return chat_session


async def _authenticate_websocket(
    websocket: WebSocket,
    data: dict,
) -> tuple[User, ChatSession] | None:
    if data.get("type") != "auth":
        await websocket.close(code=4401, reason="Authentication required")
        return None
    token = data.get("token")
    payload = verify_token(token) if isinstance(token, str) else None
    try:
        user_id = int(payload["sub"]) if payload else None
    except (KeyError, TypeError, ValueError):
        user_id = None
    if user_id is None:
        await websocket.close(code=4401, reason="Authentication required")
        return None

    raw_session_id = data.get("session_id")
    try:
        session_id = str(UUID(raw_session_id))
    except (AttributeError, TypeError, ValueError):
        await websocket.close(code=4400, reason="Invalid Chat Session identifier")
        return None

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
    if user is None:
        await websocket.close(code=4401, reason="Authentication required")
        return None
    if not user.is_active:
        await websocket.close(code=4403, reason="Chat Session unavailable")
        return None

    try:
        chat_session = await _bind_chat_session(user, session_id)
    except PermissionError:
        await websocket.close(code=4403, reason="Chat Session unavailable")
        return None
    return user, chat_session


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    await websocket.accept()

    try:
        data = await websocket.receive_json()
        authenticated = await _authenticate_websocket(websocket, data)
        if authenticated is None:
            return
        _, chat_session = authenticated
        manager.active_connections.append(websocket)

        session_id = chat_session.client_uuid
        client_provider = data.get("provider", "openai")
        client_model = data.get("model", "gpt-4o-mini")

        async with AsyncSessionLocal() as settings_db:
            result = await settings_db.execute(select(SystemSettings).limit(1))
            settings = result.scalar_one_or_none()

            if settings:
                provider = (
                    client_provider
                    if client_provider != "openai"
                    else (settings.llm_provider or "openai")
                )
                model = (
                    client_model
                    if client_model != "gpt-4o-mini"
                    else (settings.llm_model or "gpt-4o-mini")
                )
                api_key = settings.llm_api_key or ""
            else:
                provider = client_provider
                model = client_model
                api_key = ""

        logger.info(
            "WebSocket session=%s provider=%s model=%s", session_id, provider, model
        )

        history = await _load_session_history(chat_session.id)
        await websocket.send_json(
            {"type": "history", "messages": [msg.model_dump() for msg in history]}
        )

        status_msg = await _settings_status_message(settings)
        if status_msg:
            await websocket.send_json({"type": "status", "message": status_msg})

        llm_instance = LLMProvider(provider, model, api_key).get_llm()

        while True:
            data = await websocket.receive_json()
            message = data.get("message", "")

            logger.info("WebSocket message: %.50s", message)

            async with AsyncSessionLocal() as langfuse_db:
                from backend.services.settings_service import settings_service

                s = await settings_service.get_settings(langfuse_db)
                if s and s.langfuse_public_key and s.langfuse_secret_key:
                    langfuse_service.initialize(
                        public_key=s.langfuse_public_key,
                        secret_key=s.langfuse_secret_key,
                        base_url=s.langfuse_base_url or "https://us.cloud.langfuse.com",
                    )
                else:
                    langfuse_service._initialized = False

            user_msg = ChatMessage(role="user", content=message)
            history.append(user_msg)
            user_msg.id = await _persist_chat_message(
                chat_session=chat_session,
                role="user",
                content=message,
            )

            await _query_with_knowledge(
                llm=llm_instance,
                user_message=message,
                history=history,
                chat_session=chat_session,
                websocket=websocket,
                provider=provider,
                model=model,
            )

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
        manager.disconnect(websocket)
    except Exception as e:
        logger.error("WebSocket error: %s", e)
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
        manager.disconnect(websocket)


@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
    if full_path.startswith("assets/") or full_path.startswith("static/"):
        file_path = frontend_dist / full_path
        if file_path.exists():
            return FileResponse(file_path)
    index_file = frontend_dist / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    raise HTTPException(status_code=404, detail="Frontend not built")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
