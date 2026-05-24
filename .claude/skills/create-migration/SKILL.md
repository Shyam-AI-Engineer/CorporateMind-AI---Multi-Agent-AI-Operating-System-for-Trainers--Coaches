---
name: create-migration
description: Generate an Alembic migration following the expand-then-contract discipline for safe production rollout
---

# Create Migration Skill

## Goal
Add a database schema change safely. Migrations in CorporateMind AI are NEVER all-or-nothing — they follow expand-then-contract so app and DB can deploy independently.

## Steps
1. **Ask for:** what the change does, the table(s) involved, whether it's additive or destructive.
2. **Classify the change:**
   - **Additive** (new column nullable, new table, new index): single migration.
   - **Destructive** (drop column, drop table, NOT NULL on existing column, rename): MUST be split into expand-then-contract over multiple releases.
3. **For additive changes:**
   - `cd apps/api && alembic revision -m "<short description>"`
   - Implement `upgrade()` and `downgrade()`.
   - Indexes added with `CREATE INDEX CONCURRENTLY` to avoid locking.
   - For new tables: include `tenant_id UUID NOT NULL`, `created_at`, `updated_at`, soft `deleted_at` (where applicable), composite index `(tenant_id, created_at DESC)`.
   - Enable RLS policy on the new table.
4. **For destructive changes — plan the sequence:**
   - **Step 1 (this release):** Additive migration (e.g., add new column nullable).
   - **Step 2 (this release):** Backfill job — idempotent, batched, written as a separate Alembic data-only migration OR a Celery task.
   - **Step 3 (next release):** App reads + writes new column.
   - **Step 4 (later release):** Cleanup migration (e.g., NOT NULL, drop old column).
   - Document the sequence in the migration's docstring AND in the corresponding ADR if architectural.
5. **Test the migration:**
   - `alembic upgrade head` against an ephemeral PG.
   - `alembic downgrade -1` then `upgrade head` again — must be idempotent.
6. **Add a tenant-isolation test** if the change adds a new table (see `review-tenant-isolation` skill).
7. **Verify CI** — the `alembic upgrade check` job must pass on the PR.

## Quality rules
- ONE migration per PR.
- NEVER edit an applied migration. Write a new one.
- NEVER deploy a destructive contract step (drop column / table) in the same release that introduces it.
- Index creation: `CREATE INDEX CONCURRENTLY` for tables > 100k rows.
- Long-running migrations (> 30s expected) gated by a maintenance flag and run via a one-off worker, not the API container; use `lock_timeout` and `statement_timeout`.
- `downgrade()` must work (or be explicitly marked as one-way with a comment explaining why).
- Migration docstring documents the why, not just the what.

## Forbidden
- Migrations without `downgrade()` (one-way migrations require explicit justification in docstring).
- Bare `CREATE INDEX` without `CONCURRENTLY` on large tables.
- Combining expand and contract in one release.

## References
- `.claude/rules/deployment-guardrails.md`
- `.claude/rules/multi-tenancy.md`
