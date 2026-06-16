# DEPLOYMENT.md — Production Deployment Methodology

> **Audience:** human maintainers and coding agents shipping this app to production.
> **Status:** living document. See [Keeping this document current](#keeping-this-document-current) and the [Revision history](#revision-history).
> **Last verified:** 2026-06-16.

> [!IMPORTANT]
> **This repository is public.** Do **not** commit production connection specifics
> (host IPs, SSH user/key, login commands) or any secrets (keys, passwords, tokens)
> into tracked files. The concrete values for the `$VARIABLES` used below live in a
> **gitignored** `deploy.local.md` and in the server's `.env`. This document
> describes the *method*; `deploy.local.md` supplies the *targets*.

---

## TL;DR

Production runs the FastAPI backend directly on an EC2 host inside a `screen`
session under `uvicorn --reload`, fronted by Caddy (TLS) and backed by Dockerized
Postgres/Neo4j/Qdrant. **Deploying = push to `main`, then on the host `git pull` +
ship the pre-built frontend bundle (the host has no Node) + let `--reload` restart
the backend.** Database migrations apply automatically on startup.

```bash
# 0. locally: merge work to main and push
git checkout main && git merge --ff-only <feature-branch> && git push origin main

# 1. build the frontend locally (the server cannot build it)
cd frontend && npm run build && cd ..

# 2. on the host: pull backend code (see deploy.local.md for $VARS)
ssh -i $SSH_KEY $DEPLOY_USER@$DEPLOY_HOST \
  "cd $DEPLOY_DIR && git checkout -- frontend/dist/index.html && git pull --ff-only origin $DEPLOY_BRANCH"

# 3. ship the built frontend (index.html + hashed assets)
scp -i $SSH_KEY frontend/dist/index.html $DEPLOY_USER@$DEPLOY_HOST:$DEPLOY_DIR/frontend/dist/index.html
scp -i $SSH_KEY frontend/dist/assets/*  $DEPLOY_USER@$DEPLOY_HOST:$DEPLOY_DIR/frontend/dist/assets/

# 4. backend auto-reloads on the .py changes; verify
curl -s $PUBLIC_URL/health   # -> {"status":"healthy"}
```

---

## Environment facts (single source of truth)

These are the variables the runbook references. **Concrete values are in the
gitignored `deploy.local.md`.** Keep that table and this one in sync.

| Variable         | Meaning                                                        |
|------------------|----------------------------------------------------------------|
| `$PUBLIC_URL`    | Public HTTPS URL (Caddy-terminated)                            |
| `$DEPLOY_HOST`   | Production host (EC2) — public IP or DNS                       |
| `$DEPLOY_USER`   | SSH user on the host                                           |
| `$SSH_KEY`       | Path to the SSH private key (local machine only)              |
| `$DEPLOY_DIR`    | Git checkout the running process serves                        |
| `$DEPLOY_BRANCH` | Branch production tracks (currently `main`)                    |

---

## Architecture: how production actually runs

```
Internet ──HTTPS──> Caddy (docker: caddy-caddy-1)
                      │  reverse_proxy <bridge-gateway>:8000
                      ▼
            uvicorn backend.main:app  (host process, port 8000)
            run inside `screen -S webchat`, flag: --reload
                      │
                      ├── serves the React SPA from frontend/dist/  (catch-all route)
                      └── talks to Dockerized stores:
                            • webchat-db     (Postgres   — app data + feedback)
                            • webchat-neo4j  (graph      — GraphRAG entities)
                            • webchat-qdrant (vectors    — kb_chunks, 384-dim)
```

Key properties:

- **Process manager is `screen`, not systemd.** The backend lives in a detached
  `screen` session named `webchat`. (Sibling sessions: `db`, `caddy`, `fe`.)
  A `scripts/webchat.service` systemd unit exists in the repo but **is not
  installed** on the host — don't assume `systemctl` controls the app.
- **`uvicorn --reload` is on in production.** Editing/pulling `.py` files triggers
  an automatic worker restart, which re-runs the FastAPI lifespan
  (`init_db` → `run_migrations`). This is why a plain `git pull` is usually enough
  to deploy backend changes and apply migrations — no manual restart needed.
- **The frontend is served from `frontend/dist/`** by the backend's catch-all
  route (and/or Caddy). It is a static, pre-built bundle.

---

## The one non-obvious constraint: shipping the frontend

> [!WARNING]
> **The host has no Node/npm, and `frontend/dist/assets/*` is gitignored.**

Consequences you must account for on every frontend change:

1. `git pull` on the host updates the tracked `frontend/dist/index.html`, which
   references a **content-hashed** bundle (e.g. `index-ABC123.js`).
2. But the hashed asset files themselves are **not in git** and **cannot be built
   on the host**. So after a pull, `index.html` points at a bundle that isn't
   there → blank/broken UI.
3. **You must `scp` the locally-built `dist/index.html` + `dist/assets/*`** to the
   host so the referenced bundle exists. Hashed filenames make this safe and
   additive (old bundles simply become unreferenced).
4. The host also keeps a **locally-built `dist/index.html`** that differs from the
   committed one, which **blocks `git pull`** with a "local changes would be
   overwritten" error. Run `git checkout -- frontend/dist/index.html` first
   (safe — you overwrite the whole `dist` via scp anyway).

If you change only backend code, steps 1/3 are unnecessary — just `git pull`.

---

## Runbook

### Prerequisites
- SSH access to the host (key in `$SSH_KEY`); values in `deploy.local.md`.
- Local Node toolchain (to build the frontend) and a clean local clone.
- Write access to `origin/main`.

### Steps
1. **Land code on `main`.** Production tracks `main`. Merge your branch
   (usually a clean fast-forward) and `git push origin main`.
2. **Build the frontend locally:** `cd frontend && npm run build`. Note the bundle
   hash in `dist/index.html` matches `dist/assets/`.
3. **Pull backend code on the host:**
   `cd $DEPLOY_DIR && git checkout -- frontend/dist/index.html && git pull --ff-only origin $DEPLOY_BRANCH`.
4. **Ship the frontend** (only if the frontend changed): scp `dist/index.html` and
   `dist/assets/*` into `$DEPLOY_DIR/frontend/dist/`.
5. **Backend restart:** normally automatic via `--reload`. Confirm a fresh worker
   (see [Verification](#verification)). If it didn't reload, see
   [Restarting the backend manually](#restarting-the-backend-manually).
6. **Migrations:** apply automatically on startup via `run_migrations()` (idempotent,
   guarded with `IF NOT EXISTS` / `information_schema` checks). No manual step.

---

## Verification

```bash
# public health + that the SPA points at a bundle that actually exists
curl -s $PUBLIC_URL/health                                   # {"status":"healthy"}
BUNDLE=$(curl -s $PUBLIC_URL/ | grep -oE '/assets/index-[A-Za-z0-9_-]+\.js')
curl -s -o /dev/null -w "%{http_code}\n" $PUBLIC_URL$BUNDLE  # 200

# confirm an auth-gated API still enforces auth
curl -s -o /dev/null -w "%{http_code}\n" $PUBLIC_URL/api/feedback/admin  # 401
```

On the host, confirm the backend worker actually restarted (fresh `ELAPSED`):

```bash
ssh -i $SSH_KEY $DEPLOY_USER@$DEPLOY_HOST \
  'P=$(pgrep -f "uvicorn backend.main" | head -1); ps --ppid $P -o pid,etime,cmd'
```

For a behavior-level check, exercise the changed feature (e.g. a chat query to
confirm GraphRAG grounding, or `/api/feedback/admin` shape with an admin token).

---

## Rollback

Because deploys are a `git pull` + scp, rollback is a checkout of the previous
commit plus re-shipping that commit's frontend build:

```bash
# on the host: roll backend code back
ssh -i $SSH_KEY $DEPLOY_USER@$DEPLOY_HOST \
  "cd $DEPLOY_DIR && git checkout -- frontend/dist/index.html && git reset --hard <previous-good-sha>"
# locally: rebuild that SHA's frontend and scp dist/* back (see Runbook step 4)
```

`--reload` picks up the reverted `.py` files automatically. Prefer rolling
`main` back with a revert commit if the bad code was already pushed.

---

## Restarting the backend manually

Only needed if `--reload` didn't pick up changes (rare) or you changed
non-watched files. The backend runs in `screen -S webchat`:

```bash
ssh -i $SSH_KEY $DEPLOY_USER@$DEPLOY_HOST
screen -r webchat          # attach
# Ctrl-C to stop uvicorn, then re-run the start command, then Ctrl-A D to detach
# Start command (from $DEPLOY_DIR):
#   PYTHONPATH=.::./backend .venv/bin/uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

> Risk: a failed restart takes the site down. Verify health immediately after.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Blank page / 404 on `/assets/index-*.js` | Frontend bundle not shipped after pull | scp `dist/index.html` + `dist/assets/*` (see [shipping the frontend](#the-one-non-obvious-constraint-shipping-the-frontend)) |
| `git pull` aborts: "local changes would be overwritten: frontend/dist/index.html" | Host's locally-built index.html | `git checkout -- frontend/dist/index.html` then pull |
| Chat answers hallucinate / ignore the knowledge base | Neo4j or Qdrant container down → retrieval tool silently disabled | `docker ps` on host; restart `webchat-neo4j` / `webchat-qdrant` |
| First chat after deploy is slow | Embedding model (`all-MiniLM-L6-v2`, ~80 MB) downloads on first GraphRAG query | One-time; warms after first request |
| Backend changes not live | `--reload` missed the change | [Restart manually](#restarting-the-backend-manually) |
| `SECRET_KEY`/`NEO4J_PASSWORD` default errors on start | Server `.env` missing production secrets | App refuses to start in production with defaults — set real values in `$DEPLOY_DIR/.env` |

---

## What this is NOT

- **Not `make docker-publish` / ghcr.io.** The Makefile can build and push an image
  to `ghcr.io/letsconfab/template-webchat`, but **nothing on the host pulls or runs
  that image** (no CI workflow, no watchtower, no Coolify). The app runs from the
  git checkout, not a container. Ignore the ghcr path unless you intentionally
  migrate to it (see [Evolving the methodology](#evolving-the-methodology)).
- **Not systemd.** Despite `scripts/webchat.service`, the unit is not installed.

---

## Keeping this document current

This file is meant to **evolve**. When you change deployment in any way:

1. Update the relevant section here **in the same PR** as the infra change.
2. If a `$VARIABLE`'s value changes (host, branch, dir), edit **`deploy.local.md`**
   (not this file) so this file stays secret-free.
3. Bump the **Last verified** date at the top when you've re-confirmed the steps
   end-to-end against production.
4. Add a row to the [Revision history](#revision-history).
5. Keep `README.md` and `AGENTS.md` pointing here rather than duplicating steps.

### Evolving the methodology

Likely future migrations and what to change here when they happen:

- **screen → systemd:** install `scripts/webchat.service`, replace the
  [manual restart](#restarting-the-backend-manually) and process-check commands
  with `systemctl restart/status webchat`, and update the Architecture diagram.
- **Manual scp → committed/built frontend:** if `frontend/dist` is committed, or a
  build step is added on the host (install Node) or in CI, delete the
  [shipping-the-frontend](#the-one-non-obvious-constraint-shipping-the-frontend)
  workaround and document the new path.
- **git-pull → image-based (ghcr/Coolify):** move the runbook to "push image →
  trigger redeploy", and move the [What this is NOT](#what-this-is-not) ghcr note
  into the main flow.
- **Manual → CI/CD:** if a GitHub Actions workflow is added, this file becomes the
  description of what the pipeline does; link the workflow file.

---

## Revision history

| Date       | Change | By |
|------------|--------|----|
| 2026-06-16 | Initial methodology captured: screen + `uvicorn --reload`, Caddy, Dockerized stores, manual frontend scp, auto-migrations. Documented the no-Node/gitignored-assets constraint and the ghcr/systemd red herrings. | agent |
