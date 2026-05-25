.PHONY: dev dev-api dev-web dev-worker lint lint-api lint-web test test-api test-web migrate infra-up infra-down clean

# ── Local dev (all services) ─────────────────────────────────────────────────
dev: infra-up
	@echo "Starting API, Celery worker, and web in parallel..."
	@$(MAKE) -j3 dev-api dev-worker dev-web

dev-api:
	cd apps/api && uv run uvicorn corpmind.main:app --reload --port 8000

dev-worker:
	cd apps/api && uv run celery -A corpmind.workers.celery_app worker \
		-l info -Q agents,outreach,social,ingestion,analytics,scrape

dev-web:
	cd apps/web && pnpm dev

# ── Data services (Docker Compose) ───────────────────────────────────────────
infra-up:
	docker compose -f infra/docker/compose.dev.yml up -d

infra-down:
	docker compose -f infra/docker/compose.dev.yml down

infra-logs:
	docker compose -f infra/docker/compose.dev.yml logs -f

# ── Linting ───────────────────────────────────────────────────────────────────
lint: lint-api lint-web

lint-api:
	cd apps/api && uv run ruff check src/ tests/
	cd apps/api && uv run mypy src/

lint-web:
	cd apps/web && pnpm lint
	cd apps/web && pnpm typecheck

# ── Tests ─────────────────────────────────────────────────────────────────────
test: test-api test-web

test-api:
	cd apps/api && uv run pytest -q

test-web:
	cd apps/web && pnpm test

# ── Migrations ────────────────────────────────────────────────────────────────
migrate:
	cd apps/api && uv run alembic upgrade head

migrate-down:
	cd apps/api && uv run alembic downgrade -1

migrate-new:
	@read -p "Migration name: " name; \
	cd apps/api && uv run alembic revision --autogenerate -m "$$name"

# ── Dependency management ─────────────────────────────────────────────────────
install:
	cd apps/api && uv sync
	cd apps/web && pnpm install
	cd packages/shared-types && pnpm install

# ── Cleanup ───────────────────────────────────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .next -exec rm -rf {} + 2>/dev/null || true
