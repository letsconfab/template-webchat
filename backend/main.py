"""FastAPI application for Admin Invite and Chat."""

import os
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

from .config import config
from .database import init_db, close_db
from .routers import auth, users, invites, settings, knowledge
from .knowledge_base import knowledge_base
from .llm_providers import LLMProvider, validate_api_key, get_available_models


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    # Startup
    print("Starting FastAPI application...")

    # Initialize database
    print("Initializing database...")
    await init_db()

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
        # Receive initial settings
        data = await websocket.receive_json()
        session_id = data.get("session_id", "default")
        provider = data.get("provider", "openai")
        model = data.get("model", "gpt-4o-mini")
        api_key = data.get("api_key", "")

        print(
            f"WebSocket: Received settings - session: {session_id}, provider: {provider}, model: {model}"
        )

        # Send chat history
        history = chat_history.get(session_id, [])
        if history:
            await websocket.send_json(
                {"type": "history", "messages": [msg.model_dump() for msg in history]}
            )

        # Initialize knowledge base if not done
        if knowledge_base.vector_store is None:
            try:
                llm_provider = LLMProvider(provider, model, api_key)
                embeddings = llm_provider.get_embeddings()
                knowledge_base.initialize(embeddings)
                await websocket.send_json(
                    {"type": "status", "message": "Welcome! I'm ready to help you."}
                )
            except Exception as e:
                print(f"Error initializing knowledge base: {e}")
                print("Continuing without knowledge base")
                await websocket.send_json(
                    {
                        "type": "status",
                        "message": "Welcome! I'm ready to help you. Note: Knowledge base not available.",
                    }
                )

        # Chat loop
        while True:
            data = await websocket.receive_json()
            message = data.get("message", "")

            print(f"WebSocket: Received message: {message[:50]}...")

            # Store user message in history
            if session_id not in chat_history:
                chat_history[session_id] = []
            chat_history[session_id].append(ChatMessage(role="user", content=message))

            # Search knowledge base (only if initialized)
            relevant_docs = []
            if knowledge_base.vector_store is not None:
                relevant_docs = knowledge_base.search(message, k=5)

            # Build context
            context = ""
            if relevant_docs:
                context_parts = []
                for i, doc in enumerate(relevant_docs, 1):
                    source = doc.metadata.get("source", "Unknown")
                    context_parts.append(f"[{i}] Source: {source}\n{doc.page_content}")
                context = "\n\n".join(context_parts)

            # Build messages with conversation history
            system_prompt = getattr(
                config, "system_prompt", "You are a helpful AI assistant."
            )
            messages = [SystemMessage(content=system_prompt)]

            # Add knowledge base context if available
            if context:
                messages.append(
                    SystemMessage(
                        content=f"Relevant knowledge base documents:\n\n{context}\n\nUse the above information to answer the user's question."
                    )
                )

            # Add conversation history (last 10 messages to stay within token limits)
            history = chat_history.get(session_id, [])
            recent_history = history[-10:] if len(history) > 10 else history

            for hist_msg in recent_history[:-1]:
                if hist_msg.role == "user":
                    messages.append(HumanMessage(content=hist_msg.content))
                elif hist_msg.role == "assistant":
                    messages.append(AIMessage(content=hist_msg.content))

            # Add current message
            messages.append(HumanMessage(content=message))

            # Get LLM and stream response
            llm_provider = LLMProvider(provider, model, api_key)
            llm = llm_provider.get_llm()

            if llm is None:
                error_msg = "Failed to initialize LLM provider"
                await websocket.send_json({"type": "error", "message": error_msg})
                chat_history[session_id].append(
                    ChatMessage(role="assistant", content=error_msg)
                )
                continue

            # Stream response
            await websocket.send_json({"type": "start"})
            full_response = ""

            for chunk in llm.stream(messages):
                if chunk.content:
                    full_response += chunk.content
                    await websocket.send_json(
                        {"type": "chunk", "content": chunk.content}
                    )

            # Store assistant message in history
            chat_history[session_id].append(
                ChatMessage(role="assistant", content=full_response)
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
