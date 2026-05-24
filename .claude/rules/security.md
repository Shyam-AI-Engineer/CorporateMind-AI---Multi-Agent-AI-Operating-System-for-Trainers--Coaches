# Security Rules

## AuthN / AuthZ
- JWT (RS256), 15-min access + 30-day refresh, httpOnly cookies for web sessions.
- MFA enforced for `OrgAdmin+` roles.
- RBAC via Casbin; policies version-controlled in `apps/api/src/corpmind/core/rbac/policy.csv`.
- Deny-overrides-grant semantics. Built-in roles: `OrgAdmin | AgencyManager | Trainer | Reviewer | Analyst`.

## Input handling
- Validate + sanitize ALL untrusted input — uploads, webhooks, agent tool outputs, scraped HR data.
- Treat uploaded posters/videos/PDFs as untrusted; sandbox parsing (timeouts, memory caps).
- Never expose stack traces to end users. Map exceptions to safe `{code, message, request_id}` envelope.

## Secrets
- `pydantic-settings` from env only. Never hardcoded.
- Prod: Doppler / Infisical. Preview: Railway Secrets. Local dev: `.env` (gitignored).
- CI fails on `gitleaks` finding.
- Rotation: 90-day for service keys; per-tenant channel tokens rotated on user request.

## Transport
- TLS 1.3 everywhere. HSTS preload.
- mTLS between internal services from Stage 2 onward.

## At-rest
- Postgres TDE.
- Cloudinary / S3 server-side encryption.
- Per-tenant channel OAuth refresh tokens encrypted at column level.

## PII handling
- Phone hashed in analytics tables (HMAC with per-org salt).
- Email stored as-is for delivery but redacted in logs.
- Presidio analyzer runs on every prompt before model call; redacted tokens reversed only in tenant-scoped post-processing.
- See `compliance-guard.md` for DPDP/GDPR erasure + export.

## Prompt injection
- LLM-Guard input filter on every user-supplied content that enters an LLM call.
- Output validators with allowlist for tool invocation.
- An agent CANNOT call a tool not in its registered toolset.

## Rate limits
- Per-tenant, per-endpoint, per-IP layered (Redis token bucket).
- Abusive IP auto-blocked at Cloudflare WAF.

## Audit
- Every privileged operation (RBAC change, cross-tenant access, billing change, send-block override) → `audit_events` (append-only).
- 7-year retention for Enterprise; 2-year for others.

## File uploads
- Cloudinary upload signed by backend; client never holds the upload key.
- File-type + size enforced server-side after upload (don't trust client-declared types).
- Virus scan integration for Enterprise tier.

## Webhooks (inbound)
- HMAC signature verified BEFORE parsing the body.
- Replay protection via `event_id` Redis lock with TTL > provider retry window.

## Forbidden
- `eval`, `exec`, `pickle.loads` on untrusted input.
- Logging full request/response bodies (PII risk).
- Returning raw exception messages to the client.
- Storing decrypted credentials at rest.
