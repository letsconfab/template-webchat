"""FastAPI application for Admin Invite and Chat."""

import os
import logging
from typing import List, Optional, Dict
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import httpx

# from config import config
from backend.config import config

# from database import init_db, close_db
from backend.database import init_db, close_db, AsyncSessionLocal

# from routers import auth, users, invites, settings, knowledge, feedback, insights
from backend.routers import (
    auth,
    users,
    invites,
    settings,
    knowledge,
    feedback,
    insights,
    wiki,
)
from backend.llm_providers import LLMProvider, validate_api_key, get_available_models
from backend.services.knowledge_book_service import knowledge_book_service
from backend.services.langfuse_service import langfuse_service
from langfuse import propagate_attributes

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


# Pydantic models for API
class SettingsRequest(BaseModel):
    provider: str
    model: str
    api_key: str


class ChatMessage(BaseModel):
    role: str
    content: str


class ModelsResponse(BaseModel):
    models: List[str]


# In-memory chat history storage (keyed by session ID)
chat_history: Dict[str, List[ChatMessage]] = {}


# Global session storage (in production, use Redis or database)
user_sessions = {}


def _knowledge_status_message(status: Dict[str, object]) -> str:
    source_counts = status.get("source_counts") or {}
    processing_sources = int(status.get("processing_sources") or source_counts.get("processing") or 0)
    processing_progress = int(status.get("processing_progress") or 0)

    if status.get("chat_ready"):
        return "Knowledge book is ready for chat."

    if processing_sources > 0:
        if processing_progress > 0:
            return f"Knowledge book is still processing ({processing_progress}% complete)."
        return "Knowledge book is still processing."

    if not status.get("rag_initialized"):
        return "Knowledge book grounding is not initialized yet."

    if not status.get("rag_healthy"):
        return "Knowledge book grounding service is offline."

    return "Knowledge book grounding is unavailable."


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    # Startup
    print("Starting FastAPI application...")

    # Initialize database
    print("Initializing database...")
    await init_db()

    # Try to initialize the external RAG-Anything service if settings exist
    try:
        from sqlalchemy import select
        from backend.models.settings import SystemSettings

        async with AsyncSessionLocal() as session:
            result = await session.execute(select(SystemSettings).limit(1))
            settings = result.scalar_one_or_none()
            print(f"Settings object: {settings}, type: {type(settings)}")

            if settings:
                from backend.services.rag_anything_service import rag_anything_service

                sync_result = await rag_anything_service.sync_from_settings(settings)
                print(f"RAG-Anything sync result: {sync_result}")
                if rag_anything_service.is_initialized:
                    try:
                        await knowledge_book_service.resume_pending_sources()
                        await knowledge_book_service.reindex_current_book()
                        print("Knowledge book indexing complete")
                    except Exception as e:
                        print(f"Knowledge book warmup failed: {e}")
    except Exception as e:
        print(f"RAG-Anything auto-sync failed: {e}")

    try:
        await knowledge_book_service.resume_pending_sources()
    except Exception as e:
        print(f"Knowledge book resume failed: {e}")

    # Mount static files for React frontend
    frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
    if frontend_dist.exists():
        assets_dir = frontend_dist / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
        static_dir = frontend_dist / "static"
        if static_dir.exists():
            app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    else:
        print(f"Warning: Frontend dist directory not found at {frontend_dist}")

    yield
    # Shutdown
    print("Shutting down FastAPI application...")
    await close_db()


