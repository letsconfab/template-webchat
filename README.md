# AI Copilot Chat with Knowledge Base

A multi-tenant AI copilot chat application with RAG (Retrieval Augmented Generation) capabilities. Built with FastAPI backend, React frontend, and supports multiple LLM providers (OpenAI, Groq, Ollama, Sarvam).

## Features

- **Multi-Tenant Architecture**: Each browser session has a unique ID with isolated chat history
- **Multiple LLM Providers**: OpenAI, Groq, Ollama (local), Sarvam
- **Dynamic Model Fetching**: Models are fetched live from provider APIs (no hardcoding)
- **Knowledge Base RAG**: Supports PDF, DOCX, DOC, CSV, XLSX, TXT files
- **In-Memory Vector Store**: Uses Qdrant for fast document retrieval
- **Streaming Responses**: Real-time chat via WebSocket
- **Chat History**: Conversation history stored in backend, persisted across refreshes
- **Session Management**: UUID-based sessions with sessionStorage
- **Langfuse Observability**: Track and monitor conversations
- **Configurable via .env**: Easy setup with environment variables
- **React Frontend**: Modern UI with TailwindCSS and Radix UI

## Quick Start

### 1. Install Backend Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

### 3. Add Knowledge Base Documents

Create a `kb_assets` folder and add your documents:

```bash
mkdir kb_assets
# Add PDF, DOCX, CSV, XLSX, TXT files here
```

### 4. Run the Backend

```bash
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

The backend API will be available at `http://localhost:8000`

### 5. Run the Frontend (Development)

```bash
cd frontend
npm install
npm run dev
```

The frontend will be available at `http://localhost:3000`

## Architecture

### Backend (FastAPI)
- **WebSocket**: Real-time streaming chat responses
- **API Endpoints**: Health check, providers, models, settings, chat history
- **Session Management**: UUID-based sessions stored in sessionStorage
- **Chat History**: In-memory storage per session
- **Knowledge Base**: Document loading, chunking, and Qdrant vector store
- **Multi-LLM Support**: OpenAI, Groq, Ollama, Sarvam with dynamic model fetching

### Frontend (React)
- **Vite**: Fast development server with HMR
- **TailwindCSS**: Utility-first styling
- **Radix UI**: Accessible UI components
- **Lucide Icons**: Beautiful icon set
- **WebSocket Client**: Real-time streaming with reconnection handling
- **Session Storage**: Persistent session ID across page refreshes
- **Settings Modal**: Multi-step configuration (provider → API key → model)

### Session & Chat History
- Each browser session gets a unique UUID stored in sessionStorage
- Chat history is stored in backend memory keyed by session ID
- History is automatically loaded when WebSocket connects
- Clear history button in header to reset conversation
- Settings (provider, model, API key) persisted in localStorage

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `PURPOSE` | Define the AI's role and purpose | No (default provided) |
| `GAURDRAILS` | Safety guidelines and boundaries | No (default provided) |
| `STORE_CHAT_THREADS` | Enable/disable chat history | No (default: true) |
| `USE_EMAIL_AS_IDENTIFIER` | Use email as user ID | No (default: true) |
| `KB_ASSETS_DIR` | Directory containing documents | No (default: ./kb_assets) |
| `LANGFUSE_BASE_URL` | Langfuse server URL | No |
| `LANGFUSE_PUBLIC_KEY` | Langfuse public key | No |
| `LANGFUSE_SECRET_KEY` | Langfuse secret key | No |
| `OPENAI_API_KEY` | OpenAI API key (fallback) | No |

## API Endpoints

- `GET /health` - Health check
- `GET /api/providers` - List available LLM providers
- `POST /api/models` - Get models for a provider (dynamic fetching)
- `POST /api/validate-key` - Validate API key
- `POST /api/settings` - Update user settings
- `GET /api/chat-history?session_id={id}` - Get chat history
- `DELETE /api/chat-history?session_id={id}` - Clear chat history
- `WS /ws/chat` - WebSocket for streaming chat

## Project Structure

```
.
├── backend/
│   ├── main.py              # FastAPI application with WebSocket
│   ├── config.py            # Configuration loader
│   ├── knowledge_base.py    # Document loading and vector store
│   └── llm_providers.py     # Multi-provider LLM with dynamic model fetching
├── frontend/
│   ├── src/
│   │   ├── components/      # React components
│   │   │   ├── ChatInterface.tsx
│   │   │   ├── SettingsModal.tsx
│   │   │   └── WelcomeScreen.tsx
│   │   ├── services/        # API service and WebSocket client
│   │   ├── lib/             # Utilities
│   │   └── App.tsx          # Main app with session management
│   ├── package.json
│   └── vite.config.ts
├── requirements.txt         # Python dependencies
├── Dockerfile              # Multi-stage build for production
├── .env.example            # Example environment variables
└── kb_assets/              # Knowledge base documents (create this)
```

## Deployment to Coolify

This project includes a `Dockerfile` ready for deployment on [Coolify](https://coolify.io/).

### Coolify Setup Steps:

1. **Push to Git**: Push your code to a Git repository (GitHub, GitLab, etc.)

2. **Create Resource in Coolify**:
   - Add a new "Application" resource
   - Select your Git repository
   - Choose "Dockerfile" as the build method
   - Set port to **8000**

3. **Environment Variables**: Add all variables from `.env.example`:
   - `PURPOSE`, `GAURDRAILS` (optional)
   - `KB_ASSETS_DIR=/app/kb_assets` (important: use absolute path)
   - Optional: `LANGFUSE_*` keys for observability

4. **Persistent Storage**: Add a persistent storage volume:
   - Container Path: `/app/kb_assets`
   - This preserves your knowledge base files

5. **Health Check**: Already configured in Dockerfile at `/health`

6. **Deploy**: Click "Deploy" and Coolify will build and run your app

### Local Docker Build

```bash
docker build -t copilot-chat .
docker run -p 8000:8000 --env-file .env -v $(pwd)/kb_assets:/app/kb_assets copilot-chat
```

## Development

### Adding New File Types

Edit `backend/knowledge_base.py` and add loaders in `_get_loader()` method.

### Adding New LLM Providers

Edit `backend/llm_providers.py` and add the provider implementation in `get_available_models()` function.

### Customizing the System Prompt

Modify the `PURPOSE` and `GAURDRAILS` environment variables in your `.env` file.

MIT
