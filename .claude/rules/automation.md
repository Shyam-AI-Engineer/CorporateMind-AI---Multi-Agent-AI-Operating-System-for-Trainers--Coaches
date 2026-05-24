# Automation Rules

CorporateMind AI is fundamentally an autonomous system. Automation is correctness-critical — bugs in scheduled flows are silent and compounding.

## What runs autonomously
- **Daily**: AnalyticsAgent rollups, CompetitorIntel (when enabled), CampaignOptimizer proposals, churn-save segment refresh.
- **Continuous**: Reply ingestion, webhook handlers, follow-up cadence advancement.
- **On trigger**: Outreach generation (on segment lock), proposal drafting (on positive reply), social post scheduling.

## Scheduling
- Celery beat for cron-like schedules. Schedule defined in `apps/api/src/corpmind/workers/celery_beat_schedule.py` — version-controlled.
- Per-tenant timezone respected: a "9 AM" daily job uses the tenant's `Org.timezone`.
- No `time.sleep()` based "schedulers." No threading.Timer. Beat or nothing.

## Idempotency
Every scheduled job is idempotent. Re-running the same job on the same logical date yields the same outcome (no duplicate sends, no double-charges).

## HITL by default
The first week of a new tenant is **training-wheels mode**: every agent-proposed action requires explicit user approval, even if it would normally auto-execute. This:
- Prevents new-user surprise.
- Generates supervised data for the RLHF loop.
- Catches misconfigured profiles before they cause mass-sends.

After week 1, the tenant can opt INTO auto-execute for low-risk actions per category.

## Auto-execute eligibility
Actions auto-execute (without HITL) ONLY if ALL apply:
- Tenant is past training-wheels.
- Action is in the tenant's auto-execute allowlist.
- Recipient count ≤ 200.
- ComplianceGuard passes.
- Estimated cost ≤ tenant's auto-approve threshold.
- The agent's confidence score (where applicable) ≥ task-specific floor.

Anything else routes to the HITL approval queue.

## Quiet hours
- No outbound sends to recipients outside their local 8 AM – 9 PM unless flagged urgent and HITL-approved.
- No notifications to trainers outside their org timezone's 7 AM – 10 PM (configurable).

## Kill switch
Every autonomous workflow has a per-tenant kill switch (in UI) and a global kill switch (in admin/feature flags). Flipping either pauses immediately at the next checkpoint.

## Auditability
Every autonomous action writes to `audit_events`: who proposed it (which agent + run_id), what it did, when it executed, why (the rationale field shown in UI).

## Forbidden
- Background jobs that bypass `ComplianceGuard`.
- Jobs that mutate cross-tenant state.
- "Heartbeat" jobs running every < 30 seconds — review the design.
- Cron in `crontab` outside the orchestrator (use Celery beat).
