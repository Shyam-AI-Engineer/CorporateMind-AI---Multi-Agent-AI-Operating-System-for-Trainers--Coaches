# Runbook: Compliance Guard Mass Block

## Incident Summary

The ComplianceGuardAgent is blocking a large volume of outbound messages unexpectedly, causing campaign sends to fail or stall. This may be a legitimate compliance enforcement (the messages were genuinely non-compliant) or a false-positive triggered by a rule misconfiguration or content classifier regression.

## Trigger Conditions

- Prometheus alert: `compliance_blocks_total{reason="*"} > 50` in a 10-minute window.
- Grafana Channels dashboard shows compliance block rate > 5% for any channel.
- Multiple tenants reporting that campaigns are not sending.
- Admin panel Compliance Investigator shows a spike in blocked sends.
- Trainer opens a support ticket: "none of my emails are going out."

## Severity Level

- **SEV3** — isolated to one tenant, low block count. Normal enforcement or misconfigured contact list.
- **SEV2** — multiple tenants affected, high block rate, campaign revenue at risk.
- **SEV1** — a new compliance rule or classifier update is blocking all sends platform-wide.

## Immediate Response Steps

1. **Identify the block reason:**
   - Admin panel → Compliance Investigator → filter by last 30 minutes.
   - Most common block reasons: `opt_in_missing`, `frequency_cap_exceeded`, `duplicate_content`, `content_classifier_flag`, `wa_window_expired`.
2. **Legitimate enforcement (opt-in missing or frequency cap):**
   - This is correct behavior. The trainer needs to review their contact list or wait for the frequency window to reset.
   - Do NOT override — audit logs must be clean.
   - Notify the trainer with the specific reason via the support channel.
3. **Content classifier false positive:**
   - Pull a sample of blocked messages from `audit_events`.
   - Review the content classifier output in Langfuse (search by `agent=compliance_guard_agent`).
   - If a false positive is confirmed: document the sample, manually review the message, and if safe, add a `manager_override` record with justification.
   - **Do NOT disable the classifier** — add a targeted exception.
4. **Rule misconfiguration (SEV2/SEV1):**
   - Check if a new compliance rule was deployed in the last release.
   - If a new rule is the root cause: flip the feature flag for that rule to `false` immediately.
   - Notify tenants of the incident via status page.
5. **If all sends are blocked (SEV1):** Check whether ComplianceGuardAgent itself has a bug causing all sends to throw an exception. Check Sentry for `ComplianceGuardAgent` errors.

## Escalation Path

- **L1:** On-call engineer — identify reason, assess scope.
- **L2:** Tech Lead — if a code/rule change is the root cause and rollback is needed.
- **L3:** Legal/Compliance lead — if the block reveals a genuine compliance risk that requires investigation before resuming sends.

## Recovery Checklist

- [ ] Block reason identified and documented.
- [ ] If false positive: override record created with justification; root cause in classifier noted.
- [ ] If rule misconfiguration: feature flag disabled; fix queued.
- [ ] Affected tenants notified of root cause and expected resolution.
- [ ] `compliance_blocks_total` returning to baseline rate.
- [ ] Audit events reviewed to confirm no legitimate violations were overridden.
- [ ] Status page updated.

## Follow-up Actions

- [ ] If false positive: add the sample to the classifier eval fixtures; schedule a model re-evaluation.
- [ ] Postmortem if SEV2 or higher.
- [ ] If a compliance rule was rolled back: write a new `/create-compliance-rule` PR with the corrected logic and a regression test.
- [ ] Review ComplianceGuard HITL override rate in Grafana — rising HITL rates indicate classifier tuning is needed.
