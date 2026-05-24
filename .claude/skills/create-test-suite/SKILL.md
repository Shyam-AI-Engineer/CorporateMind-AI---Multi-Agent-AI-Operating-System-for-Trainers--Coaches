---
name: create-test-suite
description: Scaffold a test suite for a module or feature — unit, repo, API, integration, and tenant-isolation regression
---

# Create Test Suite Skill

## Goal
Add the test coverage required by `.claude/rules/testing.md` for a new module or feature. Tests are not a follow-up — they're part of the change.

## Steps
1. **Ask for:** module name, feature(s) being tested, critical user flows.
2. **Create test files:**
   ```
   apps/api/tests/
   ├── unit/test_<module>_<area>.py        # pure logic, mocked repos
   ├── repo/test_<module>_repo.py          # real PG via testcontainers
   ├── api/test_<module>_endpoints.py      # httpx + testcontainers
   ├── integration/test_<flow>.py          # multi-step (per critical flow)
   └── isolation/test_<module>_tenancy.py  # tenant-isolation regression
   ```
3. **Unit tests** — every public function in `service.py`:
   - Happy path.
   - At least one edge case (empty, boundary, timeout).
   - At least one error case (raises the expected domain exception).
4. **Repo tests** — every public function in `repo.py` against a real Postgres:
   - CRUD round-trip.
   - Tenant filter is applied (write as A, read as B → not found).
   - Soft-delete excludes from default queries.
5. **API tests** — every endpoint:
   - Auth required (401 without JWT).
   - RBAC enforced (403 for wrong role).
   - Validation (422 on bad input).
   - Idempotency (`Idempotency-Key` on mutating endpoints).
   - Rate-limit (429 above threshold).
   - Pagination (cursor-based, max page size respected).
6. **Integration tests** — at least one per critical user flow (e.g., upload → extract profile → discover HRs → generate outreach → send → reply ingested).
7. **Tenant-isolation test** (MANDATORY for any new table or query path):
   - Create tenants A and B.
   - Write into A.
   - As B, assert every read path returns nothing (API, repo, Qdrant, Redis).
8. **AI test fixtures** — for LLM-call paths:
   - Schema validity assertion (output matches `response_format`).
   - Forbidden-word denylist (no PII leakage, no competitor names, no profanity).
   - Property tests (length bounds, language match).
   - NEVER assert exact text.

## Quality rules
- Use `testcontainers` for PG, Redis, Qdrant. No mocked databases in repo/api/integration tests.
- Use `freezegun` for time-dependent logic. No `time.sleep()`.
- Fixtures over copy-paste — share via `conftest.py`.
- Coverage targets: services ≥ 80%, channel adapters ≥ 90%.
- One assertion concept per test name. Don't test five things in `test_user_creation`.

## References
- `.claude/rules/testing.md`
- `.claude/rules/multi-tenancy.md`
