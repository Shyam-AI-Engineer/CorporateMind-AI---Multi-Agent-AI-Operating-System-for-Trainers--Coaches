# Backend Python Rules

Apply when editing files under `apps/api/`.

## Architecture
- Modular monolith. Modules live under `apps/api/src/corpmind/modules/<name>/`.
- Each module exposes: `api.py | service.py | repo.py | models.py | schemas.py | events.py`.
- Inter-module rule: NEVER import another module's `repo.py` or `models.py`. Cross-module talk via service interfaces (DI) or the in-process event bus.
- Async/await everywhere — this is an event-driven system.
- DI via FastAPI `Depends()` over global state.
- Functions focused, testable, under 30 lines.

## Code style
- Type hints on all function signatures and return types.
- Pydantic v2 DTOs over loose dicts. No `dict[str, Any]` crossing module boundaries.
- Docstrings on non-obvious service/repository functions.
- Descriptive repository method names (`find_hr_contacts_by_company_id`, not `get`).

## Patterns
- NO business logic in route handlers — handlers ≤ 15 lines, delegate to services.
- Repository pattern for all DB access; routes never touch SQLAlchemy directly.
- Adapter pattern for all third-party integrations (see `channel-adapter.md`).
- Raise domain-specific exceptions (`OptInRequiredError`, `BudgetExceededError`), not generic.
- Return structured error envelope: `{code, message, request_id}`.

## Async and performance
- Never use blocking I/O in async handlers.
- `asyncio.gather()` for concurrent independent operations.
- Offload heavy work (ingestion, embeddings, send pipelines) to Celery (see `queue-celery.md`).
- Use Redis for caching hot paths (tenant context, semantic cache).

## Logging
- Structured JSON via structlog. Always include `request_id`, `tenant_id`, `run_id`.
- Log service-level decisions, not raw payloads.
- Never log PII, tokens, or credentials.

## Forbidden
- Direct LLM-provider SDK imports (`openai`, `anthropic`, etc.) — use `corpmind.ai.euri_client.EuriClient` (mechanically enforced by `.claude/scripts/block-direct-llm-imports.sh`).
- Editing applied Alembic migrations — write a new migration instead.
- Global mutable state.
