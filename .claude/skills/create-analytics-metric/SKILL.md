---
name: create-analytics-metric
description: Add a new business or AI metric — definition, daily rollup job, dashboard panel, alert
---

# Create Analytics Metric Skill

## Goal
Add a new metric tracked per tenant per day. Metrics must be defined once, computed once, and consumed many times — never recomputed inline in request handlers.

## Steps
1. **Ask for:**
   - Metric name (snake_case) and one-sentence description.
   - Unit (`count` / `rate` / `seconds` / `inr`).
   - Grouping dimensions (per channel, per agent, per segment, ...).
   - Computation source (which table(s) / event stream).
   - Refresh cadence (real-time / hourly / daily).
2. **Add the metric definition** in `apps/api/src/corpmind/modules/analytics/metrics.py`:
   ```python
   @metric(unit="count", description="...")
   def outreach_replies_total(tenant_id: UUID, date: date) -> int:
       ...
   ```
3. **Add to `analytics_daily` rollup:**
   - Extend the daily rollup Celery task (`apps/api/src/corpmind/workers/analytics_tasks.py`) to compute and upsert the new metric.
   - Rollup is idempotent — re-running the same day's job overwrites with the same result.
4. **Expose via API:** add the metric to the existing `/api/v1/analytics/metrics` endpoint (no new endpoint per metric — they share a parameterized handler).
5. **Add Prometheus metric** (if live-updated, not just daily rollup):
   ```python
   from prometheus_client import Counter
   OUTREACH_REPLIES = Counter("outreach_replies_total", "...", ["channel", "tenant"])
   ```
6. **Add Grafana panel** in the appropriate dashboard JSON (`infra/grafana/dashboards/<area>.json`). Filter by `tenant_label`.
7. **Add alert (if appropriate)** in Prometheus alertmanager config — only for metrics that warrant paging (see `.claude/rules/observability.md` SLO list).
8. **Tests:**
   - Unit: metric function returns expected value for fixture data.
   - Idempotent rollup: running the daily task twice on the same date produces the same row.
   - API: endpoint returns the metric for a tenant, scoped correctly.

## Quality rules
- Metric defined ONCE; never recomputed in request handlers.
- Time-range filterable on every endpoint exposing the metric (default 30d, max 365d).
- Every metric has a unit. Never dimensionless.
- Renaming a metric requires a deprecation period + dual-write. Document in the PR.
- NO PII in rolled-up rows — phone/email pre-hashed.
- Tenant-scoped at the query layer; no cross-tenant aggregation outside admin paths.

## References
- `.claude/rules/analytics.md`
- `.claude/rules/observability.md`
- `.claude/rules/multi-tenancy.md`
