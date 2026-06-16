# Template Webchat

AI chat application with authentication, admin tooling, and a knowledge-book pipeline powered by a separate RAG-Anything container.

## What It Does

- Authenticated chat UI at `/chat`
- Admin login, registration, and invite flow
- First-time setup wizard at `/setup`
- Admin dashboard and system settings
- Knowledge book workflow at `/admin/knowledge`
- Upload PDFs, DOCX, and Markdown files
- Convert uploaded sources into a 3-level knowledge book:
  - chapter
  - topic
  - page
- Store raw source files locally for auditing and reprocessing
- Redact obvious PII before building the book
- Ground chat through the external RAG-Anything container once the book is ready
- Keep the published knowledge book read-only
- Allow draft patches to be edited before commit and audited with user + timestamp

## Current Route Map

- `/setup` - first-time configuration wizard
- `/login` - user login
- `/register` - user registration
- `/dashboard` - authenticated dashboard
- `/chat` - authenticated chat interface
- `/admin/dashboard` - admin dashboard
- `/admin/settings` - system settings
- `/admin/knowledge` - knowledge book workflow
- `/admin/feedback` - feedback review
- `/admin/insights` - insights review

## Features

### Chat

- WebSocket streaming responses
- Session-based conversation history
- LLM provider support:
  - OpenAI
  - Groq
  - Ollama
  - Sarvam
- Provider/model selection comes from backend settings
- Grounded answers come from the RAG-Anything service container
- If the knowledge book is not ready, chat tells the user to try again later

### Admin

- Login and role-based access control
- User invitation system
- System settings management
- Knowledge book uploads and review
- Draft patch editing and commit flow
- Audit log of knowledge book changes

### Knowledge Book

- Upload `PDF`, `DOCX`, and `MD` files
- Create notes as markdown input
- Auto-generate a structured draft
- Enforce a maximum depth of 3 levels
- Redact obvious PII from generated content
- Commit approved patches to the active book
- Reindex the active book into the external RAG-Anything service

## Quick Start

### Local

Run these commands from the repo root:

```bash
make setup
make install
make install-fe
make smoke-rag
make run
```

`make smoke-rag` starts the separate RAG-Anything container and checks that it is healthy. If you are using Docker Compose for everything, you can also run `docker compose up -d` instead of starting pieces individually.

The frontend dev server runs on `http://localhost:3030` and the backend runs on `http://localhost:8000`.

### Docker

```bash
docker compose up -d
```

Then open `http://localhost:8000`.

This starts:
- backend app
- PostgreSQL
- Qdrant
- Garage-compatible storage
- RAG-Anything service on Python 3.13
- RAG service health endpoint on `http://localhost:8010/health`

## First-Time Setup

1. Open `http://localhost:3030` in local development or `http://localhost:8000` in Docker.
2. You will be redirected to `/setup`.
3. Complete the setup wizard:
   - admin account
   - app name and email settings
   - SMTP settings
   - LLM provider, model, and API key
   - optional Foundry connection fields
4. After setup, log in and open the admin dashboard.
5. Upload documents in `/admin/knowledge` to build the knowledge book.
6. Configure the separate RAG provider/model/API key/base URL in `/admin/settings` if you want grounding to use values different from chat.

## Build

### Backend

```bash
make install
```

### Frontend

```bash
make build
```

## Run Commands

Available Make targets:

- `make setup` - create the database
- `make install` - install backend dependencies and create `.venv`
- `make install-full` - install backend dependencies and skip the broken in-process RAG dependency
- `make install-fe` - install frontend dependencies
- `make run` - run backend and frontend
- `make run-be` - run backend only
- `make run-fe` - run frontend only
- `make run-db` - start PostgreSQL in Docker
- `make smoke-rag` - start the RAG service and check its health
- `make build` - build the frontend for production
- `make dev` - run the frontend dev server
- `make clean` - remove build artifacts and local virtualenv

## Environment Variables

### Required

- `DATABASE_URL` - PostgreSQL connection string
- `SECRET_KEY` - JWT secret key

### Knowledge Book / RAG

- `RAG_SERVICE_URL` - internal URL for the separate RAG-Anything service
- `KNOWLEDGE_STORAGE_DIR` - filesystem location for raw source files and generated snapshots

### Email / Auth

- `SMTP_SERVER`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `FROM_EMAIL`
- `USE_EMAIL_AS_IDENTIFIER`

### Observability

- `LANGFUSE_BASE_URL`
- `LANGFUSE_PUBLIC_KEY`
- `LANGFUSE_SECRET_KEY`

