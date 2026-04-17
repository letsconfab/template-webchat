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
- **User Authentication**: JWT-based authentication with role-based access control
- **Admin Panel**: User management and invitation system
- **Email Invitations**: Admin can invite users via email with secure tokens
- **PostgreSQL Database**: Persistent storage for users and invitations
- **Role-Based Access**: Admin and user roles with appropriate permissions

## Quick Start

### 1. Install Backend Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Up PostgreSQL Database

Create a PostgreSQL database and update the `DATABASE_URL` in your `.env` file:

```bash
# Example DATABASE_URL format:
DATABASE_URL=postgresql+asyncpg://username:password@localhost:5432/webchat_db
```

### 3. Configure Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

**Required for Authentication:**
- `DATABASE_URL`: PostgreSQL connection string
- `SECRET_KEY`: JWT secret key (change in production)
- `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `FROM_EMAIL`: Email settings for invitations

### 4. Add Knowledge Base Documents

Create a `kb_assets` folder and add your documents:

```bash
mkdir kb_assets
# Add PDF, DOCX, CSV, XLSX, TXT files here
```

### 5. Run the Backend

```bash
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

The backend API will be available at `http://localhost:8000`

### 6. Run the Frontend (Development)

```bash
cd frontend
npm install
npm run dev
```

The frontend will be available at `http://localhost:3000`

### 7. Create First Admin User

After starting the backend, create an admin user via the API:

```bash
curl -X POST "http://localhost:8000/api/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "admin123", "role": "admin"}'
```

Then update their role in the database or use the admin panel to manage users.

## Architecture

### Backend (FastAPI)
- **WebSocket**: Real-time streaming chat responses
- **API Endpoints**: Health check, providers, models, settings, chat history
- **Session Management**: UUID-based sessions stored in sessionStorage
- **Chat History**: In-memory storage per session
- **Knowledge Base**: Document loading, chunking, and Qdrant vector store
- **Multi-LLM Support**: OpenAI, Groq, Ollama, Sarvam with dynamic model fetching
- **Authentication**: JWT-based authentication with role-based access control
- **User Management**: Admin panel for managing users and invitations
- **Email Service**: SMTP-based email invitations with secure tokens
- **Database**: PostgreSQL for persistent user and invitation storage

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

### Chat & LLM
- `GET /health` - Health check
- `GET /api/providers` - List available LLM providers
- `POST /api/models` - Get models for a provider (dynamic fetching)
- `POST /api/validate-key` - Validate API key
- `POST /api/settings` - Update user settings
- `GET /api/chat-history?session_id={id}` - Get chat history
- `DELETE /api/chat-history?session_id={id}` - Clear chat history
- `WS /ws/chat` - WebSocket for streaming chat

### Authentication
- `POST /api/auth/register` - User registration
- `POST /api/auth/login` - User login (returns JWT token)
- `GET /api/auth/me` - Get current user info
- `POST /api/auth/logout` - User logout

### Admin Management (Admin only)
- `GET /api/admin/users` - List all users
- `GET /api/admin/users/{id}` - Get specific user
- `PUT /api/admin/users/{id}` - Update user (role, status)
- `DELETE /api/admin/users/{id}` - Delete user
- `GET /api/admin/users/stats` - User statistics

### Invitation System
- `POST /api/admin/invite-user` - Create and send invitation (Admin)
- `GET /api/admin/invites` - List all invitations (Admin)
- `DELETE /api/admin/invites/{id}` - Cancel invitation (Admin)
- `GET /api/accept-invite/{token}` - Check invitation validity
- `POST /api/accept-invite/{token}` - Accept invitation and create account

## Project Structure

```
.
|-- backend/
|   |-- main.py              # FastAPI application with WebSocket
|   |-- config.py            # Configuration loader
|   |-- database.py          # Database connection and setup
|   |-- knowledge_base.py    # Document loading and vector store
|   |-- llm_providers.py     # Multi-provider LLM with dynamic model fetching
|   |-- models/              # Database models
|   |   |-- user.py          # User model
|   |   |-- invite.py        # Invitation model
|   |-- routers/             # API routers
|   |   |-- auth.py          # Authentication endpoints
|   |   |-- users.py         # User management endpoints
|   |   |-- invites.py       # Invitation endpoints
|   |-- services/            # Business logic services
|   |   |-- auth.py          # Authentication utilities
|   |   |-- email.py         # Email service
|   |-- middleware/          # Custom middleware
|   |   |-- auth.py          # Authentication middleware
|   |-- schemas/             # Pydantic schemas
|   |   |-- user.py          # User schemas
|   |   |-- invite.py        # Invitation schemas
|-- frontend/
|   |-- src/
|   |   |-- components/      # React components
|   |   |   |-- auth/        # Authentication components
|   |   |   |   |-- LoginForm.tsx
|   |   |   |   |-- InviteAcceptForm.tsx
|   |   |   |-- admin/       # Admin panel components
|   |   |   |   |-- InviteUser.tsx
|   |   |   |   |-- UserList.tsx
|   |   |   |-- ui/          # UI components
|   |   |   |   |-- button.tsx
|   |   |   |   |-- input.tsx
|   |   |   |   |-- label.tsx
|   |   |   |   |-- card.tsx
|   |   |   |   |-- badge.tsx
|   |   |   |   |-- table.tsx
|   |   |   |-- ChatInterface.tsx
|   |   |   |-- SettingsModal.tsx
|   |   |   |-- WelcomeScreen.tsx
|   |   |-- contexts/        # React contexts
|   |   |   |-- AuthContext.tsx
|   |   |-- services/        # API service and WebSocket client
|   |   |-- lib/             # Utilities
|   |   |-- App.tsx          # Main app with session management
|   |-- package.json
|   |-- vite.config.ts
|-- requirements.txt         # Python dependencies
|-- Dockerfile              # Multi-stage build for production
|-- .env.example            # Example environment variables
|-- kb_assets/              # Knowledge base documents (create this)
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
