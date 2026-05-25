# Runbook: Cross-Tenant Data Leak Suspected

## Incident Summary

A user or automated monitor has indicated that data belonging to one tenant may have been accessible by another tenant. This is a P0 security invariant violation and a potential DPDP/GDPR breach.

**CRITICAL: Do not attempt to minimize or dismiss this report. Treat every suspected cross-tenant leak as a confirmed incident until proven otherwise. The 72-hour breach notification clock may have already started.**

## Trigger Conditions

- Trainer reports seeing data that does not belong to their workspace.
- Security audit log shows a `cross_tenant_admin_only` call with an anomalous actor/target pair.
- Automated isolation test regression detected in CI.
- A `tenant_id` value appears in API responses that does not match the authenticated tenant's `org_id`.
- Sentry captures an exception with a foreign `tenant_id` in the context.
- Qdrant search returns results with a `tenant_id` payload that does not match the searcher.

## Severity Level

**SEV1** — always. Any confirmed or suspected cross-tenant data exposure is a P0 incident.

## Immediate Response Steps

**STOP. Do not attempt to fix the leak by writing code. Preserve evidence first.**

1. **Assign an Incident Commander (IC) immediately.** Open `#incident-<id>` channel.
2. **Preserve evidence:**
   - Do NOT delete or modify any database records.
   - Export the relevant request logs, API response payloads, and `audit_events` rows before any restarts.
   - Save the stack trace and Sentry event URL.
3. **Assess blast radius (must complete within 10 minutes):**
   - What data was exposed? (contact list? trainer profile? campaign messages? proposals?)
   - Which tenants are involved? (reporter and potentially leaked-to tenant)
   - How long has the leak been possible? (check git log for the date of the regression)
   - How many requests could have triggered the leak? (check API access logs)
4. **Contain the leak:**
   - If the leak is via a specific API endpoint: immediately disable that endpoint via feature flag or emergency hotfix.
   - If the leak is in a Qdrant search: add an emergency payload filter override and disable the affected search path.
   - If the leak is via a session issue: force-invalidate all active sessions for the affected tenants.
5. **Notify legal/DPO within 1 hour** — the 72-hour DPDP/GDPR breach notification clock starts at detection. See `breach-notification.md` for the DPO contact and notification template.
6. **Notify affected tenants** — via secure channel, IC must approve message before sending.

## Escalation Path

- **IC:** First responder — owns coordination.
- **Tech Lead:** Owns diagnosis and fix.
- **Legal / DPO:** Must be notified within 1 hour (see `ops/secrets.md` for contact).
- **Founder:** Notify for SEV1 always, regardless of time.

## Recovery Checklist

- [ ] Blast radius fully documented (tenants affected, data types, time window, request count).
- [ ] Leak path identified in code (missing `tenant_id` filter? RLS bypass? Qdrant missing predicate?).
- [ ] Fix deployed to production (see `emergency-hotfix.md`).
- [ ] Isolation regression test added that reproduces the exact leak condition.
- [ ] All affected tenants notified personally (not just via status page).
- [ ] Legal/DPO has assessed whether 72-hour DPDP/GDPR notification is required.
- [ ] `audit_events` reviewed for any cross-tenant accesses in the breach window.
- [ ] Session tokens invalidated for affected tenants if session compromise is possible.
- [ ] Status page updated only after tenants have been notified directly.

## Follow-up Actions

- [ ] Postmortem mandatory — blameless, completed within 5 business days.
- [ ] ADR or rule update to close the architectural gap that allowed the bypass.
- [ ] Full isolation regression test suite run against production (read-only) to confirm no other paths are affected.
- [ ] Consider third-party security audit if the breach involves PII of > 100 contacts.
