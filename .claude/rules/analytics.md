# Analytics Rules

## Where analytics lives
- Compute: `apps/api/src/corpmind/modules/analytics/`
- Rollups: `analytics_daily` table partitioned monthly.
- Live dashboards: backend serves pre-computed rows; frontend never recomputes.

## Aggregation policy
- **Never aggregate in a request handler.** All rollups are background jobs (Celery scheduled via beat).
- Use materialized views or pre-computed tables for any dashboard query expected to run > 100x/day.
- Time-range filters on every analytics endpoint; default 30 days, max 365.

## Metric definitions
- Definitions are version-controlled in `apps/api/src/corpmind/modules/analytics/metrics.py` with docstrings.
- Renaming a metric requires a deprecation window + dual-write period.
- Every metric has a unit (`count`, `rate`, `seconds`, `inr`) — never dimensionless.

## Per-tenant
- Every dashboard query is `tenant_id`-scoped (see `multi-tenancy.md`).
- No cross-tenant aggregation outside admin-only paths.

## Business metrics tracked (per tenant per day)
- Outreach sent / delivered / opened / replied (per channel)
- Reply rate by segment × channel × prompt version
- Compliance blocks (count + reasons)
- Meetings scheduled / completed
- Proposals drafted / sent
- AI token spend (sum + by agent + by model)
- Active workspaces, active campaigns
- Pipeline conversion: `discovered → engaged → meeting → booked`

## AI performance metrics (tracked but visible only to admins)
- Per-agent run count, success %, p95 latency
- Per-prompt eval scores
- Fallback rate, cache hit rate
- HITL override rate
- Hallucination rate (where verifiable)

## Anomaly detection
- `AnalyticsAgent` runs daily; flags anomalies (sudden drop in delivery, sudden spike in compliance blocks, model drift) and surfaces as insight cards.
- Threshold per metric configurable per tenant.

## Forbidden
- Writing analytics queries inline in route files.
- Storing PII in rollup tables — phone/email are pre-hashed before aggregation.
- "Live" cross-tenant leaderboards that could leak per-tenant performance.
