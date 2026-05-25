# ADR-0003: Postgres RLS as Tenant Isolation Default

- **Status:** Accepted
- **Date:** 2026-05-25
- **Deciders:** Shyam (Founder/CTO), AI Architect

## Context

CorporateMind AI is a multi-tenant SaaS platform. Every business table contains data that belongs to exactly one tenant (organization). Cross-tenant data leakage is a P0 security invariant — a bug that exposes one trainer's prospect list to another trainer is a critical incident, not a minor defect.

We need a tenant isolation strategy that:
- Prevents leakage even if application-layer `tenant_id` filters are accidentally omitted.
- Is operationally simple for Stage 1 (no per-tenant database spin-up overhead).
- Has a credible upgrade path for Enterprise tenants who require dedicated storage.
- Is auditable and testable (every PR that adds a table must include a tenant-isolation regression test).

## Decision

**Row-Level Security (RLS) on every base table in the primary Postgres database, with `TenantContext` propagated as a connection-level variable.**

Implementation:
- Every business table has `tenant_id UUID NOT NULL` with a composite index `(tenant_id, ...)`.
- RLS policy on every table: `USING (tenant_id = current_setting('app.tenant_id')::uuid)`.
- FastAPI middleware sets `SET LOCAL app.tenant_id = {tenant_id}` at request start, read from the validated JWT.
- `corpmind.core.tenancy.TenantContext` is a `contextvars.ContextVar`. Middleware sets it; all downstream code reads it — never accepts `tenant_id` as a parameter (prevents "trust the caller" bugs).
- Repository base class injects the tenant filter automatically on every query.
- Cross-tenant admin access requires explicit `@cross_tenant_admin_only` decorator that audit-logs every call.

**Enterprise tier upgrade path:** Schema-per-org via Postgres schemas + logical replication. The application-layer filter still applies as defense-in-depth. This upgrade does not require an app code change — only a migration and routing configuration change.

## Alternatives Considered

**1. Schema-per-org (Postgres schemas) from day 1**
- `+` Complete schema-level isolation; no `tenant_id` column needed on every table; easier to migrate a single tenant.
- `-` Schema provisioning per new tenant adds latency and operational complexity. Alembic migrations must run per schema. At Stage 1 volumes (< 500 tenants), the overhead is unjustified. This is the Enterprise upgrade path, not the default.

**2. Database-per-tenant**
- `+` Maximum isolation; tenant egress is trivially complete.
- `-` One Postgres instance per tenant is unviable at Stage 1 economics. Connection pooling becomes a separate infrastructure problem. Operational complexity is Stage 3 territory.

**3. Application-layer filters only (no RLS)**
- `+` No Postgres-specific features; portable to other databases.
- `-` A single missing `WHERE tenant_id = ?` clause causes a cross-tenant leak. This has happened at multiple SaaS companies. Defense-in-depth at the database layer is a non-negotiable requirement for a compliance-forward product (DPDP, GDPR).

## Consequences

**Positive:**
- Even if a developer forgets a `tenant_id` filter in a new query, the RLS policy blocks the leak at the database level.
- Audit logs for cross-tenant admin access are structurally enforced by the `@cross_tenant_admin_only` decorator.
- Standard Postgres — no additional infrastructure component.
- Enterprise isolation upgrade is additive (schema-per-org on top of RLS), not a replacement.

**Negative:**
- Requires `SET LOCAL app.tenant_id` at the start of every request. Missed in async or background contexts can cause RLS to use a stale or null tenant_id. Mitigated by the Celery task envelope which propagates `tenant_id` in task headers.
- RLS adds a minor performance overhead per query. Acceptable at Stage 1 volumes; profiled before Stage 2 if necessary.
- Testing requires explicitly setting the tenant context variable; `testcontainers` tests must simulate this.

**Neutral:**
- Redis keys, Qdrant collections, Celery task headers, and object storage paths all use their own tenant namespace conventions (documented in `.claude/rules/multi-tenancy.md`) — RLS does not cover these planes.

## References

- `.claude/rules/multi-tenancy.md` — full tenancy rules and enforcement patterns
- `.claude/skills/review-tenant-isolation/SKILL.md` — isolation test runbook
- `docs/architecture.md` §6 (data stores)
- Supersedes: N/A
- Superseded by: N/A (if we move to schema-per-org for all tenants, write ADR-XXXX to supersede this)
