# Multi-Tenancy Rules (NON-NEGOTIABLE)

Tenant isolation is a P0 security invariant. Cross-tenant data leakage is the worst class of bug we can ship.

## Schema
- Every business table has `tenant_id UUID NOT NULL`.
- Composite index `(tenant_id, ...)` on every event-style and hot-path table.
- Postgres Row-Level Security (RLS) policies enabled on every base table as defense-in-depth:
  ```sql
  USING (tenant_id = current_setting('app.tenant_id')::uuid)
  ```
- Tenant ID set per connection via `SET LOCAL app.tenant_id = ...` by a FastAPI dependency at request start.
- Enterprise tier may use `schema-per-org` with logical replication; the app-level filter still applies.

## Application layer
- `corpmind.core.tenancy.TenantContext` is a `contextvars.ContextVar`. Middleware sets it from the JWT; every query and tool call reads it.
- Service and repository code MUST NOT accept `tenant_id` as a parameter — it comes from `TenantContext`. This prevents accidental "trust the caller" bugs.
- The repository base class injects the tenant filter automatically; opt-out requires an explicit `@cross_tenant_admin_only` decorator that audit-logs every call.

## Other planes
- **Redis**: keys prefixed `t:{org_id}:{workspace_id}:...`. Per-tenant memory budget enforced.
- **Qdrant**: every search includes a `tenant_id` payload predicate. Collections are per-org for trainer/HR data.
- **Celery**: tasks carry `tenant_id` in headers; per-tenant queue concurrency cap prevents noisy-neighbor.
- **Object storage**: paths under `tenants/{org_id}/workspaces/{ws_id}/...` with per-tenant signed URLs.
- **Langfuse**: traces tagged with `tenant_id`; dashboards filtered.

## Testing requirement
- Every PR that adds a new table OR a new query path MUST include a tenant-isolation regression test: create two tenants, write data into one, assert the other cannot read it.
- See `.claude/skills/review-tenant-isolation/SKILL.md`.

## Audit
- Every cross-tenant admin action (rare, e.g. support staff impersonation) is append-only logged to `audit_events` with actor, target tenant, and reason.