## Important Ports

- Frontend dev server: `3030`
- Backend API: `8000`
- PostgreSQL: `5432` in Docker, `5454` in some local docs/scripts
- Qdrant: `6333`
- Garage: `3900`
- RAG-Anything service: `8010` inside Docker network and on the host when using Docker Compose

## API Overview

### Auth

- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `POST /api/auth/logout`

### Setup / Settings

- `GET /api/settings/config-status`
- `POST /api/settings/configure`
- `GET /api/settings/current`
- `PUT /api/settings/current`
- `POST /api/settings/reset-configuration`
- `GET /api/settings/chat-config`

### Knowledge Book

- `GET /api/knowledge/status`
- `GET /api/knowledge/sources`
- `POST /api/knowledge/upload`
- `POST /api/knowledge/note`
- `GET /api/knowledge/patches`
- `GET /api/knowledge/patches/{patch_id}`
- `PUT /api/knowledge/patches/{patch_id}`
- `POST /api/knowledge/patches/{patch_id}/commit`
- `GET /api/knowledge/tree`
- `GET /api/knowledge/audit`
- `POST /api/knowledge/reindex`

### Chat

- `WS /ws/chat`
- `GET /api/chat-history?session_id={id}`
- `DELETE /api/chat-history?session_id={id}`

## Project Structure

```text
.
|-- backend/
|   |-- main.py
|   |-- config.py
|   |-- database.py
|   |-- llm_providers.py
|   |-- models/
|   |   |-- user.py
|   |   |-- invite.py
|   |   |-- settings.py
|   |   |-- wiki.py
|   |   |-- knowledge.py
|   |   |-- knowledge_book.py
|   |-- routers/
|   |   |-- auth.py
|   |   |-- users.py
|   |   |-- invites.py
|   |   |-- settings.py
|   |   |-- knowledge.py
|   |   |-- feedback.py
|   |   |-- insights.py
|   |   |-- wiki.py
|   |-- services/
|   |   |-- auth.py
|   |   |-- email.py
|   |   |-- settings_service.py
|   |   |-- rag_anything_service.py
|   |   |-- knowledge_book_service.py
|-- rag_service/
|   |-- app.py
|   |-- Dockerfile
|-- frontend/
|   |-- src/
|   |   |-- pages/
|   |   |   |-- AdminDashboard.tsx
|   |   |   |-- AdminSettings.tsx
|   |   |   |-- ChatPage.tsx
|   |   |   |-- KnowledgeBook.tsx
|   |-- package.json
|   |-- vite.config.ts
|-- migrations/
|-- Dockerfile
|-- docker-compose.yml
|-- requirements.txt
```

## Notes

- The old settings-based knowledge base UI has been removed.
- The current knowledge pipeline uses the external RAG-Anything service container.
- Raw document files are kept separately from the generated knowledge book.
- The knowledge book itself is generated and reviewed through draft patches instead of freeform editing.

## Development Tips

- If the frontend dev server is running, open `http://localhost:3030`.
- If you are using Docker, open `http://localhost:8000`.
- If the chat says the knowledge book is still processing, wait for ingestion to finish or refresh the knowledge book page.
- For a clean reset of the app configuration, use `/admin/settings` and the reset action there.

## Production Deployment

> **The authoritative deployment runbook is [`DEPLOYMENT.md`](DEPLOYMENT.md).**
> It documents how production *actually* runs today (a `screen` session under
> `uvicorn --reload`, Caddy, Dockerized stores) and the one non-obvious step:
> the host has no Node, so the pre-built frontend bundle must be shipped manually.
> Read that file before deploying.

### Optional hardening: run under systemd (not currently installed)

Instead of a `screen`/`tmux` session, the backend *can* run under systemd so it
auto-restarts on failure. This is optional and not the current production setup:

```bash
# One-time setup (paths assume /home/admin/deployments/template-webchat)
sudo cp scripts/webchat.service /etc/systemd/system/webchat.service
sudo systemctl daemon-reload
sudo systemctl enable --now webchat

# Logs / status
journalctl -u webchat -f
systemctl status webchat
```

Before starting, make sure the server `.env` sets `ENVIRONMENT=production`, a strong
`SECRET_KEY`, a non-default `NEO4J_PASSWORD`, and `FRONTEND_URL` pointing at the public
domain — the app refuses to start in production with default secrets. Retire any old
screen/tmux session running `make run-be`; for a manual production-mode run use
`make run-be-prod` (no auto-reload).
