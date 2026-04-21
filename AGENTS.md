# AGENTS.md - Demo Branch

## Running the Application

### Quick Start

```bash
# Initial setup (creates DB + installs deps)
make setup
make install
make install-fe

# Run the application
make run
```

Or step by step:

### 1. Database
```bash
createdb webchat_db
# Or use: make setup
```

### 2. Environment
Create `.env` file in project root:
```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/webchat_db
SECRET_KEY=your-secret-key-change-in-production
```

### 3. Install Dependencies

**Backend:**
```bash
pip install -r requirements.txt
# Or: make install
```

**Frontend:**
```bash
cd frontend && npm install
# Or: make install-fe
```

### 4. Run

**Backend (Terminal 1):**
```bash
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
# Or: make run-be
```

**Frontend (Terminal 2):**
```bash
cd frontend && npm run dev
# Or: make run-fe
```

### Available Make Commands

| Command | Description |
|---------|-------------|
| `make setup` | Create database |
| `make install` | Install backend dependencies |
| `make install-fe` | Install frontend dependencies |
| `make run` | Run both backend and frontend |
| `make run-be` | Run backend only |
| `make run-fe` | Run frontend only |
| `make build` | Build frontend for production |
| `make dev` | Run in development mode |
| `make clean` | Clean build artifacts |

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

## Key Features

- **Admin creation**: Only during first-time setup (`/api/settings/configure`)
- **Role-based access**: Admin vs regular user
- **LLM config**: Admin configures in settings, shared by all users
- **Knowledge base**: Upload docs or sync from Foundry

## Environment Variables

| Variable | Default | Notes |
|----------|---------|-------|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/webchat_db` | |
| `SECRET_KEY` | - | JWT secret |
| `KB_ASSETS_DIR` | `./kb_assets` | Knowledge base files |
| `LLM_PROVIDER` | `openai` | Default LLM |
| `LLM_MODEL` | `gpt-4o-mini` | Default model |

## Database Models

- `users` - User accounts with roles (admin/user)
- `invites` - User invitations with roles
- `system_settings` - App config including LLM + Foundry settings