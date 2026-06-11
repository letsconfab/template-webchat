# Makefile for template-webchat demo branch

# Virtual environment path
VENV = .venv

# Python path
PYTHONPATH = $(CURDIR)

# Container runtime detection
CONTAINER_RUNTIME = $(shell if command -v podman >/dev/null 2>&1; then echo podman; else echo docker; fi)
COMPOSE_RUNTIME = $(shell \
	if command -v podman >/dev/null 2>&1; then \
		if podman compose version >/dev/null 2>&1; then \
			echo "podman compose"; \
		elif command -v podman-compose >/dev/null 2>&1; then \
			echo podman-compose; \
		else \
			echo "docker compose"; \
		fi; \
	else \
		echo "docker compose"; \
	fi)

.PHONY: help setup install install-full install-fe run run-be run-be-prod run-fe run-db infra infra-down infra-logs infra-reset build build-fe dev clean smoke-rag docker-build docker-login docker-push docker-publish

# Default target
help:
	@echo "template-webchat - Available commands:"
	@echo "  make setup         - Initial setup (create db, install deps)"
	@echo "  make install      - Install backend dependencies (creates venv)"
	@echo "  make install-full - Install backend dependencies and note containerized RAG service"
	@echo "  make install-fe   - Install frontend dependencies"
	@echo "  make run          - Run both backend and frontend"
	@echo "  make run-be       - Run backend only"
	@echo "  make run-be-prod  - Run backend without auto-reload (production mode)"
	@echo "  make run-fe       - Run frontend only"
	@echo "  make run-db       - Run PostgreSQL database"
	@echo "  make infra        - Start all infrastructure (postgres, neo4j, qdrant)"
	@echo "  make infra-down   - Stop all infrastructure"
	@echo "  make infra-logs   - Tail logs from infrastructure containers"
	@echo "  make infra-reset  - Stop infra and delete volumes (fresh start)"
	@echo "  make build        - Build frontend"
	@echo "  make dev          - Run in development mode"
	@echo "  make clean        - Clean build artifacts"
	@echo "  make smoke-rag    - Start the RAG service and check its health"
	@echo "  make docker-push  - Push Docker image to GitHub Packages (requires CR_PAT env var)"
	@echo "  Runtime          - $(CONTAINER_RUNTIME) / $(COMPOSE_RUNTIME)"

# Initial setup
setup:
	@echo "Creating database..."
	@if [ -x "$(VENV)/bin/python" ]; then \
		$(VENV)/bin/python scripts/ensure_database.py; \
	else \
		python3 -m venv $(VENV) && $(VENV)/bin/pip install asyncpg && $(VENV)/bin/python scripts/ensure_database.py; \
	fi
	@echo "Database ready. Install dependencies with: make install && make install-fe"

# Create virtual environment if it doesn't exist
$(VENV):
	python3 -m venv $(VENV)

# Install dependencies (creates venv if needed)
install: $(VENV)
	@echo "Installing core backend dependencies..."
	$(VENV)/bin/pip install -r requirements.txt
	@echo "RAG-Anything runs in the separate Docker container. Use 'docker compose up' to start it."

# Install backend dependencies and surface the containerized RAG service note
install-full: $(VENV)
	@$(MAKE) install
	@echo "AnythingRAG is now containerized. Start the full stack with 'docker compose up'."

install-fe:
	cd frontend && npm install

# Run commands
run: run-be run-fe

run-be: $(VENV)
	PYTHONPATH=.::./backend $(VENV)/bin/uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# Production mode: no auto-reload. Prefer the systemd unit (scripts/webchat.service) on servers.
run-be-prod: $(VENV)
	PYTHONPATH=.::./backend $(VENV)/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000

run-fe:
	cd frontend && npm run dev

# Run database
run-db:
	$(COMPOSE_RUNTIME) up postgres

# Infrastructure (postgres + neo4j + qdrant)
infra:
	$(COMPOSE_RUNTIME) up -d postgres neo4j qdrant

infra-down:
	$(COMPOSE_RUNTIME) down

infra-logs:
	$(COMPOSE_RUNTIME) logs -f postgres neo4j qdrant

infra-reset:
	$(COMPOSE_RUNTIME) down -v
	@echo "Volumes deleted. Run 'make infra' to start fresh."

# Smoke test the isolated RAG service
smoke-rag:
	$(COMPOSE_RUNTIME) up -d rag-anything
	@echo "Waiting for RAG service health..."
	@for i in 1 2 3 4 5 6 7 8 9 10; do \
		if curl -fsS http://localhost:8010/health >/dev/null; then \
			curl -fsS http://localhost:8010/status; \
			echo ""; \
			exit 0; \
		fi; \
		sleep 2; \
	done; \
	echo "RAG service did not become healthy in time" >&2; \
	exit 1

# Build
build:
	cd frontend && npm run build

# Development (runs frontend which proxies to backend)
dev: run-fe

# Clean
clean:
	rm -rf frontend/dist
	rm -rf frontend/node_modules
	rm -rf $(VENV)
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# Docker configuration
# Required env vars for docker-push:
#   export CR_PAT=your_classic_pat_with_write_packages_scope
REGISTRY = ghcr.io
IMAGE_NAME = letsconfab/template-webchat
IMAGE_TAG = latest
IMAGE = $(REGISTRY)/$(IMAGE_NAME):$(IMAGE_TAG)

# Docker build
docker-build:
	$(CONTAINER_RUNTIME) build -t $(IMAGE) .

# Docker login (requires CR_PAT env var)
docker-login:
	@if [ -z "$$CR_PAT" ]; then \
		echo "Error: CR_PAT env var not set. Run: export CR_PAT=your_pat"; \
		exit 1; \
	fi
	@echo "$$CR_PAT" | $(CONTAINER_RUNTIME) login $(REGISTRY) -u letsconfab --password-stdin

# Docker push
docker-push:
	$(CONTAINER_RUNTIME) push $(IMAGE)

# Docker publish (login + build + push)
docker-publish: docker-login docker-build docker-push
	@echo "Image pushed to $(IMAGE)"
