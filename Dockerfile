# syntax=docker/dockerfile:1

# ── Stage 1: Frontend Asset Builder ──────────────────────────────────────────
FROM node:20-alpine AS frontend-builder
WORKDIR /build

COPY package.json package-lock.json tailwind.config.js ./
COPY static ./static
COPY templates ./templates

RUN npm ci && npm run build:css

# ── Stage 2: Python Dependency Builder ───────────────────────────────────────
FROM python:3.12-slim AS python-builder
WORKDIR /install

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install/local -r requirements.txt

# ── Stage 3: Minimal Production Runtime ──────────────────────────────────────
FROM python:3.12-slim AS runtime

# Security: Install minimal runtime dependencies and create non-root user
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r abhihub && useradd -r -g abhihub -d /app -s /sbin/nologin abhihub

WORKDIR /app

# Copy Python packages from builder
COPY --from=python-builder /install/local /usr/local

# Copy application runtime files
COPY --chown=abhihub:abhihub app.py gunicorn.conf.py cache_manager.py push_api.py push_notifications.py scheduled_tasks.py firebase_config.py Procfile requirements.txt robots.txt ads.txt favicon.ico LICENSE ./
COPY --chown=abhihub:abhihub data/ ./data/
COPY --chown=abhihub:abhihub methods/ ./methods/
COPY --chown=abhihub:abhihub templates/ ./templates/
COPY --chown=abhihub:abhihub static/ ./static/
COPY --chown=abhihub:abhihub migrations/ ./migrations/

# Overwrite static CSS with compiled output from frontend-builder
COPY --from=frontend-builder --chown=abhihub:abhihub /build/static/css/tailwind.min.css ./static/css/tailwind.min.css

# Runtime environment settings
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=5000 \
    FLASK_ENV=production

USER abhihub

EXPOSE 5000

# Health check against unauthenticated /health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

CMD ["gunicorn", "-k", "geventwebsocket.gunicorn.workers.GeventWebSocketWorker", "-w", "1", "--config", "gunicorn.conf.py", "app:app"]
