# Runbook: Outreach Mass Bounce

## Incident Summary

A high percentage of outbound emails or messages are bouncing or being rejected by receiving mail servers or channel providers. This may indicate a domain reputation issue, blocklist listing, or a misconfigured campaign targeting non-deliverable addresses.

## Trigger Conditions

- Email bounce rate > 5% in a single campaign (industry threshold for hard bounces: > 2% is concerning).
- Prometheus alert: `channel_send_total{channel="email", status="bounced"}` > 50 in a 30-minute window.
- Grafana Channels dashboard shows delivery rate dropping below 90% for email.
- SendGrid / Postmark / SES reporting a sending suspension or warning.
- Multiple tenants reporting that their email campaigns show zero delivery.
- Domain blacklist check returns positive for our sending domain.

## Severity Level

- **SEV3** — single tenant, low volume, transient bounce spike. Likely bad contact list.
- **SEV2** — multiple tenants, high bounce rate, our sending domain reputation at risk.
- **SEV1** — our sending domain is blacklisted, all email delivery suspended.

## Immediate Response Steps

1. **Check bounce rate by tenant and campaign:**
   - Admin panel → Analytics → Outreach → filter by `status=bounced` last 30 minutes.
   - Identify whether bounces are concentrated in one tenant's campaign or spread across all tenants.
2. **Check sending domain reputation:**
   - Run domain on MXToolbox blacklist check (or use the admin diagnostic script).
   - Check the email provider (SendGrid/Postmark) dashboard for bounces, spam complaints, and suppression list entries.
3. **Classify the bounce type:**
   - **Hard bounce (invalid address):** Permanently remove from the contact list. Mark `hr_contacts.email_deliverable = false`. Do not retry.
   - **Soft bounce (mailbox full, server temporarily unavailable):** These auto-retry. Do not act unless the rate is sustained.
   - **Spam complaint:** The recipient marked the email as spam. This is the most damaging bounce type for domain reputation. Investigate content.
4. **If a campaign is generating excessive spam complaints (SEV2):**
   - Pause the campaign immediately: `campaign.status = paused`.
   - Review the campaign's email content for spam-trigger phrases.
   - Check if ComplianceGuardAgent ran — if it did and passed, the content classifier needs tuning.
5. **If the sending domain is blacklisted (SEV1):**
   - Pause all outbound email sends immediately (flip `channels.email.enabled = false`).
   - Submit a delisting request to the blocklist provider (requires clean send history evidence).
   - Activate the backup sending domain (see `ops/secrets.md` for backup SMTP configuration).
   - Notify all tenants of email degradation.

## Escalation Path

- **L1:** On-call engineer — identify scope, pause affected campaigns.
- **L2:** Tech Lead + Customer Success — if domain reputation is at risk or tenants are directly impacted.
- **L3:** Email provider support (SendGrid/Postmark/SES) — if account suspended or blacklist delisting is needed. Contact details in `ops/secrets.md`.

## Recovery Checklist

- [ ] Bounce root cause identified (bad contact list / content / domain reputation).
- [ ] Hard bounces marked as non-deliverable in `hr_contacts` table; suppressed in provider suppression list.
- [ ] Campaign paused if spam complaint rate exceeded provider threshold.
- [ ] Domain reputation confirmed clean (MXToolbox, provider dashboard).
- [ ] `channels.email.enabled = true` if it was disabled.
- [ ] Affected tenants notified with bounce summary and guidance on list hygiene.
- [ ] Email delivery rate back above 95%.
- [ ] Status page updated.

## Follow-up Actions

- [ ] Add email validation step to the HR contact ingestion pipeline (DNS-level MX record check on domain).
- [ ] Review ComplianceGuardAgent content classifier to better detect spam-risk copy before send.
- [ ] If a single campaign caused the spike: postmortem on why ComplianceGuard passed it.
- [ ] Add bounce rate as a per-campaign SLO in the analytics dashboard (alert at > 3%).
- [ ] Consider warmup strategy for new sending domains (sending volume ramp-up).
