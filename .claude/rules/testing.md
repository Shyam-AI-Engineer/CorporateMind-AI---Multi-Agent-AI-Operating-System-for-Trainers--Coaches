# Testing Rules

## What to test, where
- **Unit** — every `service.py` function. Pure logic, mocked repos. Lives in `apps/api/tests/unit/`.
- **Repo** — repository against a real Postgres via `testcontainers`. `apps/api/tests/repo/`.
- **API** — endpoint-level via httpx AsyncClient + testcontainers (PG + Redis + Qdrant). `apps/api/tests/api/`.
- **Integration** — multi-step flows (upload → extract → discover → generate → send). `apps/api/tests/integration/`.
- **Frontend** — Vitest + Testing Library for components; Playwright for critical user journeys.

## AI / LLM testing
- **NEVER** assert exact LLM text. Test shape, schema, and properties.
- Use fixture-based assertions: schema validity, field presence, length bounds, forbidden-word denylist.
- For prompt regression: Promptfoo eval suite (see `prompt-engineering.md`). Must pass in CI on any prompt change.
- For agent flows: replay against frozen tool fixtures; assert state transitions and side effects.

## Tenant-isolation regression (REQUIRED)
Every PR that adds a new table OR new query path includes a test that:
1. Creates two tenants `A` and `B`.
2. Writes data into `A`.
3. As `B`, asserts the data is invisible to all read paths (API, repo, Qdrant search, Redis lookup).

See `.claude/skills/review-tenant-isolation/SKILL.md` for the runbook.

## Compliance regression
Every change to `ComplianceGuardAgent` or a channel adapter includes a test that:
1. A non-opted-in contact is blocked.
2. An over-frequency-cap send is blocked.
3. A WA send outside the 24h window without an approved template is blocked.

## CI gates
A PR cannot merge until ALL pass:
- `ruff check`
- `mypy --strict` on `apps/api/src/`
- `eslint` + `tsc --noEmit` on `apps/web/`
- `pytest -q` (unit + repo + api)
- `alembic upgrade head` against an ephemeral PG
- OpenAPI diff check (no accidental breaking changes)
- Promptfoo eval (if prompts touched)
- Tenant-isolation regression (if new table)

## Coverage
- Service layer: aim for 80%. Hard fail under 70%.
- Channel adapters: 90% — these are external-facing and the most failure-prone.
- LLM-call paths: schema-validity 100% on fixtures.

## Forbidden
- Mocking the database in integration tests — use testcontainers.
- `time.sleep()` in tests — use `freezegun` or controllable clocks.
- Tests that depend on production-like data — generate fixtures.
- Marking a task complete without running the relevant checks.
