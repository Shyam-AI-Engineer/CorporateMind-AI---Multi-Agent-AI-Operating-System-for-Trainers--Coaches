---
name: create-module
description: Scaffold a new business module under apps/api/src/corpmind/modules/ following the Ports & Adapters pattern (api/service/repo/models/schemas/events)
---

# Create Module Skill

## Goal
Scaffold a new modular-monolith module that conforms to the project's strict module boundaries (see `.claude/rules/backend-python.md` and `.claude/rules/multi-tenancy.md`).

## Steps
1. **Ask for:** module name (snake_case), one-line domain description, primary entities, primary endpoints (verbs + resources).
2. **Create the directory tree:**
   ```
   apps/api/src/corpmind/modules/<name>/
   ├── __init__.py
   ├── api.py          # FastAPI router; handlers ≤ 15 lines
   ├── service.py      # business logic; depends on repo via DI
   ├── repo.py         # SQLAlchemy async; only file that touches DB
   ├── models.py       # ORM entities; tenant_id NOT NULL on every table
   ├── schemas.py      # Pydantic v2 DTOs
   ├── events.py       # domain events published to the bus
   └── exceptions.py   # module-specific exceptions
   ```
3. **Add tests skeleton:**
   ```
   apps/api/tests/{unit,repo,api}/test_<name>_*.py
   ```
4. **Wire the router** into `apps/api/src/corpmind/main.py` under `/api/v1/<name>`.
5. **Generate an Alembic migration** for any new tables (use the `create-migration` skill).
6. **Add tenant-isolation regression test** (mandatory — use `review-tenant-isolation` skill).
7. **Summarize**: what was scaffolded, what still needs business logic, what tests pass / pending.

## Quality rules
- Single responsibility — one module, one domain.
- Handlers ≤ 15 lines; logic lives in `service.py`.
- Repo is the only file that touches the DB.
- All inputs/outputs are Pydantic v2 DTOs. No raw dicts cross boundaries.
- Every table has `tenant_id UUID NOT NULL` + composite index.
- Every table has UUID v7 primary key, `created_at`, `updated_at`, soft `deleted_at` for customer-facing entities.
- Structured JSON logging with `request_id`, `tenant_id`.
- No imports from other modules' `repo.py` or `models.py` — talk via service interface or event bus.
- No direct LLM-provider SDK imports (enforced by `block-direct-llm-imports.sh`).

## References
- `.claude/rules/backend-python.md`
- `.claude/rules/multi-tenancy.md`
- `.claude/rules/testing.md`
