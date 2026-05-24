---
name: create-channel-adapter
description: Add a new outbound/inbound channel adapter (Email/WA/TG/IG/FB/LI/...) implementing the ChannelAdapter ABC
---

# Create Channel Adapter Skill

## Goal
Add a new channel adapter that integrates with the unified outreach system. All provider-specific code stays inside `apps/api/src/corpmind/channels/<name>/`.

## Steps
1. **Ask for:** channel name, provider API docs/reference, message types supported, rate limits, opt-in semantics, webhook events (if any).
2. **Create the adapter directory:**
   ```
   apps/api/src/corpmind/channels/<name>/
   ├── __init__.py
   ├── adapter.py      # implements ChannelAdapter ABC (send/fetch_status/handle_webhook)
   ├── schemas.py      # channel-specific message + webhook schemas
   ├── webhook.py      # inbound handler with HMAC verification (if applicable)
   ├── config.py       # pydantic-settings: API keys, base URL, rate-limit config
   └── normalize.py    # provider format ↔ internal OutboundMessage/InboundEvent
   ```
3. **Implement `send()`:**
   - Normalize internal `OutboundMessage` → provider payload.
   - Route through `ComplianceGuardAgent.check()` first. No bypass.
   - Wrap in retry with exponential backoff + jitter.
   - Apply per-channel Redis token-bucket rate limit.
   - Wrap in circuit breaker; respect open state.
   - Emit Prometheus metrics + structured log.
4. **Implement `handle_webhook()`:**
   - Verify HMAC signature BEFORE parsing.
   - Replay protection via Redis lock on `event_id`.
   - Normalize provider event → internal `InboundEvent`.
   - Publish to the event bus.
5. **Register** the adapter in `apps/api/src/corpmind/channels/registry.py`.
6. **Add opt-in tracking** integration with `compliance` module — every send updates last-contact, every webhook can flip opt-in state (e.g., unsubscribe reply).
7. **Tests:**
   - Unit: normalization roundtrip.
   - Unit: HMAC verification (positive and tampered cases).
   - Integration: send via provider sandbox if available.
   - Integration: webhook handler with sample provider payloads.
   - Replay protection: same `event_id` twice → second is dropped.
   - Compliance: send without opt-in → blocked + audited.

## Quality rules
- Implement the common `ChannelAdapter` ABC — no channel-specific logic in core services or agents.
- Normalize ALL messages to the internal unified schema (`OutboundMessage`, `InboundEvent`).
- Retry with exponential backoff + jitter (1s, 3s, 9s) for outbound delivery.
- Validate webhook signatures on ALL inbound requests, BEFORE parsing.
- Respect provider rate limits (Redis token bucket per provider).
- Queue messages when the channel is open-circuit; surface degraded state in UI.
- NEVER hardcode API keys or endpoints — pydantic-settings only.
- Log delivery attempts with status + latency; never log message body.
- Add a kill-switch feature flag `channel.<name>.enabled`.

## Channel-specific reminders
- **WhatsApp**: enforce 24-hour customer-care window; templates required outside. Track tier + per-tier rate.
- **LinkedIn**: PUBLIC company-page posts and public-data lookups ONLY. Never automate personal DMs.
- **Email**: physical address + unsubscribe footer; honor `List-Unsubscribe`.
- **Telegram / IG / FB**: provider TOS adherence; no engagement-bot patterns.

## References
- `.claude/rules/channel-adapter.md`
- `.claude/rules/compliance-guard.md`
- `.claude/rules/security.md`
