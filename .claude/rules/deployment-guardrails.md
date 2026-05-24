# Deployment Guardrails

## Branching
- Trunk-based. `main` is always deployable.
- PRs are short-lived. Squash-merge.
- Feature branches → preview env per PR.

## CI gates (must all pass before merge)
- `ruff check` + `mypy --strict` on `apps/api/src/`
- `eslint` + `tsc --noEmit` on `apps/web/`
- `pytest -q` (unit + repo + api)
- `alembic upgrade head` against an ephemeral Postgres
- OpenAPI diff check (additive-only within a major version)
- Container build (multi-stage, distroless final)
- Promptfoo eval (if prompts touched)
- Tenant-isolation regression (if new table added)

## Environments
`dev` (local Docker Compose) → `preview` (per-PR Vercel + Railway) → `staging` (mirrors prod, daily snapshot restore) → `prod`.

No direct prod deploys. Staging soak ≥ 1 hour for risky changes (new agent, new channel, schema change).

## Migrations: expand-then-contract
Never combine the expand and contract steps. Sequence:
1. **Expand** — additive migration (add column nullable, add table, add index `CONCURRENTLY`).
2. **Backfill** — idempotent batched job.
3. **App switch** — release that reads + writes new column.
4. **Contract** — release later, drop old column / set NOT NULL.

Every migration is reversible. Destructive changes (drop column, drop table) ship a release AFTER deprecation.

Long-running migrations gated by a maintenance flag and executed via a one-off worker, not the API container; use `lock_timeout` and `statement_timeout`.

## Progressive rollout
- Prod deploys are blue/green or canary (10% → 50% → 100%).
- New agent graphs / channel adapters: behind a feature flag, 5% → 25% → 100% by tenant cohort (see `feature-flags.md`).
- **Auto-rollback** if SLO burn (error rate, p95 latency, LLM fallback rate) crosses threshold within first 15 minutes.

## Change windows
- **No prod deploys** Fridays after 14:00 IST, weekends, or during a known customer-critical campaign (campaign-aware deploy gate reads upcoming `campaigns.scheduled_at`).
- Emergency hotfix path is documented (`ops/runbooks/emergency-hotfix.md`) and has IC + Tech Lead approval.

## Secrets
- Never logged.
- Never echoed in CI.
- Secret-scanning runs on every PR (`gitleaks`).
- Rotation is scheduled, not reactive.

## External providers
Every new integration ships with:
- A kill-switch feature flag.
- A documented rollback plan (revert env var, flip flag, redeploy).
- A runbook for the provider's known failure modes.

## Pre-deploy checklist (PR template)
- [ ] Migrations included? Reversible? Expand-then-contract?
- [ ] Behind a feature flag? Owner + expiry set?
- [ ] Rollback plan documented?
- [ ] Langfuse / Grafana dashboard for the change?
- [ ] Alert thresholds reviewed and not silenced?
- [ ] Tenant-isolation test added (if new table)?
- [ ] Prompt eval suite green (if prompts touched)?
- [ ] No new direct LLM-provider SDK imports?
- [ ] ADR written / referenced (if architectural)?
