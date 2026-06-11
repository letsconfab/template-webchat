"""FastAPI application for AI Copilot with GraphRAG knowledge base."""

import logging
from typing import List, Optional, Dict
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select

from backend.config import config, validate_config
from backend.database import init_db, close_db, AsyncSessionLocal
from backend.routers import auth, users, invites, settings, feedback, insights, wiki, drive
from backend.llm_providers import LLMProvider, validate_api_key, get_available_models
from backend.services.langfuse_service import langfuse_service
from backend.services.cocoindex_manager import cocoindex_manager
from backend.services.graphrag_service import graphrag_service
from backend.services.drive_sync_service import drive_sync_service
from backend.models.settings import SystemSettings

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
    role: str
    content: str


class ModelsResponse(BaseModel):
    models: List[str]


chat_history: Dict[str, List[ChatMessage]] = {}
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
app.include_router(settings.router)
app.include_router(feedback.router)
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


@app.get("/api/chat-history")
async def get_chat_history(session_id: str = "default"):
    return {"messages": chat_history.get(session_id, [])}


@app.delete("/api/chat-history")
async def clear_chat_history(session_id: str = "default"):
    chat_history[session_id] = []
    return {"status": "success"}


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)


manager = ConnectionManager()


def _build_system_prompt(has_kb: bool, provider: str, model: str) -> str:
    kb_note = (
        "\n\nYou have access to a knowledge base. "
        "When answering, use the `retrieve_knowledge` tool to look up relevant information. "
        "If the knowledge base returns empty results, rely on your own knowledge."
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
    session_id: str,
    websocket: WebSocket,
):
    full_response = ""
    try:
        from deepagents import create_deep_agent
        from langchain_core.tools import tool

        if await graphrag_service.is_ready():
            @tool
            async def retrieve_knowledge(query: str) -> str:
                """Search the knowledge base for information relevant to the query."""
                return await graphrag_service.retrieve_knowledge(query)

            tools = [retrieve_knowledge]
        else:
            tools = []

        agent = create_deep_agent(
            model=llm,
            tools=tools,
            system_prompt=_build_system_prompt(
                has_kb=len(tools) > 0,
                provider=getattr(llm, "model", "unknown"),
                model=getattr(llm, "model_name", "unknown"),
            ),
        )

        messages = [HumanMessage(content=user_message)]

        await websocket.send_json({"type": "start"})
        think_buf = ""

        async for event in agent.astream_events(
            {"messages": messages}, version="v2"
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
                await websocket.send_json({
                    "type": "think",
                    "content": f"Searching knowledge base: {str(input_data)[:120]}",
                })

            elif kind == "on_tool_end":
                output = str(event["data"].get("output", ""))[:200]
                await websocket.send_json({
                    "type": "think",
                    "content": output[:200],
                })

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
        error_msg = f"An error occurred: {str(e)}"
        full_response = full_response or error_msg
        try:
            await websocket.send_json({"type": "start"})
            await websocket.send_json({"type": "chunk", "content": error_msg})
        except Exception:
            pass

    if full_response:
        chat_history.setdefault(session_id, []).append(
            ChatMessage(role="assistant", content=full_response)
        )
    try:
        await websocket.send_json({"type": "end"})
    except Exception:
        pass


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    await manager.connect(websocket)

    try:
        data = await websocket.receive_json()
        session_id = data.get("session_id", "default")
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

        history = chat_history.get(session_id, [])
        if history:
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

            if session_id not in chat_history:
                chat_history[session_id] = []
            chat_history[session_id].append(ChatMessage(role="user", content=message))

            await _query_with_knowledge(
                llm=llm_instance,
                user_message=message,
                history=chat_history[session_id],
                session_id=session_id,
                websocket=websocket,
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
