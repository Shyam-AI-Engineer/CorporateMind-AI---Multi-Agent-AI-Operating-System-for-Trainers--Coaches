# DEFECT: Inbox fan-out depends on an unprovisioned BYPASSRLS role

- **Status:** Open
- **Filed:** 2026-06-11 (during Sprint 8B readiness verification)
- **Severity:** SEV2 candidate (silent feature outage; no data corruption, no leak)
- **Component:** `apps/api/src/corpmind/workers/tasks/inbox.py` — `sync_all_active_connections` / `_run_fan_out`
- **Found by:** Sprint 8B blocker-3 verification (see ADR-0008 §8 amendment)

---

## Summary

The inbox sync fan-out task `sync_all_active_connections` runs a **cross-tenant query
with no RLS GUC set**:

```python
# tasks/inbox.py:_run_fan_out
select(InboxConnection.id, InboxConnection.tenant_id, InboxConnection.workspace_id)
    .where(InboxConnection.status == "active")
```

`inbox_connections` has `ENABLE` + **`FORCE ROW LEVEL SECURITY`** (per the inbox table
migrations and the model docstring). Under `FORCE`, the **table owner is also subject
to the policy** — there is no implicit owner bypass. With `app.tenant_id` unset, the
hardened policy predicate evaluates to NULL → fail-closed → **zero rows**.

The task's own docstring acknowledges the dependency:

```
Requires the DATABASE_URL role to have BYPASSRLS (or be a superuser) because
this task queries all tenants with no tenant_id filter. ...
ALTER ROLE corpmind_app BYPASSRLS;
```

Two problems with that:

1. **The role name is wrong.** The app role is `corpmind`
   ([infra/docker/init-db.sql:16-17](../../infra/docker/init-db.sql#L16-L17),
   [apps/api/.env:11](../../apps/api/.env#L11)). There is no `corpmind_app` role.
2. **It is not provisioned anywhere in-repo.** `init-db.sql` creates `corpmind` with
   `LOGIN PASSWORD` only — **no `SUPERUSER`, no `BYPASSRLS`**. There is no
   docker-compose, Terraform, or Railway manifest in the repo that grants it. Prod DB
   roles are configured out-of-band on Railway.

The test harness (`tests/conftest.py::_setup_test_role`) explicitly `SET ROLE`s to a
non-superuser `corpmind_test` to *enforce* RLS, with the comment "matching production
behaviour" — confirming prod is expected to run as a non-superuser with RLS enforced,
i.e. **the inbox fan-out would return zero rows in prod** unless someone manually ran a
`BYPASSRLS` grant that is recorded nowhere.

## Impact

- If the prod app role is a plain non-superuser (the documented expectation), the
  inbox fan-out **silently scans zero connections every interval** → no inbound Gmail
  replies are synced → the entire reply → classify → CRM automation loop never fires.
- The failure is **silent**: `inbox.fan_out.complete` logs `connections_scanned=0`
  with no error. No alert exists for "scanned 0 while active connections exist".
- In dev/CI this is masked because testcontainers connects as the postgres superuser
  (which bypasses RLS even under FORCE), so the fan-out "works" in tests and never in
  a correctly-locked-down environment.

## How to confirm in prod

1. Check the live app role's attributes: `\du` / `SELECT rolbypassrls, rolsuper FROM pg_roles WHERE rolname = current_user;`
2. Inspect recent `inbox.fan_out.complete` structured logs: is `connections_scanned`
   ≥ the number of `inbox_connections` rows with `status='active'`? If it's 0 while
   active connections exist, the defect is live.

## Recommended fix

Prefer **eliminating the BYPASSRLS dependency** over granting it (granting a bypass
attribute to the primary app role weakens the P0 tenant-isolation invariant — any
future query bug could then leak cross-tenant). Two options:

- **(A) Migrate the fan-out to an `orgs`-sweep** (the pattern Sprint 8B adopts for the
  follow-up cadence — see ADR-0008 §8). `orgs` is RLS-exempt; read active orgs with no
  GUC, then enqueue one RLS-scoped per-tenant sync subtask. Each subtask resolves its
  own connections under RLS. No bypass needed. **Recommended.**
- **(B) Provision a dedicated least-privilege `corpmind_jobs` role** with `BYPASSRLS`
  + `SELECT`-only on the sweep tables, used via a separate DSN only by fan-out tasks;
  codify it in `init-db.sql` and a prod runbook, and fix the docstring role name.

Either way: **add an alert** — "fan-out scanned 0 connections while ≥1 active
connection exists" — so a silent RLS misconfiguration cannot recur undetected.

## Scope note

This defect is **out of scope for Sprint 8B** (which only needs its *own* cadence
sweep to be correct, and achieves that via the `orgs`-fanout with no bypass). It is
filed so the inbox fan-out is not forgotten; recommend scheduling the fix (Option A for
consistency) plus the missing alert as a fast-follow.
