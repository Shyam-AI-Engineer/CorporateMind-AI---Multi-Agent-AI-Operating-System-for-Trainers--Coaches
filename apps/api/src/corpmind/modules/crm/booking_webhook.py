"""Inbound booking webhook endpoint (ADR-0009 — Generic Booking Webhook).

Public endpoint — bypassed by TenantMiddleware via _PUBLIC_PREFIXES entry
"/api/v1/webhooks/".  Authentication is HMAC-SHA256 verification against
the per-workspace shared secret stored in Workspace.booking_webhook_secret.

Flow:
  1. Read raw request body (needed for HMAC before JSON parsing).
  2. Look up workspace + secret (public session, no RLS — workspaces table
     has no tenant_id / RLS policy).
  3. Verify HMAC-SHA256 using hmac.compare_digest (constant-time).
  4. Parse body as BookingWebhookPayload.
  5. Manually set TenantContext from workspace.org_id.
  6. Activate Postgres RLS for the session.
  7. Delegate to CRMService.process_booking_event() — all CRM mutations
     happen inside a single session transaction.
  8. Return {"status": "ok"} — always 200 after HMAC passes (booking tools
     interpret non-2xx as delivery failure and retry).
"""

from __future__ import annotations

import hashlib
import hmac
import uuid

import structlog
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.database import get_public_session, set_rls_tenant
from corpmind.core.exceptions import AuthenticationError, ValidationError
from corpmind.core.tenancy import TenantContext, clear_tenant_context, set_tenant_context
from corpmind.modules.crm.schemas import BookingWebhookPayload
from corpmind.modules.crm.service import CRMService
from corpmind.modules.identity.models import Workspace

log = structlog.get_logger(__name__)

router = APIRouter()

_SIGNATURE_HEADER = "X-Booking-Signature"


@router.post(
    "/booking/{workspace_id}",
    include_in_schema=False,  # not in public OpenAPI docs
    summary="Receive a booking webhook event",
)
async def receive_booking_webhook(
    workspace_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_public_session),
) -> dict[str, str]:
    """HMAC-verified inbound booking event from any provider.

    Returns 200 on HMAC pass even when the event is skipped (contact not found,
    duplicate, unsupported type) so the booking tool does not retry needlessly.
    Returns 401 on HMAC failure to signal a misconfigured secret.
    """
    raw_body = await request.body()

    # 1. Look up workspace (no RLS — workspaces has no tenant isolation policy)
    result = await session.execute(
        select(Workspace).where(
            Workspace.id == workspace_id,
            Workspace.is_active.is_(True),
        )
    )
    workspace = result.scalar_one_or_none()
    if not workspace or not workspace.booking_webhook_secret:
        # Return 200 to avoid leaking info about workspace existence / secret state.
        log.info(
            "booking_webhook.no_workspace_or_secret",
            workspace_id=str(workspace_id),
        )
        return {"status": "ok"}

    # 2. Verify HMAC-SHA256 (constant-time comparison)
    signature = request.headers.get(_SIGNATURE_HEADER, "")
    expected = hmac.new(
        workspace.booking_webhook_secret.encode(),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        log.warning(
            "booking_webhook.invalid_signature",
            workspace_id=str(workspace_id),
        )
        raise AuthenticationError("Invalid webhook signature")

    # 3. Parse payload
    try:
        payload = BookingWebhookPayload.model_validate_json(raw_body)
    except Exception as exc:
        raise ValidationError(f"Invalid webhook payload: {exc}") from exc

    # 4. Build TenantContext from workspace (no JWT — webhook uses HMAC auth)
    ctx = TenantContext(
        org_id=workspace.org_id,
        workspace_id=workspace.id,
        user_id=uuid.UUID(int=0),  # system actor — no human user
        role="system",
        request_id=request.headers.get("X-Request-ID", str(uuid.uuid4())),
    )
    token = set_tenant_context(ctx)

    try:
        # 5. Activate RLS so all subsequent queries are tenant-scoped
        await set_rls_tenant(session, workspace.org_id)

        # 6. Process — all CRM mutations in the same session transaction
        await CRMService(session).process_booking_event(workspace.id, payload)

    finally:
        clear_tenant_context(token)

    return {"status": "ok"}
