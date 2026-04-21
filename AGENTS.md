# AGENTS.md - Demo Branch

## Running the Application

### Quick Start (Local)

```bash
# Initial setup (creates DB + installs deps)
make setup
make install
make install-fe

# Run both backend and frontend
make run
```

### Quick Start (Docker)

```bash
docker-compose up -d
```

Then visit `http://localhost:3000`

### Available Make Commands

| Command | Description |
|---------|-------------|
| `make setup` | Create database |
| `make install` | Install backend dependencies (creates venv) |
| `make install-fe` | Install frontend dependencies |
| `make run` | Run both backend and frontend |
| `make run-be` | Run backend only |
| `make run-fe` | Run frontend only |
| `make build` | Build frontend for production |
| `make dev` | Run in development mode |
| `make clean` | Clean build artifacts |

### Manual Setup

#### 1. Database
```bash
createdb webchat_db
```

#### 2. Environment
Create `.env` file:
```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/webchat_db
SECRET_KEY=your-secret-key-change-in-production
```

#### 3. Install Dependencies
```bash
# Backend
pip install -r requirements.txt
# Or: make install

# Frontend
cd frontend && npm install
# Or: make install-fe
```

#### 4. Run
```bash
# Backend (Terminal 1)
make run-be

# Frontend (Terminal 2)
make run-fe
```

## First-Time Setup Flow

1. Visit `http://localhost:3000` → redirects to `/setup`
2. Complete Configuration Wizard:
   - **Step 1**: Admin account (email + password)
   - **Step 2**: App name + from email
   - **Step 3**: SMTP settings
   - **Step 4**: LLM provider, model, API key
   - **Step 5** (optional): Connect Foundry
3. After success → redirect to `/login`
4. Login → `/admin/dashboard`

## Routes

| Path | Access | Description |
|------|--------|-------------|
| `/setup` | Public (first-time) | Configuration wizard |
| `/login` | Public | User login |
| `/register` | Public | User registration |
| `/dashboard` | Authenticated | User dashboard |
| `/chat` | Authenticated | Chat interface |
| `/admin/dashboard` | Admin | Admin dashboard |
| `/admin/settings` | Admin | System settings |

## Ports

| Service | Port |
|---------|------|
| Frontend (dev) | 3000 |
| Backend | 8005 |
| PostgreSQL | 5432 |

## Environment Variables

| Variable | Default | Notes |
|----------|---------|-------|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/webchat_db` | |
| `SECRET_KEY` | - | JWT secret |
| `KB_ASSETS_DIR` | `./kb_assets` | Knowledge base files |

## Docker Compose

The project includes `docker-compose.yml` for running all services:

```bash
docker-compose up -d
```

This starts:
- PostgreSQL (port 5432)
- Backend API (port 8005)
- Frontend dev server (port 3000)