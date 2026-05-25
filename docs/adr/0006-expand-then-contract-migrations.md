# ADR-0006: Expand-Then-Contract Migrations

- **Status:** Accepted
- **Date:** 2026-05-25
- **Deciders:** Shyam (Founder/CTO), AI Architect

## Context

CorporateMind AI runs on Railway with zero-downtime deployment targets. Database schema migrations are the highest-risk operation in the deployment pipeline — a bad migration can lock tables, cause data loss, or create a state incompatible with the running application version.

Specific risks we must prevent:
- **Table locks during deploys** — `ALTER TABLE ADD COLUMN NOT NULL` on a large table holds an exclusive lock, causing outage.
- **Rollback incompatibility** — if the new app version writes to a column that the old version doesn't know about, rolling back the app leaves the database in a state the old code can't read.
- **Lost data on contract** — dropping a column before all app code has been removed from referencing it.

We are also regulated (DPDP, GDPR) — any migration that risks data loss requires a documented backup path and a reversibility guarantee.

## Decision

**All database schema changes follow the 4-step Expand-Then-Contract pattern. No exceptions.**

The four steps must be shipped in separate releases:

1. **Expand** — Add the new column (nullable) / add new table / add index `CONCURRENTLY`. The old app version ignores the new column; the new app version is not yet deployed.

2. **Backfill** — Idempotent, batched job (Celery task) populates the new column for existing rows. Runs with `statement_timeout` and `lock_timeout` set. Safe to re-run.

3. **App Switch** — Deploy the new app version that reads and writes the new column. Old column still exists (backwards-compatible).

4. **Contract** — After the app switch has been stable for ≥ 1 sprint, ship a migration to drop the old column, add the `NOT NULL` constraint, or perform the destructive change. This release requires a documented backup path.

**Additional rules:**
- No migration file is ever edited after it has been applied to any environment (`ops/runbooks/emergency-hotfix.md` covers the exception path for critical data bugs).
- Long-running migrations run via one-off worker (not the API container); use `lock_timeout = '2s'`, `statement_timeout = '60s'`.
- Every migration has a corresponding Alembic `downgrade()` function.
- Destructive changes (drop column, drop table) ship only after a deprecation period and require IC + Tech Lead approval.

## Alternatives Considered

**1. Big-bang migration (single release, all steps)**
- `+` Fewer releases; simpler to reason about as a unit.
- `-` Locks the table during deploy, causing outage on any non-trivial table. If the new app version has a bug, rolling it back leaves the database incompatible with the old code. Rejected: incompatible with zero-downtime requirement.

**2. Lock-and-migrate (planned maintenance window)**
- `+` Simplest implementation; no multi-step sequencing.
- `-` Requires scheduled downtime, which violates our zero-downtime deployment goal. Unacceptable for a B2B SaaS product targeting autonomous 24/7 operation.

**3. Ghost (gh-ost) or pt-online-schema-change**
- `+` Allows large-table schema changes without locking.
- `-` Adds an external operational dependency (MySQL-origin tools with limited Postgres equivalents). `CREATE INDEX CONCURRENTLY` in Postgres already provides non-locking index creation, which covers our primary use case. Reconsidered if we encounter > 100M row tables.

## Consequences

**Positive:**
- Zero-downtime schema changes for all production deployments.
- Full rollback path: old app version always compatible with the database state.
- Backfill step is independently observable and restartable.
- Alembic `downgrade()` functions provide mechanical rollback for every step.

**Negative:**
- A schema change that would be a single file in a big-bang approach now requires 2–3 separate PRs and coordinated releases. Feature delivery for schema-heavy changes takes longer.
- Developers must understand the pattern and not collapse steps. The Alembic migration check in CI (`alembic upgrade head` against ephemeral PG) does not catch this — it requires PR review awareness.

**Neutral:**
- The `/create-migration` skill generates the correct Alembic template with expand/backfill/contract steps pre-scaffolded, reducing the cognitive load of following the pattern.

## References

- `.claude/rules/deployment-guardrails.md` — full migration and deployment rules
- `ops/runbooks/emergency-hotfix.md` — exception path for critical data bugs
- Supersedes: N/A
- Superseded by: N/A
