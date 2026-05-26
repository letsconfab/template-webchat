# Makefile for template-webchat demo branch

# Virtual environment path
VENV = .venv
PODMAN_LOCKFILE = $(HOME)/.config/containers/podman/machine/libkrun/podman-machine-default.lock

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

.PHONY: help setup install install-full install-fe run run-be run-fe run-db build build-fe dev clean smoke-rag restart-rag docker-build docker-login docker-push docker-publish ensure-container-runtime

# Default target
help:
	@echo "template-webchat - Available commands:"
	@echo "  make setup         - Initial setup (create db, install deps)"
	@echo "  make install      - Install backend dependencies (creates venv)"
	@echo "  make install-full - Install backend dependencies and note containerized RAG service"
	@echo "  make install-fe   - Install frontend dependencies"
	@echo "  make run          - Run both backend and frontend"
	@echo "  make run-be       - Run backend only"
	@echo "  make run-fe       - Run frontend only"
	@echo "  make run-db       - Run PostgreSQL database"
	@echo "  make build        - Build frontend"
	@echo "  make dev          - Run in development mode"
	@echo "  make clean        - Clean build artifacts"
	@echo "  make smoke-rag    - Start the RAG service and check its health"
	@echo "  make restart-rag  - Restart the RAG service"
	@echo "  make docker-push  - Push Docker image to GitHub Packages (requires CR_PAT env var)"
	@echo "  Runtime          - $(CONTAINER_RUNTIME) / $(COMPOSE_RUNTIME)"

# Initial setup
setup:
	@$(MAKE) ensure-container-runtime
	@echo "Starting database..."
	@$(COMPOSE_RUNTIME) up -d postgres
	@if [ ! -x "$(VENV)/bin/python" ]; then \
		python3 -m venv $(VENV) && $(VENV)/bin/pip install asyncpg; \
	fi
	@echo "Creating database..."
	@for i in 1 2 3 4 5 6 7 8 9 10 11 12; do \
		if $(VENV)/bin/python scripts/ensure_database.py; then \
			echo "Database ready. Install dependencies with: make install && make install-fe"; \
			exit 0; \
		fi; \
		sleep 2; \
	done; \
	echo "Database did not become ready in time" >&2; \
	exit 1

# Ensure the local container runtime is available before using compose/build/push
ensure-container-runtime:
	@if command -v podman >/dev/null 2>&1; then \
		if podman info >/dev/null 2>&1; then \
			exit 0; \
		fi; \
		echo "Podman is installed but the machine is not ready; initializing or starting it..."; \
		if podman machine init --now >/dev/null 2>&1; then \
			exit 0; \
		fi; \
		podman_start_output="$$(podman machine start 2>&1)" && exit 0 || true; \
		if printf '%s\n' "$$podman_start_output" | grep -Eq 'creating lockfile for VM|operation not permitted'; then \
			echo "Removing stale Podman lockfile and retrying..."; \
			rm -f "$(PODMAN_LOCKFILE)"; \
			if podman machine start >/dev/null 2>&1; then \
				exit 0; \
			fi; \
		fi; \
		if [ -n "$$podman_start_output" ]; then \
			printf '%s\n' "$$podman_start_output" >&2; \
		fi; \
		if podman machine start >/dev/null 2>&1; then \
			exit 0; \
		fi; \
		echo "Unable to start Podman automatically. Run: podman machine init --now" >&2; \
		exit 1; \
	elif command -v docker >/dev/null 2>&1; then \
		if docker info >/dev/null 2>&1; then \
			exit 0; \
		fi; \
		echo "Docker is installed but the daemon is not running. Start Docker and try again." >&2; \
		exit 1; \
	else \
		echo "Error: neither podman nor docker is installed." >&2; \
		exit 1; \
	fi

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

run-fe:
	cd frontend && npm run dev

# Run database
run-db: ensure-container-runtime
	$(COMPOSE_RUNTIME) up postgres

# Smoke test the isolated RAG service
smoke-rag: ensure-container-runtime
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

# Restart the RAG service
restart-rag: ensure-container-runtime
	$(COMPOSE_RUNTIME) restart rag-anything
	@echo "Waiting for RAG service to restart..."
	@for i in 1 2 3 4 5 6 7 8 9 10; do \
		if curl -fsS http://localhost:8010/health >/dev/null; then \
			echo "RAG service restarted successfully"; \
			curl -fsS http://localhost:8010/status | head -c 200; \
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
docker-build: ensure-container-runtime
	$(CONTAINER_RUNTIME) build -t $(IMAGE) .

# Docker login (requires CR_PAT env var)
docker-login: ensure-container-runtime
	@if [ -z "$$CR_PAT" ]; then \
		echo "Error: CR_PAT env var not set. Run: export CR_PAT=your_pat"; \
		exit 1; \
	fi
	@echo "$$CR_PAT" | $(CONTAINER_RUNTIME) login $(REGISTRY) -u letsconfab --password-stdin

# Docker push
docker-push: ensure-container-runtime
	$(CONTAINER_RUNTIME) push $(IMAGE)

# Docker publish (login + build + push)
docker-publish: docker-login docker-build docker-push
	@echo "Image pushed to $(IMAGE)"
