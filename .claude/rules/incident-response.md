# Incident Response

## Severity ladder
- **SEV1** — Data loss, cross-tenant data leak, total platform outage, mass-send to wrong audience, security breach with PII exposure.
- **SEV2** — Major feature down (e.g., WhatsApp send broken), billing broken, mass-send delivery failure, agent runs failing for > 25% of tenants.
- **SEV3** — Degraded UX, slow agent runs, single-tenant outage, dashboard data stale.
- **SEV4** — Cosmetic, single non-critical workflow failure.

## On-call response
- **SEV1 / SEV2** automatically:
  - Page on-call (PagerDuty / Better Stack).
  - Open `#incident-<short-id>` channel.
  - Assign an **Incident Commander** (IC) — first responder by default; can hand off.
  - Update the public status page within 15 minutes.
- Updates: every **30 min** for SEV1, every **hour** for SEV2, until resolved.

## First-10-minutes priorities
1. **Stop the bleeding** before RCA:
   - Flip kill-switch flag for the affected feature.
   - Pause the relevant Celery queue.
   - Rotate compromised credentials if applicable.
   - Engage circuit breakers manually if needed.
2. **Blast-radius check**: is this isolated to one tenant or platform-wide? Answer in the first 10 minutes.
3. **Customer comms**: SEV1 always; SEV2 if customer-visible.

## Runbooks
Live under `ops/runbooks/`. One markdown file per common failure mode:
- `euri-provider-down.md`
- `whatsapp-template-rejection-storm.md`
- `celery-queue-backlog.md`
- `postgres-connection-exhaustion.md`
- `compliance-guard-mass-block.md`
- `outreach-mass-bounce.md`
- `cross-tenant-data-suspected.md`

Each runbook: triggers, immediate-action checklist, diagnostic commands, escalation path, rollback steps.

## Comms
- Single source of truth = the incident channel.
- Status page updates point at the channel.
- Customer email/WA only after IC approval to avoid contradictory messaging.

## DPDP / GDPR breach clock
If the incident involves customer PII or cross-tenant exposure:
- **72-hour notification clock** starts at detection.
- Legal owner notified within 1h (named contact in `ops/runbooks/breach-notification.md`).
- DPO email template prepared; sent only after IC + Legal sign-off.
- Audit log entry created with detection time, scope, affected tenants, remediation.

## Post-incident
- Blameless **postmortem** within 5 business days. IC writes; reviewed by team.
- Outcomes → action items in the issue tracker, each with **owner + due date**.
- If the root cause is architectural → write an ADR.
- If the root cause is observability (we didn't see it soon enough) → add the missing metric/alert.

## Roles
- **IC (Incident Commander)** — owns coordination, decision-making, comms cadence.
- **Tech Lead** — owns diagnosis + fix execution.
- **Comms Lead** — owns customer + internal stakeholder updates.
- **Scribe** — keeps the incident channel timeline clean for the postmortem.

For SEV3/SEV4, one person can wear multiple hats.
