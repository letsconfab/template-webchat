# Makefile for template-webchat demo branch

# Virtual environment path
VENV = .venv

# Python path
PYTHONPATH = $(CURDIR)

.PHONY: help setup install install-fe run run-be run-fe run-db build build-fe dev clean docker-build docker-login docker-push docker-publish

# Default target
help:
	@echo "template-webchat - Available commands:"
	@echo "  make setup         - Initial setup (create db, install deps)"
	@echo "  make install      - Install backend dependencies (creates venv)"
	@echo "  make install-fe   - Install frontend dependencies"
	@echo "  make run          - Run both backend and frontend"
	@echo "  make run-be       - Run backend only"
	@echo "  make run-fe       - Run frontend only"
	@echo "  make run-db       - Run PostgreSQL database"
	@echo "  make build        - Build frontend"
	@echo "  make dev          - Run in development mode"
	@echo "  make clean        - Clean build artifacts"
	@echo "  make docker-push  - Push Docker image to GitHub Packages (requires CR_PAT env var)"

# Initial setup
setup:
	@echo "Creating database..."
	-createdb webchat_db 2>/dev/null || true
	@echo "Database ready. Install dependencies with: make install && make install-fe"

# Create virtual environment if it doesn't exist
$(VENV):
	python3 -m venv $(VENV)

# Install dependencies (creates venv if needed)
install: $(VENV)
	$(VENV)/bin/pip install -r requirements.txt

install-fe:
	cd frontend && npm install

# Run commands
run: run-be run-fe

run-be: $(VENV)
	PYTHONPATH=.::./backend $(VENV)/bin/uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

run-fe:
	cd frontend && npm run dev

# Run database
run-db:
	docker compose up postgres

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
	docker build -t $(IMAGE) .

# Docker login (requires CR_PAT env var)
docker-login:
	@if [ -z "$$CR_PAT" ]; then \
		echo "Error: CR_PAT env var not set. Run: export CR_PAT=your_pat"; \
		exit 1; \
	fi
	@echo "$$CR_PAT" | docker login $(REGISTRY) -u letsconfab --password-stdin

# Docker push
docker-push:
	docker push $(IMAGE)

# Docker publish (login + build + push)
docker-publish: docker-login docker-build docker-push
	@echo "Image pushed to $(IMAGE)"