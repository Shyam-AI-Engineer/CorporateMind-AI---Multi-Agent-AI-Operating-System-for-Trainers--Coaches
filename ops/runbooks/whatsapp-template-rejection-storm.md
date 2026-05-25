# Runbook: WhatsApp Template Rejection Storm

## Incident Summary

Meta has rejected one or more approved WhatsApp message templates for one or multiple tenants, causing campaign sends to fail silently or with errors. In a rejection storm, multiple templates are rejected in rapid succession — often after a Meta policy update or quality flag on the Business Account.

## Trigger Conditions

- WhatsApp Business Cloud API returning `error_code: 1013` (template not approved) or `error_code: 131026` (template paused by Meta).
- Prometheus alert: `channel_send_total{channel="whatsapp", status="rejected"}` > 10/minute.
- Grafana Channels dashboard shows WhatsApp delivery rate dropping below 80%.
- Tenant complains that WhatsApp campaigns are not sending.
- Meta Business Manager shows templates in "Rejected" or "Paused" status.

## Severity Level

- **SEV3** — single template rejected, affecting one campaign.
- **SEV2** — multiple templates rejected, blocking primary outreach channel for one or more tenants.
- **SEV1** — entire Business Account flagged or suspended by Meta.

## Immediate Response Steps

1. **Identify scope** — check the WhatsApp template registry in the admin panel (`/admin/v1/channels/whatsapp/templates`) to see which templates are rejected and for which tenants.
2. **Check Meta Business Manager** — log in to the tenant's connected Meta Business Account to see the rejection reason.
3. **Pause affected campaigns** — in the admin panel, set `campaign.status = paused` for campaigns using rejected templates. Prevents further failed send attempts.
4. **Check rejection reason** — common reasons:
   - `ABUSIVE_CONTENT` — template content violates Meta policies.
   - `INCORRECT_CATEGORY` — template categorized incorrectly (marketing vs. utility vs. authentication).
   - `INVALID_FORMAT` — template has formatting errors.
5. **For paused templates (recoverable):** Templates paused for quality issues can be revised and resubmitted. Draft a revised template in the admin panel template editor.
6. **For suspended accounts (SEV1):** Escalate to Meta Business Support immediately. Do not retry sends. Flip the WhatsApp kill-switch: `channels.whatsapp.enabled = false`.
7. **Notify affected tenants** — inform them that their WhatsApp campaigns are paused and provide the rejection reason.

## Escalation Path

- **L1:** On-call engineer — pause campaigns, identify scope.
- **L2:** Tech Lead + Customer Success — if tenant revenue is directly impacted.
- **L3:** Meta Business Support escalation (tenant account ID + phone number ID required). Contact details in `ops/secrets.md`.

## Recovery Checklist

- [ ] Revised templates submitted and approved in Meta Business Manager.
- [ ] Template registry updated with new template IDs.
- [ ] Campaign `status` set back to `active` after template re-approval.
- [ ] Test send to sandbox contact confirms template is working.
- [ ] Affected tenants notified of resolution.
- [ ] `channels.whatsapp.enabled = true` if kill-switch was flipped.
- [ ] Status page updated.

## Follow-up Actions

- [ ] Review template content to understand what triggered the rejection — document for future template guidelines.
- [ ] Add the rejection reason to the content classifier in ComplianceGuardAgent to catch similar content proactively.
- [ ] If multiple tenants affected simultaneously, check whether a Meta policy update triggered the storm — document in a postmortem.
- [ ] Consider adding a template health check to the daily automation job.
