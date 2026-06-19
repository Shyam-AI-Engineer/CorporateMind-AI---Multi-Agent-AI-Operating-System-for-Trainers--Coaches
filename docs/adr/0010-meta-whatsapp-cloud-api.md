# ADR-0010: Meta WhatsApp Cloud API as the WhatsApp Provider

- **Status:** Accepted
- **Date:** 2026-06-18
- **Deciders:** Shyam (Founder/Engineer), Claude Sonnet 4.6 (Staff Engineer AI)

## Context

Sprint 16A adds WhatsApp as the second outbound channel.  Three options were
evaluated: direct Meta Cloud API, Twilio (as a BSP), and a generic BSP
abstraction layer.

CorporateMind AI's primary market is Indian corporate trainers whose outreach
targets HR professionals.  WhatsApp penetration among Indian professionals is
near-universal, making it the highest-ROI second channel after email.

The existing `ChannelAdapter` Protocol in `channels/base.py` already defines the
interface (`send`, `fetch_status`, `handle_webhook`) and `OutboundMessage` already
carries `template_id: str | None`, anticipating exactly this integration.

`core/config.py` already declares `WHATSAPP_BUSINESS_ACCOUNT_ID`,
`WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_WEBHOOK_VERIFY_TOKEN`,
and `WHATSAPP_WEBHOOK_SECRET`, indicating the original design always planned Meta
Cloud API directly.

Two options were formally compared:

**Option A — Meta WhatsApp Cloud API (direct)**
- No per-message intermediary cost
- Official Meta support; highest reliability
- Webhooks deliver delivery receipts, read receipts, and inbound messages
- Requires Meta WABA (WhatsApp Business Account) verification
- Template approval per language: 24–72h from Meta review team

**Option B — Twilio WhatsApp (BSP layer)**
- Faster sandbox for dev/test
- Still requires Meta WABA; Twilio acts as the BSP
- ~$0.005–0.008 USD per-message surcharge vs. Meta direct pricing
- Adds third-party dependency: Twilio outage = our outage even if Meta is up
- Credential duplication (Twilio account + Meta WABA ID)

## Decision

Use **Meta WhatsApp Cloud API directly** via `POST /graph.facebook.com/{version}/{phone_number_id}/messages`.

The `WhatsAppCloudAdapter` in `channels/whatsapp_cloud.py` is the sole caller of
the Meta Graph API.  All other code — outreach service, compliance, Celery tasks —
talks to this adapter through `channels/registry.get("whatsapp")`.

## Alternatives considered

### Option B — Twilio WhatsApp
- Rejected: per-message surcharge compounds at scale; adds a third-party failure
  domain without material benefit.  Twilio's sandbox convenience is outweighed by
  the cost and operational overhead.

### Option C — Generic BSP abstraction
- Rejected: premature abstraction.  The `ChannelAdapter` Protocol already provides
  the abstraction boundary.  A BSP-selection layer on top adds complexity for
  currently zero providers beyond Meta.  If a second WA BSP is ever needed, the
  adapter interface accommodates it without an additional layer.

## Consequences

### Positive
- No per-message intermediary cost
- No third-party dependency in the send path
- Delivery receipts, read receipts, and future inbound messages arrive natively
- The existing `ChannelAdapter` Protocol requires zero changes
- `WHATSAPP_API_VERSION` in config makes Meta API version pinning explicit

### Negative
- Requires Meta WABA verification before sends are live (typically 1–3 business days)
- Meta template approval per language required for cold outreach (24–72h review)
- Meta Graph API is versioned; breaking changes occur with each major version; the
  adapter pins `WHATSAPP_API_VERSION` and must be reviewed at each Meta API sunset

### Neutral
- Feature flag `channel.whatsapp.outbound` gates all sends; WABA approval and
  feature-flag promotion are decoupled from the code deploy
- Phone numbers stored as E.164 in `hr_contacts.phone_e164` (new column) — separate
  from the display-only `phone` field

## References

- `apps/api/src/corpmind/channels/base.py` — `ChannelAdapter` Protocol
- `apps/api/src/corpmind/channels/registry.py` — adapter registration
- `apps/api/src/corpmind/core/config.py` — WhatsApp credential declarations
- `apps/api/src/corpmind/modules/whatsapp/models.py` — `WhatsAppTemplate`, `WhatsAppSession`
- Sprint 16 Architecture Audit (conversation 2026-06-18)
- Meta WhatsApp Cloud API docs: https://developers.facebook.com/docs/whatsapp/cloud-api
