# AGENTS.md

## Commands

### Backend
```bash
# Install dependencies
pip install -r requirements.txt

# Run development server
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev      # Dev server on port 3000 (proxies /api and /ws to backend:8000)
npm run build   # Type-check (tsc) then build
```

### Docker
```bash
docker build -t copilot-chat .
docker run -p 8000:8000 --env-file .env -v $(pwd)/kb_assets:/app/kb_assets copilot-chat
```

## Architecture

### Backend Entry Point
`backend/main.py` exports `app` (FastAPI). The backend:
- Serves API at `/api/*` endpoints
- Mounts static files from `frontend/dist/` (built frontend)
- WebSocket chat at `/ws/chat`
- Serves `frontend/dist/index.html` for all non-API routes

**Critical**: Backend expects `frontend/dist/` to exist. Run `npm run build` in frontend first, or backend prints a warning.

### Frontend Entry Point
`frontend/src/main.tsx` renders `App.tsx`.

### Knowledge Base
Documents live in `./kb_assets/` (configured via `KB_ASSETS_DIR`). Supported formats: PDF, DOCX, DOC, TXT, CSV, XLSX.

Document loaders are defined in `backend/knowledge_base.py:_get_loader()`.

## State Persistence

| Data | Storage |
|------|--------|
| User settings (provider, model, API key) | Frontend: `localStorage['copilot-settings']` |
| Session ID | Frontend: `sessionStorage['sessionId']` (UUID, survives refresh) |
| Chat history | Backend: in-memory `Dict[session_id, messages]`, cleared on server restart |
| Knowledge base | Backend: Qdrant in-memory, recreated on server restart |

## LLM Providers

Providers and model fetching are in `backend/llm_providers.py`:
- **openai**: Fetches from `api.openai.com/v1/models`
- **groq**: Fetches from `api.groq.com/openai/v1/models`
- **ollama**: Fetches from `localhost:11434/api/tags` (no API key needed)
- **sarvam**: Hardcoded list (no public models API)

All providers use FastEmbed embeddings (local), not provider-specific embeddings.

## Environment Variables

| Variable | Default | Notes |
|----------|---------|-------|
| `KB_ASSETS_DIR` | `./kb_assets` | Must exist for RAG to work |
| `PURPOSE` | System prompt | Used in chat |
| `GAURDRAILS` | Guardrails | Not enforced, used in prompt |
| `OPENAI_API_KEY` | None | Required for OpenAI provider |

## Quirks

- **No tests**: `frontend/package.json` has no test scripts. Backend has no test runner.
- **No lint/typecheck**: Frontend uses strict TypeScript but no pre-commit hooks.
- **Docker multi-stage**: Builds frontend first (node:20-alpine), then Python backend, then combines in final image.
- **FastEmbed cache**: Requires `HF_HOME` set to writeable path. Docker sets this to `/app/.cache`.
- **CORS**: Backend allows `*` origins. No authentication on API endpoints.
- **In-memory chat**: Chat history is lost on server restart. No database.