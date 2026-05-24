# Compliance & Anti-Spam Rules (NON-NEGOTIABLE)

Every outbound message — email, WhatsApp, Telegram, IG, FB, LinkedIn post — passes through `ComplianceGuardAgent` **before** dispatch. There is no exception path.

## What ComplianceGuard checks (in order)
1. **Opt-in** for `(tenant, contact, channel)` exists and is current.
2. **Unsubscribe** list — global per tenant; honored across all channels.
3. **Frequency cap** — default ≤ 2 marketing messages / 7 days / cross-channel. Configurable per tenant, never disabled.
4. **WhatsApp 24-hour customer-care window** — enforced via session-state lookup; approved templates required outside the window.
5. **Duplicate detection** — content + recipient hash; soft block with manager override.
6. **Content classifier** — flags spam-like, deceptive, or policy-violating content.
7. **Tenant budget** — channel-specific send budget remaining.
8. **HITL gate** — see `langgraph-agents.md` triggers.

## Audit
- Every send AND every block is written to `audit_events` (append-only) with reason, recipient, channel, content hash, tenant, actor.
- Audit log retention: 7 years for Enterprise, 2 years for others.

## Channel-specific rules
- **Email**: physical address + unsubscribe footer in every campaign send. `List-Unsubscribe` header honored automatically.
- **WhatsApp Business Cloud API**: only official templates outside 24h window; rate-limited per Meta tier; opt-in proof stored.
- **LinkedIn**: PUBLIC company-page posts and public-data lookups ONLY. **Never automate personal DMs.** Never scrape private profiles. This is permanent — no override.
- **Telegram / IG / FB**: provider TOS adherence; HMAC-verified webhooks; no engagement-bot patterns.

## Opt-in evidence
Every `hr_contacts` row that's receivable stores:
- `source` (URL or system that produced the contact)
- `source_type` (webinar registration, company website, public directory, ...)
- `opted_in_at` (timestamp)
- `opt_in_evidence` (URL / screenshot reference / consent record)
Contacts without complete opt-in evidence are flagged `non_contactable` and cannot be added to send segments.

## DPDP / GDPR
- Right to erasure: cascading soft-delete + 30-day hard purge job. Implemented as a tenant-scoped admin endpoint.
- Data export: per-tenant ZIP of all PII the tenant owns, generated on request, signed URL, expires 24h.
- Breach notification: 72h clock per DPDP/GDPR. See `incident-response.md`.

## Forbidden
- Bypassing ComplianceGuard for "just a test send" — use a sandbox tenant with synthetic contacts.
- Disabling frequency cap programmatically.
- Storing decrypted phone/email in logs or analytics dumps.
- Adding a contact whose opt-in source is "scraped from LinkedIn" or "purchased list".
