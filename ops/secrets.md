# Secret Owners & Rotation Schedule

This document tracks which team member owns each secret category, the rotation schedule, and where the actual secrets live (never in this file).

**IMPORTANT: Never store actual secret values in this file. This file tracks ownership and rotation metadata only.**

---

## Secret Storage Locations

| Environment | Secret Store | Access |
|---|---|---|
| Production | Doppler (production config) | IC + Tech Lead |
| Staging | Doppler (staging config) | Engineering team |
| Preview | Railway Secrets per PR | CI/CD pipeline |
| Local dev | `.env` (gitignored, self-generated) | Individual developer |

---

## Secret Inventory

### LLM / AI Gateway

| Secret | Owner | Rotation | Notes |
|---|---|---|---|
| `EURI_API_KEY` | Tech Lead | 90 days | Euri AI Gateway API key |
| `LANGFUSE_PUBLIC_KEY` | Tech Lead | On compromise | Langfuse project key |
| `LANGFUSE_SECRET_KEY` | Tech Lead | On compromise | Langfuse project secret |

### Database & Infrastructure

| Secret | Owner | Rotation | Notes |
|---|---|---|---|
| `DATABASE_URL` | Tech Lead | On compromise | Postgres connection string (Railway managed) |
| `REDIS_URL` | Tech Lead | On compromise | Redis connection string (Railway managed) |
| `QDRANT_API_KEY` | Tech Lead | 90 days | Qdrant cloud API key |
| `SECRET_KEY` | Tech Lead | 90 days | FastAPI/JWT signing key (RS256 private key) |
| `JWT_PUBLIC_KEY` | Tech Lead | With private key | RS256 public key |

### Channel Providers

| Secret | Owner | Rotation | Notes |
|---|---|---|---|
| `WA_PHONE_NUMBER_ID` | Founder | Per tenant | WhatsApp Business Cloud phone number ID |
| `WA_ACCESS_TOKEN` | Founder | 90 days | WhatsApp Business Cloud access token |
| `WA_WEBHOOK_VERIFY_TOKEN` | Tech Lead | 90 days | Webhook verification token |
| `TELEGRAM_BOT_TOKEN` | Tech Lead | On compromise | Telegram Bot API token |
| `IG_ACCESS_TOKEN` | Founder | 60 days | Instagram Graph API token |
| `FB_PAGE_ACCESS_TOKEN` | Founder | 60 days | Facebook Graph API token |
| `SENDGRID_API_KEY` | Tech Lead | 90 days | Email delivery |

### Observability & Ops

| Secret | Owner | Rotation | Notes |
|---|---|---|---|
| `SENTRY_DSN` | Tech Lead | On compromise | Sentry project DSN |
| `GRAFANA_API_KEY` | Tech Lead | 90 days | Grafana Cloud API key |

### Object Storage

| Secret | Owner | Rotation | Notes |
|---|---|---|---|
| `CLOUDINARY_API_KEY` | Tech Lead | 90 days | Cloudinary upload API key |
| `CLOUDINARY_API_SECRET` | Tech Lead | 90 days | Cloudinary upload API secret |
| `AWS_ACCESS_KEY_ID` | Tech Lead | 90 days | S3 backup storage (if used) |
| `AWS_SECRET_ACCESS_KEY` | Tech Lead | 90 days | S3 backup storage (if used) |

### Security & Compliance

| Secret | Owner | Rotation | Notes |
|---|---|---|---|
| `DPO_EMAIL` | Founder | On personnel change | Data Protection Officer contact |
| `LEGAL_COUNSEL_EMAIL` | Founder | On personnel change | Legal counsel for breach notification |
| `RAILWAY_SECURITY_CONTACT` | Tech Lead | N/A | Railway security team contact URL |

---

## Rotation Procedures

### Standard Rotation (90-day)

1. Generate new secret in the provider dashboard.
2. Update the secret in Doppler (production + staging simultaneously).
3. Verify the new secret works in staging.
4. Deploy to production (Railway picks up the new env var on next deploy).
5. Revoke the old secret in the provider dashboard.
6. Update the `Last rotated` date in this file.

### On-Compromise Rotation

If a secret is suspected to be compromised:
1. Revoke the old secret **immediately** in the provider dashboard.
2. Generate a new secret.
3. Update Doppler and redeploy immediately (see `emergency-hotfix.md` for the deploy path).
4. Check provider audit logs for unauthorized usage.
5. File an incident report.

---

## Rotation Log

| Secret | Last Rotated | Next Due | Rotated By |
|---|---|---|---|
| `EURI_API_KEY` | 2026-05-25 (initial) | 2026-08-23 | Shyam |
| `SECRET_KEY` | 2026-05-25 (initial) | 2026-08-23 | Shyam |
| (all others) | 2026-05-25 (initial) | See schedule | Shyam |

---

*This file is reviewed quarterly. Any secrets older than their rotation schedule are escalated to the IC for immediate rotation.*
