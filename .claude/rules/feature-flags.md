# Feature Flags

Every risky or user-visible change ships behind a flag. Flags give us gradual rollout, instant kill-switch, and per-tenant gating without re-deploying.

## What's flagged (mandatory)
- All user-visible UI changes (new screens, redesigns).
- AI behavior changes — new prompt version, new model in routing matrix, new agent in graph.
- New channel adapter or webhook endpoint.
- New compliance rule that could block previously-passing sends.
- Pricing/billing changes.

## What's not flagged
- Bug fixes that restore previously-correct behavior.
- Pure refactors with no observable change.
- Internal logging / observability additions.

## Backend
- Flag service: project-internal in Stage 1 (Postgres-backed `feature_flags` table + Redis cache).
- Stage 2+ may adopt Unleash / GrowthBook if usage demands richer targeting.
- Lookup API:
  ```python
  from corpmind.core.flags import is_enabled
  if is_enabled("agent.outreach.v4", tenant=ctx.tenant_id):
      ...
  ```

## Flag naming
- Dotted, hierarchical: `<domain>.<feature>.<scope>` — e.g., `agent.outreach.v4`, `compliance.linkedin_strict`, `ui.dashboard.redesign_q3`.
- Always include the scope/version in the name so superseded flags are obvious.

## Required metadata per flag
Every flag record carries:
- `name`, `description`
- `owner` (Slack handle or email) — the human accountable for cleaning it up
- `created_at`, `expires_at`
- `default` (off / on / percentage / tenant-list)
- `kill_switch: bool` — set true for flags whose flip is an incident-response action

## Gradual rollout
Standard cadence for AI behavior changes:
- **Shadow** (0% return, 100% scored) — 24–72h
- **5% tenant cohort** — 48h
- **25%** — 72h
- **50%** — 72h
- **100%** — bake for one week before flag removal

Promotion at each step requires green dashboards (no SLO burn, no error-rate increase, no eval regression).

## Kill switches
Every new agent workflow and every new channel adapter ships with a kill-switch flag that disables the graph/adapter and falls back to a safe default (skip-with-log, manual queue, previous version).

## Tenant-gating
- Experimental prompts/models live behind allow-list flags before any rollout.
- Tenants can opt INTO a flag (beta program); tenants cannot be opted INTO a flag that affects billing or compliance without their consent.

## Hygiene
- Every flag has an `expires_at` no more than 90 days from creation.
- Quarterly flag cleanup: stale flags are removed; if the flag is still needed, write an ADR explaining why it's now permanent (it shouldn't be).
- A flag older than 6 months with no rollout movement is automatically surfaced for cleanup.

## Forbidden
- Long-lived flags as a substitute for proper configuration. Use config files or DB rows instead.
- Flags without an owner.
- Flags whose default-off state shipped to prod without a planned rollout.
