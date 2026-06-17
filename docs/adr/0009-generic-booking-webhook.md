# ADR-0009: Generic Booking Webhook Architecture

- **Status:** Accepted
- **Date:** 2026-06-17
- **Deciders:** Shyam (Founder/Engineer), Claude Sonnet 4.6 (Staff Engineer AI)

## Context

After Sprint 13 delivered the Lead Detail page with manual meeting scheduling, the
critical workflow gap is that trainers must manually enter meeting times after an HR
contact books through an external tool.  Indian corporate trainers use a variety of
booking tools — Calendly, Cal.com, Tidycal, Savvycal, and Google Booking pages — with
no dominant choice.

The core business need: when an HR contact books a meeting slot, the CRM lead should
automatically have `meeting_scheduled_at` set and a CRM activity should be logged,
without the trainer having to do anything.

Two forces are in tension:
1. **Vendor diversity**: locking to Calendly-specific OAuth would break for trainers
   using other tools, and would require ongoing maintenance of Calendly's API changes.
2. **Simplicity**: a custom OAuth integration per provider is O(N) engineering effort
   and multiplies credential-rotation surface area.

The booking webhook belongs in the `corpmind/channels/` family conceptually, but
`channels/` handles outbound messaging channels (Email, WA, TG, etc.), not inbound
booking events.  The `ChannelAdapter` ABC (`channels/base.py`) was designed for a
different event shape.  A purpose-built webhook handler is cleaner.

The `corpmind.core.tenancy.TenantMiddleware` was pre-wired with `"/api/v1/webhooks/"`
in `_PUBLIC_PREFIXES`, confirming the original design anticipated inbound webhook
endpoints at this prefix.

## Decision

Implement a **provider-agnostic booking webhook endpoint** at
`POST /api/v1/webhooks/booking/{workspace_id}` verified by a per-workspace
HMAC-SHA256 shared secret.

### Key decisions

**1. Provider-agnostic, not Calendly-specific.**
The request body is a normalized JSON payload defined by us (`BookingWebhookPayload`).
Each provider (Calendly, Cal.com, etc.) has documented how to configure their webhook
to hit our URL.  A thin per-provider translation layer lives in their dashboard
configuration, not in our code.

**2. Workspace ID in the path, not a query param or header.**
`/api/v1/webhooks/booking/{workspace_id}` lets the trainer give each booking tool a
unique URL.  The workspace_id identifies which tenant and which secret to verify
against, without requiring a JWT.

**3. HMAC-SHA256 shared secret, not OAuth.**
Booking tools universally support HMAC webhook verification; OAuth would require
maintaining per-provider authorization flows and token refresh.  The secret is stored
on `Workspace.booking_webhook_secret` (VARCHAR(255)).  Trainers regenerate it via an
authenticated API endpoint.  HMAC verification uses `hmac.compare_digest()` for
constant-time comparison.

**4. `booking_webhook_events` table as idempotency anchor.**
`UNIQUE(tenant_id, provider, provider_event_id)` prevents double-processing of retried
webhooks.  The unique constraint + INSERT on first call = exactly-once semantics within
a single DB transaction.

**5. Additive-only CRM mutations.**
Processing a booking webhook sets `Lead.meeting_scheduled_at` and
`Lead.booking_provider_event_id`, and logs a `booking_confirmed` CRM activity.  It
does NOT advance the lead stage (stage advancement remains a trainer action — booking a
slot != completing the meeting).

**6. Cross-module contact lookup via raw SQL.**
`process_booking_event()` lives in `CRMService` and needs to find an `HRContact` by
email.  The module boundary rule (`backend-python.md`) forbids importing
`hr_discovery.repo` or `hr_discovery.models`.  Consistent with the existing pattern
in `proposals/service.py` (line 361), a `sqlalchemy.text()` query reads `hr_contacts`
directly.

**7. Feature flag gated.**
The endpoint checks `is_enabled("crm.booking_webhook.enabled", tenant=workspace_id)`
before processing.  Default is ON (the endpoint is live but processing is gated).
Kill-switch flag: flip to OFF to stop processing without a deploy.

## Alternatives considered

### Option A — Calendly-specific OAuth integration
- Calendly OAuth2 flow, webhook subscription management, token refresh.
- **Rejected**: couples the product to one vendor; 60%+ of target trainers use tools
  other than Calendly.  O(N) engineering per provider.

### Option B — Generic webhook with per-provider payload adapters in code
- Our endpoint accepts any provider's native payload; we write a normalizer per
  provider (Calendly schema, Cal.com schema, etc.) that runs server-side.
- **Partially accepted**: the current ADR is a step toward this.  Provider-specific
  normalizers can be added in a future sprint without changing the endpoint contract.
  For now, trainers configure the normalized payload in their booking tool's custom
  fields (most tools support this).

### Option C — Manual-only (Sprint 13 baseline)
- Trainers manually enter meeting times in the Lead Detail UI.
- **Superseded** by this ADR.  Remains as the fallback if webhook processing is
  disabled (flag off) or contact is not found.

## Consequences

### Positive
- Works with any booking tool the trainer already uses — zero switching cost.
- No OAuth tokens to rotate or expire silently.
- Idempotency built into the schema from day one.
- Trainers who don't use a booking tool continue using the manual UI unchanged.
- Feature-flag gated: safe to deploy to prod before any trainer has configured it.
- Extensible: per-provider payload adapters can be added without changing the endpoint.

### Negative
- Trainers must do a one-time configuration in their booking tool (copy URL + secret).
- Normalized payload requires the invitee's email to be present — if a booking tool
  omits it, the contact lookup will fail and the event will be logged as `skipped`.
- No OAuth means we cannot read the trainer's calendar or create calendar events
  (Phase 3 concern).

### Neutral
- `Lead.meeting_scheduled_at` becomes settable by two paths: manual UI + webhook.
  Both write the same field; last-writer-wins (no conflict resolution needed at MVP).
- The webhook URL leaks the `workspace_id` UUID to whoever holds it, but UUIDs are
  not guessable and the HMAC prevents replay.

## References

- Sprint 14 Architecture Audit (this conversation)
- ADR-0006: Expand-then-Contract Migrations
- `apps/api/src/corpmind/core/tenancy.py` — `_PUBLIC_PREFIXES`
- `apps/api/src/corpmind/channels/base.py` — `ChannelAdapter.handle_webhook()` ABC
- `apps/api/src/corpmind/modules/crm/repo.py` — `AutomationLogRepo.reserve()` idempotency pattern
- `apps/api/src/corpmind/modules/proposals/service.py:361` — cross-module raw SQL pattern
