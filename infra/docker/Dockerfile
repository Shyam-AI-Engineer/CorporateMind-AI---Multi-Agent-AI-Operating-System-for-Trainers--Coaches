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

# System deps for asyncpg, Pillow, python-magic
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /build/apps/api/.venv /app/.venv

# Copy application source
COPY apps/api/src /app/src
COPY apps/api/migrations /app/migrations
COPY apps/api/alembic.ini /app/alembic.ini

# Set environment
ENV PYTHONPATH=/app/src
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Non-root user for security
RUN useradd --create-home --shell /bin/bash appuser
USER appuser

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import httpx; httpx.get('http://localhost:8000/healthz').raise_for_status()"

# Default command — Railway overrides this per service
CMD ["uvicorn", "corpmind.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