app = FastAPI(
    title="AI Copilot API",
    description="Multi-tenant AI copilot with RAG capabilities",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(invites.router)
app.include_router(settings.router)
app.include_router(knowledge.router)
app.include_router(feedback.router)
app.include_router(insights.router)
app.include_router(wiki.router)

# Mount static files for frontend (deployment)
# app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="frontend")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/api/providers")
async def get_providers():
    """Get list of available LLM providers."""
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
    """Get available models for a provider."""
    try:
        models = await get_available_models(request.provider, request.api_key)
        return ModelsResponse(models=models)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/validate-key")
async def validate_key(request: SettingsRequest):
    """Validate API key for a provider."""
    is_valid = await validate_api_key(request.provider, request.api_key)
    return {"valid": is_valid}


@app.post("/api/settings")
async def update_settings(settings: SettingsRequest):
    """Update user settings (session-based)."""
    user_sessions["default"] = {
        "provider": settings.provider,
        "model": settings.model,
        "api_key": settings.api_key,
    }
    return {"status": "success"}


@app.get("/api/chat-history")
async def get_chat_history(session_id: str = "default"):
    """Get chat history for a session."""
    return {"messages": chat_history.get(session_id, [])}


@app.delete("/api/chat-history")
async def clear_chat_history(session_id: str = "default"):
    """Clear chat history for a session."""
    chat_history[session_id] = []
    return {"status": "success"}


class ConnectionManager:
    """Manage WebSocket connections for streaming chat."""

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


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """WebSocket endpoint for streaming chat responses."""
    await manager.connect(websocket)

    try:
        # Receive initial settings from client
        data = await websocket.receive_json()
        session_id = data.get("session_id", "default")
        client_provider = data.get("provider", "openai")
        client_model = data.get("model", "gpt-4o-mini")

        # Get API key from database settings (not from client - more secure)
        from sqlalchemy import select
        from backend.models.settings import SystemSettings

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

        print(
            f"WebSocket: Received settings - session: {session_id}, provider: {provider}, model: {model}"
        )

        # Send chat history
        history = chat_history.get(session_id, [])
        if history:
            await websocket.send_json(
                {"type": "history", "messages": [msg.model_dump() for msg in history]}
            )

        # Report knowledge book readiness
        try:
            from backend.services.knowledge_book_service import knowledge_book_service

            async with AsyncSessionLocal() as kb_db:
                status = await knowledge_book_service.get_status(kb_db)
                await websocket.send_json(
                    {
                        "type": "status",
                        "message": _knowledge_status_message(status),
                    }
                )
        except Exception as e:
            print(f"Failed to load knowledge book status: {e}")
            await websocket.send_json(
                {
                    "type": "status",
                    "message": "Knowledge book status unavailable.",
                }
            )

        # Chat loop
        while True:
            data = await websocket.receive_json()
            message = data.get("message", "")

            print(f"WebSocket: Received message: {message[:50]}...")

            # Initialize langfuse from settings
            async with AsyncSessionLocal() as langfuse_db:
                from backend.services.settings_service import settings_service

                settings = await settings_service.get_settings(langfuse_db)
                if (
                    settings
                    and settings.langfuse_public_key
                    and settings.langfuse_secret_key
                ):
                    base_url = (
                        settings.langfuse_base_url or "https://us.cloud.langfuse.com"
                    )
                    print(
                        f"[Langfuse] Initializing with public_key: {settings.langfuse_public_key[:20]}..., base_url: {base_url}"
                    )
                    langfuse_service.initialize(
                        public_key=settings.langfuse_public_key,
                        secret_key=settings.langfuse_secret_key,
                        base_url=base_url,
                    )
                else:
                    langfuse_service._initialized = False

            if langfuse_service.is_initialized():
                print(f"[Langfuse] Tracking chat session: {session_id}")

            # Store user message in history
            if session_id not in chat_history:
                chat_history[session_id] = []
            chat_history[session_id].append(ChatMessage(role="user", content=message))

            try:
                from backend.services.rag_anything_service import rag_anything_service

                if not rag_anything_service.is_initialized:
                    response_text = "Knowledge book grounding is not initialized yet."
                else:
                    async with AsyncSessionLocal() as kb_db:
                        status = await knowledge_book_service.get_status(kb_db)

                    if not status.get("chat_ready"):
                        response_text = _knowledge_status_message(status)
                    else:
                        result = await rag_anything_service.query(message, mode="hybrid")
                        if result.get("success"):
                            response_text = str(result.get("result") or "").strip()
                        else:
                            response_text = _knowledge_status_message(status)
            except Exception as e:
                print(f"RAG-Anything query error: {e}")
                response_text = "Knowledge book grounding is unavailable."

            await websocket.send_json({"type": "start"})
            await websocket.send_json({"type": "chunk", "content": response_text})
            chat_history[session_id].append(
                ChatMessage(role="assistant", content=response_text)
            )
            await websocket.send_json({"type": "end"})

    except WebSocketDisconnect:
        print("WebSocket: Client disconnected")
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except:
            pass
        manager.disconnect(websocket)


@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    """Serve the React frontend for all non-API routes."""
    frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"

    # If it's a static asset, try to serve it
    if full_path.startswith("assets/") or full_path.startswith("static/"):
        file_path = frontend_dist / full_path
        if file_path.exists():
            return FileResponse(file_path)

    # Otherwise serve index.html for client-side routing
    index_file = frontend_dist / "index.html"
    if index_file.exists():
        return FileResponse(index_file)

    raise HTTPException(status_code=404, detail="Frontend not built")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
