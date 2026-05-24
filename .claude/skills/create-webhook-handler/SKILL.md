---
name: create-webhook-handler
description: Add an inbound webhook handler with HMAC verification, replay protection, and event normalization
---

# Create Webhook Handler Skill

## Goal
Add an inbound webhook endpoint for an external provider (WhatsApp, Telegram, Instagram, Facebook, Calendly, Stripe/Razorpay, etc.). Webhooks are the most failure-prone surface; correctness here is non-negotiable.

## Steps
1. **Ask for:** provider name, signing scheme (HMAC-SHA256 / RSA / other), header name(s) carrying the signature, expected event types, replay-window duration.
2. **Add the endpoint** in `apps/api/src/corpmind/webhooks/<provider>.py`:
   - Route: `/webhooks/v1/<provider>` (mounted under `/webhooks` prefix, not the tenant-scoped `/api/v1`).
   - Accept raw bytes body — do NOT let FastAPI parse before verification.
3. **Verify signature BEFORE parsing:**
   ```python
   raw_body = await request.body()
   if not verify_hmac(raw_body, headers, secret):
       raise WebhookSignatureError()
   payload = json.loads(raw_body)
   ```
4. **Replay protection:**
   - Extract provider's event ID (or compute body hash if none).
   - `SET event_id NX EX <provider_retry_window>` in Redis. If key existed → drop with 200 OK (idempotent).
5. **Normalize → internal event:** map provider payload to an `InboundEvent` schema; never let provider format leak past this boundary.
6. **Publish to event bus** — `events.publish("<domain>.<verb_past>", payload, tenant_id=...)`. The event log captures it for replay (see `.claude/rules/observability.md`).
7. **Return 2xx fast** — webhook handlers must not do heavy work synchronously. Enqueue Celery task if processing is non-trivial.
8. **Tests:**
   - Valid signature → 200 + event published.
   - Tampered body → 401, no event published.
   - Missing signature header → 401.
   - Duplicate event_id within window → 200, no duplicate event.
   - Malformed payload → 400, structured error.
   - Provider-specific edge cases (e.g., WhatsApp status callback variants).

## Quality rules
- Signature verified BEFORE body parse. Always.
- Use `hmac.compare_digest` (constant-time) for HMAC comparison.
- Secret per (tenant, provider) when possible; global secret only for non-tenant-scoped providers (e.g., Stripe platform webhook).
- Replay protection on every webhook. Without it, retries cause duplicate side effects.
- Webhook endpoints are NOT tenant-scoped via JWT — resolve the tenant from the payload (e.g., WhatsApp phone_number_id) and bind `TenantContext` explicitly.
- Return 2xx quickly. Slow webhooks get rate-limited by providers.
- Log signature failures with provider + headers (without leaking the secret).
- No PII in webhook handler logs.

## References
- `.claude/rules/channel-adapter.md`
- `.claude/rules/security.md`
- `.claude/rules/observability.md`
