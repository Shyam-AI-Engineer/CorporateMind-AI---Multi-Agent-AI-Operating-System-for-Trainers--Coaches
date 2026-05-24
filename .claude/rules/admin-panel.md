# Admin Panel Rules

The admin panel is internal-only and provides cross-tenant operational tooling for support, billing, and incident response. It is the most security-sensitive surface in the product.

## Access
- Backed by a separate route prefix: `/admin/v1/*` on the FastAPI app.
- Authentication: same JWT but MFA-required AND role `PlatformAdmin` (a CorporateMind employee, never a tenant user).
- All admin routes require an explicit `@platform_admin_only` decorator that:
  - Asserts role.
  - Writes an `audit_events` row BEFORE the handler runs.
  - Wraps the handler in a Sentry breadcrumb.

## What it does (Phase 1)
- Tenant list, tenant details (read-only by default; mutations gated).
- Subscription management (overrides, manual extensions).
- Impersonation for support: time-limited session as a tenant user, banner visible, every action audited.
- Workflow inspector: read a failed run's full state diff per node.
- Compliance investigator: search audit events by recipient / channel / timeframe.
- Feature-flag editor: toggle, set tenant cohort, set expiry.
- Prompt-template editor: read-only in Phase 1 (edits via PR).
- Kill switches: global pause for a channel or an agent.

## What it does NOT do
- Read tenant raw PII (phone, email) — they appear masked. Reveal requires a documented justification + a second-admin approval.
- Edit tenant data directly outside a defined support workflow.
- Issue refunds without billing-team co-sign.

## Frontend
- Lives at `apps/web/app/(admin)/*` — separate from the customer dashboard.
- Visible only when the JWT carries `role: PlatformAdmin`.
- Hard-coded banner: "ADMIN VIEW — All actions logged."

## Impersonation
- Time-boxed (default 1 hour, max 4 hours).
- Banner across the impersonated UI: "Impersonated by <admin> · ends in <time>."
- Every API call in the impersonated session carries `X-Impersonated-By: <admin_id>`.
- Auto-revoked on session expiry; cannot be silently extended.

## Forbidden
- Admin routes that aren't audited.
- Reading raw PII without the documented reveal flow.
- Plain-text export of tenant data without legal sign-off.
- Storing admin credentials in tooling/scripts.
