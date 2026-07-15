# ── Stage 1: Python dependency builder ───────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install uv
RUN pip install --no-cache-dir uv==0.5.13

# Copy dependency spec
COPY apps/api/pyproject.toml apps/api/pyproject.toml

# Install dependencies into a virtual environment
RUN cd apps/api && uv sync --no-dev --no-editable

# ── Stage 2: Runtime image ────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

# curl for lightweight health check probe (no Python process startup overhead)
# libmagic1 / libpq5 for asyncpg and python-magic
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libmagic1 \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /build/apps/api/.venv /app/.venv

# Copy application source
COPY apps/api/src /app/src
COPY apps/api/migrations /app/migrations
COPY apps/api/alembic.ini /app/alembic.ini

# ── Runtime environment ────────────────────────────────────────────────────────
ENV PYTHONPATH=/app/src
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Configurable worker count — default 2; Railway overrides via env var.
# Rule of thumb for I/O-bound async apps: 2 × CPU cores.
ENV WORKERS=2

# Graceful shutdown window — uvicorn drains in-flight requests before SIGKILL.
ENV GRACEFUL_SHUTDOWN_TIMEOUT=30

# Non-root user for security
RUN useradd --create-home --shell /bin/bash appuser
USER appuser

EXPOSE 8000

# Health check — curl against the enhanced /healthz endpoint.
# start-period covers Alembic migration time on first deploy.
# Uses stdlib curl rather than spawning a Python process (faster, lower memory).
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl --silent --fail --max-time 5 http://localhost:8000/healthz || exit 1

# Default command — reads WORKERS and GRACEFUL_SHUTDOWN_TIMEOUT from env.
# Railway overrides CMD entirely for worker/migration containers.
CMD uvicorn corpmind.main:app \
      --host 0.0.0.0 \
      --port 8000 \
      --workers ${WORKERS} \
      --timeout-graceful-shutdown ${GRACEFUL_SHUTDOWN_TIMEOUT} \
      --access-log
