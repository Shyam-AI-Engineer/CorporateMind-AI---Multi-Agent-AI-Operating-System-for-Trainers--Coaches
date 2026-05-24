---
name: create-api
description: Add a new REST endpoint to an existing module — handler, schemas, service method, route registration, tests, OpenAPI verification
---

# Create API Endpoint Skill

## Goal
Add a new endpoint that follows our thin-handler / fat-service / repository-only-DB-access pattern.

## Steps
1. **Ask for:** module name, HTTP method, path, request schema, response schema, auth requirements, expected behavior.
2. **Add the request/response models** to `modules/<name>/schemas.py` (Pydantic v2).
3. **Add the service method** to `modules/<name>/service.py` — pure business logic, accepts DTOs, returns DTOs, raises domain exceptions.
4. **Add the route handler** to `modules/<name>/api.py`:
   - ≤ 15 lines.
   - Inject service via `Depends`.
   - Inject `TenantContext` via `Depends`.
   - Accept `Idempotency-Key` header if mutating.
   - Map domain exceptions to HTTP via the central exception handler.
5. **Add tests:**
   - Unit test of the service method (mock repo).
   - API test of the endpoint (httpx + testcontainers).
   - Idempotency test (mutating endpoints only).
   - Tenant-isolation test (if endpoint reads tenant data).
6. **Verify OpenAPI:** run `pytest` + check that `/openapi.json` includes the new path with correct schemas. No accidental breaking changes.
7. **Update TypeScript types** by regenerating `packages/shared-types` (the CI does this automatically; verify locally for early feedback).

## Quality rules
- Handler ≤ 15 lines. No business logic.
- Pagination is cursor-based (`cursor`, `limit`; default 50, max 200). Offset pagination is forbidden by lint.
- Every mutating endpoint accepts `Idempotency-Key`.
- Rate-limit decorator (`@rate_limit("endpoint_class")`) on every public endpoint.
- Response shape is consistent with sibling endpoints (look at neighbors before deciding).
- Error responses use the central `{code, message, request_id}` envelope.

## References
- `.claude/rules/backend-python.md`
- `.claude/rules/security.md` (rate limits, auth, input validation)
- `.claude/rules/testing.md`
