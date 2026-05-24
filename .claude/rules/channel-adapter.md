# Channel Adapter Rules

Every outbound channel (Email, WhatsApp, Telegram, Instagram, Facebook, LinkedIn-post) implements the common `ChannelAdapter` ABC. Provider SDKs are isolated here and nowhere else.

## Where adapters live
```
apps/api/src/corpmind/channels/
├── base.py                    # ChannelAdapter ABC + shared types
├── email_smtp.py
├── whatsapp_cloud.py
├── telegram_bot.py
├── instagram_graph.py
├── facebook_graph.py
└── linkedin_public.py         # public posts + public data only
```

## Interface (minimum surface)
```python
class ChannelAdapter(Protocol):
    name: str

    async def send(self, msg: OutboundMessage) -> SendResult: ...
    async def fetch_status(self, message_id: str) -> DeliveryStatus: ...
    async def handle_webhook(self, payload: bytes, headers: Headers) -> list[InboundEvent]: ...
```

## Quality rules
- One adapter per channel. No channel-specific logic outside `channels/`.
- Provider SDKs imported ONLY in the adapter (and the Euri client). Business modules talk to adapters via the registry.
- Implement message normalization: convert channel-specific format ↔ internal `OutboundMessage` / `InboundEvent` schema.
- Outbound delivery wrapped in retry with exponential backoff + jitter (1s, 3s, 9s).
- Per-channel Redis token-bucket rate limiter tuned to provider limits (WA tier, IG hourly cap, email per-domain throttle).
- Circuit breaker per provider — open after 5 consecutive failures or > 50% error rate in 60s; half-open after 60s.
- Queue messages when the provider is open-circuit; surface degraded state in UI.

## Inbound webhooks
- Every webhook handler verifies HMAC/signature BEFORE parsing the body.
- Replay protection: store `event_id` in Redis with TTL > provider retry window; duplicates dropped.
- Webhook signature secret per (tenant, channel); rotated quarterly.

## ComplianceGuard
- Every `send()` call routes through `ComplianceGuardAgent.check()` first. The adapter cannot bypass it.

## Configuration
- No hardcoded endpoints or keys. All provider config from `pydantic-settings` (env-backed).
- Per-tenant channel credentials encrypted at rest (Postgres column-level encryption).

## Logging & metrics
- Every outbound call emits Prometheus: `channel_send_total{channel,status}`, `channel_send_latency_seconds{channel}`.
- Failed sends log: provider error code, retry count, recipient hash (not raw recipient), tenant_id.

## Testing
- Unit tests for normalization (channel format ↔ internal schema).
- Integration tests for webhook signature verification.
- Contract tests against provider sandboxes when available.

## Adding a new channel
Use the `create-channel-adapter` skill: `/create-channel-adapter`.
