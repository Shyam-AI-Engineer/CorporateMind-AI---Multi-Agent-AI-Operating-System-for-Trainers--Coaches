---
name: review-security
description: Run a focused security review on changed files — input validation, auth, PII, prompt injection, secrets, dependency risk
---

# Review Security Skill

## Goal
Audit a set of changes for security issues before they merge. This is a focused review against `.claude/rules/security.md` — not a substitute for the formal OWASP review at release.

## Steps
1. **Ask for:** the PR / branch / file list to review. Default: `git diff main...HEAD`.
2. **Walk through this checklist for every changed file:**

### Input handling
- [ ] All user-supplied inputs go through Pydantic schemas. No raw `request.json()` parsing into untyped dicts.
- [ ] No `eval`, `exec`, `pickle.loads` on untrusted input.
- [ ] File uploads check type/size SERVER-SIDE (don't trust client-declared types).
- [ ] Untrusted content from scrapers / webhooks is treated as hostile.

### Auth / AuthZ
- [ ] Every new endpoint has explicit auth (no accidental public endpoints).
- [ ] RBAC decorator present and correct role.
- [ ] Admin routes require `@platform_admin_only` (audited, MFA-gated).
- [ ] No raw JWT decode without signature verification.

### PII handling
- [ ] No phone/email in logs (use hashes).
- [ ] No request/response body in logs.
- [ ] Presidio redaction wraps any user content entering an LLM call.
- [ ] DPDP/GDPR erasure path still works for any new entity holding PII.

### Prompt injection
- [ ] User-supplied content into LLMs runs through LLM-Guard input filter.
- [ ] Agent tool calls go through the registered toolset; no string-based dynamic tool dispatch.
- [ ] Output validators on every LLM call.

### Secrets
- [ ] No hardcoded credentials, tokens, URLs (run `gitleaks` locally).
- [ ] All config from `pydantic-settings`.
- [ ] New secrets documented in `ops/secrets.md` with owner + rotation cadence.

### Dependencies
- [ ] New dependencies have a maintained upstream + permissive license.
- [ ] No newly-added LLM-provider SDK imports outside the gateway (mechanically enforced, but verify).
- [ ] `pip-audit` / `npm audit` clean (or known CVEs justified).

### Webhooks
- [ ] HMAC verified BEFORE body parse.
- [ ] Replay protection on `event_id`.
- [ ] Failure modes (bad signature, malformed body) return correct status without leaking internals.

### Rate-limit / abuse
- [ ] Public endpoints have explicit `@rate_limit` decorator.
- [ ] New compute-heavy endpoints have a token budget or HITL gate.

### Cross-tenant
- [ ] Every query filters by `tenant_id` via `TenantContext` (verify by inspection AND test).
- [ ] No SQL that bypasses RLS without an explicit `@cross_tenant_admin_only` decorator + audit.

3. **Summarize findings** as:
   - Critical (must block merge): cross-tenant leak, secret leak, auth bypass, RCE risk.
   - High (must fix before merge): missing input validation on user-facing endpoint, missing audit on admin action.
   - Medium (fix in this PR or open a follow-up): missing rate-limit, missing tenant test.
   - Low / nits: log hygiene, missing docstring.

## Quality rules
- This skill is READ-ONLY review. Do not edit code as part of running it — file findings as PR comments.
- "I didn't see anything obvious" is a valid result; say so explicitly rather than inventing concerns.

## References
- `.claude/rules/security.md`
- `.claude/rules/compliance-guard.md`
- `.claude/rules/multi-tenancy.md`
- `.claude/rules/euri-gateway.md`
