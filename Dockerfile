# Multi-stage build for production deployment

# Stage 1: Build React frontend
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

# Copy frontend package files
COPY frontend/package*.json ./

# Install dependencies
RUN npm ci

# Copy frontend source
COPY frontend/ ./

# Build frontend
RUN npm run build

# Stage 2: Build Python backend
FROM python:3.11-slim AS backend-builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 3: Final image
FROM python:3.11-slim

WORKDIR /app

# Copy virtual environment from builder
COPY --from=backend-builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install runtime dependencies for document processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    poppler-utils \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r appgroup && useradd -r -g appgroup appuser

# Copy backend code
COPY --chown=appuser:appgroup backend/ ./backend/
COPY --chown=appuser:appgroup requirements.txt .

# Pre-download FastEmbed model (as root to have write permissions)
RUN python -c "from langchain_community.embeddings import FastEmbedEmbeddings; import os; os.makedirs('/app/.cache', exist_ok=True); os.environ['HF_HOME']='/app/.cache'; FastEmbedEmbeddings(cache_dir='/app/.cache').embed_query('test')" && \
    chown -R appuser:appgroup /app/.cache

# Copy frontend build from frontend-builder
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

# Switch to non-root user
USER appuser

# Expose ports
EXPOSE 8005

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8005/health || exit 1

# Run the application
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8005"]
