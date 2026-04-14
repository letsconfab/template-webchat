"""FastAPI application for Admin Invite and Authentication."""
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .config import config
from .database import init_db, close_db
from .routers import auth, users, invites




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
    title="Admin Invite API",
    description="Admin invitation and authentication system",
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


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}




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
