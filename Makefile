# Makefile for template-webchat demo branch

.PHONY: help setup install install-fe run run-be run-fe build build-fe dev clean

# Default target
help:
	@echo "template-webchat - Available commands:"
	@echo "  make setup       - Initial setup (create db, install deps)"
	@echo "  make install   - Install backend dependencies"
	@echo "  make install-fe - Install frontend dependencies"
	@echo "  make run       - Run both backend and frontend"
	@echo "  make run-be    - Run backend only"
	@echo "  make run-fe    - Run frontend only"
	@echo "  make build     - Build frontend"
	@echo "  make dev      - Run in development mode"
	@echo "  make clean    - Clean build artifacts"

# Initial setup
setup:
	@echo "Creating database..."
	-createdb webchat_db 2>/dev/null || true
	@echo "Database ready. Install dependencies with: make install && make install-fe"

# Install dependencies
install:
	pip install -r requirements.txt

install-fe:
	cd frontend && npm install

# Run commands
run: run-be run-fe

run-be:
	python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

run-fe:
	cd frontend && npm run dev

# Build
build:
	cd frontend && npm run build

# Development (runs frontend which proxies to backend)
dev: run-fe

# Clean
clean:
	rm -rf frontend/dist
	rm -rf frontend/node_modules
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true