# DEPLOYMENT.md — Production Deployment Methodology

> **Audience:** human maintainers and coding agents shipping this app to production.
> **Status:** living document. See [Keeping this document current](#keeping-this-document-current) and the [Revision history](#revision-history).
> **Last verified:** 2026-07-02.

> [!IMPORTANT]
> **This repository is public.** Do **not** commit production connection specifics
> (host IPs, SSH user/key, login commands) or any secrets (keys, passwords, tokens)
> into tracked files. The concrete values for the `$VARIABLES` used below live in a
> **gitignored** `deploy.local.md` and in the server's `.env`. This document
> describes the *method*; `deploy.local.md` supplies the *targets*.

---

## TL;DR

Production runs the FastAPI backend directly on an EC2 host as a **systemd
service** (`webchat`), fronted by Caddy (TLS) and backed by Dockerized
Postgres/Neo4j/Qdrant. **Deploying = push to `main`, then on the host `git pull` +
ship the pre-built frontend bundle (the host has no Node) + run the migration
preflight + `sudo systemctl restart webchat`.** Python 3.13 is required. The
systemd unit also runs the migration preflight and refuses to start on failure.

```bash
# 0. locally: merge work to main and push
git checkout main && git merge --ff-only <feature-branch> && git push origin main

# 1. build the frontend locally (the server cannot build it)
cd frontend && npm run build && cd ..

# 2. on the host: pull code, preflight dependencies/disk, then prepare the release environment
ssh -i $SSH_KEY $DEPLOY_USER@$DEPLOY_HOST \
  "cd $DEPLOY_DIR && PREVIOUS_SHA=\$(git rev-parse HEAD) && \
   git checkout -- frontend/dist/index.html && git pull --ff-only origin $DEPLOY_BRANCH && \
   RELEASE_SHA=\$(git rev-parse HEAD) && python3.13 scripts/check_production_dependencies.py && \
   python3.13 -m venv .venv.release-\$RELEASE_SHA && \
   .venv.release-\$RELEASE_SHA/bin/pip install -r requirements-production.txt && \
   HF_HOME=.cache/huggingface .venv.release-\$RELEASE_SHA/bin/python -c \
     'from sentence_transformers import SentenceTransformer; m = SentenceTransformer(\"sentence-transformers/all-MiniLM-L6-v2\", device=\"cpu\"); assert m.device.type == \"cpu\"' && \
   .venv.release-\$RELEASE_SHA/bin/python -c 'import backend.main' && \
   mv .venv .venv.rollback-\$PREVIOUS_SHA && mv .venv.release-\$RELEASE_SHA .venv"

# 3. ship the built frontend (index.html + hashed assets)
scp -i $SSH_KEY frontend/dist/index.html $DEPLOY_USER@$DEPLOY_HOST:$DEPLOY_DIR/frontend/dist/index.html
scp -i $SSH_KEY frontend/dist/assets/*  $DEPLOY_USER@$DEPLOY_HOST:$DEPLOY_DIR/frontend/dist/assets/

# 4. migrate, restart the backend service, then verify
ssh -i $SSH_KEY $DEPLOY_USER@$DEPLOY_HOST \
  "cd $DEPLOY_DIR && .venv/bin/python scripts/migrate.py upgrade && sudo systemctl restart webchat"
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
            run as systemd service `webchat` (auto-starts on boot)
                      │
                      ├── serves the React SPA from frontend/dist/  (catch-all route)
                      └── talks to Dockerized stores:
                            • webchat-db     (Postgres   — app data + feedback)
                            • webchat-neo4j  (graph      — GraphRAG entities)
                            • webchat-qdrant (vectors    — kb_chunks, 384-dim)
```

Key properties:

- **Process manager is systemd.** The backend runs as the `webchat` service
  (installed from `scripts/webchat.service`), `enabled` so it auto-starts on boot.
  Control it with `sudo systemctl {status,restart,stop} webchat` and read logs with
  `journalctl -u webchat`.
- **No `--reload` in production.** A deploy therefore needs an explicit
  `sudo systemctl restart webchat`. `ExecStartPre` runs `alembic upgrade head`
  through the safe migration wrapper; migration failure leaves the old process
  stopped and is visible in `systemctl status`/the journal. A bare `git pull`
  alone does **not** pick up backend changes until the service is restarted.
- **The Docker stores auto-start on boot** (`restart: unless-stopped` + Docker
  enabled), and a 4 GB swapfile (`/etc/fstab`) guards against OOM on the small host.
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
- Python 3.13 on the host.
- At least 4 GiB free on the production checkout filesystem before resolving
  dependencies or creating a release virtualenv.
- Write access to `origin/main`.

### Steps
1. **Land code on `main`.** Production tracks `main`. Merge your branch
   (usually a clean fast-forward) and `git push origin main`.
2. **Build the frontend locally:** `cd frontend && npm run build`. Note the bundle
   hash in `dist/index.html` matches `dist/assets/`.
3. **Pull backend code and run the dependency/disk preflight on the host:**

   ```bash
   cd $DEPLOY_DIR
   PREVIOUS_SHA=$(git rev-parse HEAD)
   git checkout -- frontend/dist/index.html
   git pull --ff-only origin $DEPLOY_BRANCH
   RELEASE_SHA=$(git rev-parse HEAD)
   python3.13 scripts/check_production_dependencies.py
   ```

   The preflight resolves binary wheels for clean Linux CPython 3.13 before
   creating or populating a release virtualenv. It requires the official,
   hash-pinned
   `torch==2.10.0+cpu` wheel, rejects NVIDIA/CUDA/cuDNN/cuBLAS/NCCL/NVSHMEM and
   Triton packages, rejects expanded wheel payloads above the documented 3 GiB
   dependency budget, and requires 4 GiB of free disk headroom. The CPU-only
   policy is defined in `requirements-production.txt`; do not install
   `requirements.txt` directly in production. The checker bootstraps and
   removes a disposable resolver virtualenv, so the host's system Python does
   not need to expose `pip`.

4. **Build and verify an isolated release environment:**

   ```bash
   python3.13 -m venv ".venv.release-$RELEASE_SHA"
   ".venv.release-$RELEASE_SHA/bin/pip" install -r requirements-production.txt
   HF_HOME=.cache/huggingface ".venv.release-$RELEASE_SHA/bin/python" -c \
     'from sentence_transformers import SentenceTransformer; model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2", device="cpu"); assert model.device.type == "cpu"'
   ".venv.release-$RELEASE_SHA/bin/python" -c "import backend.main"
   ```

   Do not install release dependencies into the running `.venv`. Building a
   separate environment proves dependency installation and preserves the
   current environment until the release is ready. The model check also warms
   the shared Hugging Face cache and proves the configured embedding model can
   initialize without a GPU.

   If resolution, installation, or verification fails, leave the active
   `.venv` untouched. Once no install process is using it, remove only the
   partial `".venv.release-$RELEASE_SHA"` directory and retry from the
   dependency preflight. Never delete or replace `.venv`, and retain any
   `.venv.rollback-*` directory until a successful deployment has passed smoke
   tests.
5. **Activate the release environment and migrate:**

   ```bash
   mv .venv ".venv.rollback-$PREVIOUS_SHA"
   mv ".venv.release-$RELEASE_SHA" .venv
   .venv/bin/python scripts/migrate.py upgrade
   .venv/bin/python scripts/migrate.py current
   ```

   If either migration command fails, restore the previous virtualenv before
   taking any further deployment action:

   ```bash
   mv .venv ".venv.failed-$RELEASE_SHA"
   mv ".venv.rollback-$PREVIOUS_SHA" .venv
   ```

   Retain the rollback environment until the release and its smoke tests have
   been verified.
6. **Ship the frontend** (only if the frontend changed): scp `dist/index.html` and
   `dist/assets/*` into `$DEPLOY_DIR/frontend/dist/`.
7. **Restart the backend:** `sudo systemctl restart webchat`, then confirm health
   (see [Verification](#verification)).
   The systemd `ExecStartPre` repeats the idempotent migration preflight and
   refuses to start the new process if the database is not upgradeable.

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
commit, restoration of its retained virtualenv, and re-shipping that commit's
frontend build:

```bash
# on the host: roll backend code back
ssh -i $SSH_KEY $DEPLOY_USER@$DEPLOY_HOST \
  "cd $DEPLOY_DIR && git checkout -- frontend/dist/index.html && git reset --hard <previous-good-sha> && mv .venv .venv.failed && mv .venv.rollback-<previous-good-sha> .venv"
# locally: rebuild that SHA's frontend and scp dist/* back (see Runbook step 4)
```

After resetting the code, `sudo systemctl restart webchat` to load it. Prefer
rolling `main` back with a revert commit if the bad code was already pushed.

---

## Managing the backend service

The backend runs as the systemd unit `webchat`:

```bash
ssh -i $SSH_KEY $DEPLOY_USER@$DEPLOY_HOST
sudo systemctl restart webchat    # apply new code after a git pull
sudo systemctl status  webchat    # is it active? recent log lines
journalctl -u webchat -f          # follow logs
```

The unit is defined at `/etc/systemd/system/webchat.service` (installed from the
`scripts/webchat.service` template). After editing it, run
`sudo systemctl daemon-reload && sudo systemctl restart webchat`.

> Risk: a failed restart takes the site down. Verify health immediately after.

## Database upgrades and rollback

Python 3.13 is the supported local and production runtime. Before restarting,
run:

```bash
cd $DEPLOY_DIR
.venv/bin/python --version
.venv/bin/python scripts/migrate.py upgrade
.venv/bin/python scripts/migrate.py current
```

The first command upgrades a fresh database to Alembic head. For an existing
database at the supported pre-Alembic schema, it verifies the complete table
set and stamps the baseline without changing rows, then applies later
revisions. Re-execution is idempotent. Do not manually stamp partial schemas.

Verify the reported revision matches:

```bash
.venv/bin/alembic heads
```

Feature migrations are additive. Rollback means disabling the affected feature
flag and restoring the previous application revision while leaving the newer
tables/nullable columns in place. Do not run destructive downgrades in
production. Repair or roll forward a failed migration before restarting the
service.

### Feedback Case phased rollout

Keep `admin_replay_enabled`, `tester_correspondence_enabled`, and
`tester_email_notifications_enabled` disabled during the initial deploy.

1. Deploy schema, WebSocket authentication, and Execution Trace capture with
   all Feedback Case UIs disabled. Verify migration head, authenticated owner
   reconnect, cross-user denial, and trace capture failure isolation.
2. Run `make feedback-backfill` until its `pending` count is zero. Repeat runs
   are safe. Verify quarantined sessions are absent from both replay APIs,
   failed redactions remain fail-closed, replay pagination is complete, and
   account deletion covers migrated data. Enable admin replay only after
   `/api/admin/feedback-cases/rollout/readiness` reports `ready: true`.
3. Verify case transitions, the absolute authenticated deep link, generic
   email content, SMTP delivery, and retry. Then enable tester correspondence
   and tester email notifications.

Rollback disables the three flags and restores the previous application
revision. Leave the additive schema and migrated rows in place; do not
downgrade or delete backfilled data.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Blank page / 404 on `/assets/index-*.js` | Frontend bundle not shipped after pull | scp `dist/index.html` + `dist/assets/*` (see [shipping the frontend](#the-one-non-obvious-constraint-shipping-the-frontend)) |
| `git pull` aborts: "local changes would be overwritten: frontend/dist/index.html" | Host's locally-built index.html | `git checkout -- frontend/dist/index.html` then pull |
| Chat answers hallucinate / ignore the knowledge base | Neo4j or Qdrant container down → retrieval tool silently disabled | `docker ps` on host; restart `webchat-neo4j` / `webchat-qdrant` |
| First chat after deploy is slow | Embedding model (`all-MiniLM-L6-v2`, ~80 MB) downloads on first GraphRAG query | One-time; warms after first request |
| Backend changes not live after a pull | service not restarted | `sudo systemctl restart webchat` (see [Managing the backend service](#managing-the-backend-service)) |
| Site down after a reboot | a store or the backend didn't come up | check `docker ps` + `systemctl status webchat`; both are set to auto-start, so investigate logs |
| `SECRET_KEY`/`NEO4J_PASSWORD` default errors on start | Server `.env` missing production secrets | App refuses to start in production with defaults — set real values in `$DEPLOY_DIR/.env` |
| Dependency preflight reports GPU runtimes | Production Torch pin/index was removed or bypassed | Restore `requirements-production.txt`; do not create the release virtualenv |
| Dependency preflight reports insufficient disk | Fewer than 4 GiB are free on the release filesystem | Remove only stale incomplete `.venv.release-*` directories after verifying no install uses them; never remove active `.venv` |

---

## What this is NOT

- **Not `make docker-publish` / ghcr.io.** The Makefile can build and push an image
  to `ghcr.io/letsconfab/template-webchat`, but **nothing on the host pulls or runs
  that image** (no CI workflow, no watchtower, no Coolify). The app runs from the
  git checkout, not a container. Ignore the ghcr path unless you intentionally
  migrate to it (see [Evolving the methodology](#evolving-the-methodology)).

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
| 2026-06-16 | Backend moved from a `screen` session to the `webchat` **systemd** service (auto-starts on boot; deploys now `git pull` → scp frontend → `sudo systemctl restart webchat`). Stores set to `restart: unless-stopped`; 4 GB swap added; host resized t3.small→t3.medium. | agent |
| 2026-07-01 | Adopted Python 3.11 and Alembic; deployment now fails before restart when a migration fails and uses additive rollback. | agent |
| 2026-07-02 | Promoted Python 3.13 to the application runtime baseline and added isolated release virtualenv creation with retained-environment rollback. | agent |
| 2026-07-02 | Pinned production to CPU-only Torch and added Linux dependency, GPU-runtime, expanded-size, and disk-capacity preflights before release virtualenv creation. | agent |
