"""WhatsApp inbound message persistence + classification task — Sprint 17A/B.

Sprint 17A scope: webhook → InboxMessage persistence + idempotency.
Sprint 17B scope: fresh-conversation resolution, ReplyClassifierAgent, CRM automation.

Flow
────
1. Redis NX guard on wa:inbound:{provider_message_id} (24h TTL, fail-open).
2a. context_id present → cross-tenant outbound lookup to resolve tenant/workspace/
    outbound_message_id (original Sprint 17A path).
2b. context_id absent  → cross-tenant phone lookup on hr_contacts.phone_e164 to
    resolve contact/tenant/workspace (Sprint 17B fresh-conversation path).
    Ambiguous (phone in multiple tenants) or unknown phones are skipped.
3. TenantContext + RLS set for the resolved tenant.
4. get_or_create_wa_connection() returns (or creates) the system InboxConnection
   for this workspace (provider='whatsapp').
5. InboxService.create_if_not_exists() persists the InboxMessage with channel='whatsapp'.
   The DB-level (connection_id, provider_message_id) unique constraint is the backstop
   if the Redis guard fires open during a cache outage.
6. Best-effort: ReplyClassifierAgent (WA prompt variant) → update_classification()
   → ReplyAutomationService (fresh-conversation overrides when no outbound_message_id).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Literal

import redis as _redis
import structlog
from celery import Task
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from corpmind.core.config import settings
from corpmind.core.database import set_rls_tenant
from corpmind.core.tenancy import TenantContext, clear_tenant_context, set_tenant_context
from corpmind.modules.inbox.models import InboxMessage
from corpmind.modules.inbox.service import InboxService
from corpmind.workers.celery_app import app

log = structlog.get_logger(__name__)

# Matches the webhook delivery-receipt TTL so duplicate inbound events are
# caught within the same replay-protection window as status updates.
_INBOUND_DEDUP_TTL = 86_400  # 24 hours

_WA_CLASSIFY_PROMPT = "inbox.classify_wa_reply"


@app.task(
    bind=True,
    acks_late=True,
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
    soft_time_limit=60,
    time_limit=90,
    queue="ingestion",
    name="corpmind.workers.tasks.whatsapp_inbox.process_wa_inbound_message",
)
def process_wa_inbound_message(
    self: Task,
    *,
    provider_message_id: str,
    from_address: str,
    text_body: str,
    context_id: str | None,
    contact_name: str | None,
    timestamp: str | None,
    request_id: str,
) -> dict:
    """Persist a single WhatsApp inbound text message to inbox_messages.

    Idempotent: Redis NX + DB unique constraint together guarantee exactly-once
    persistence even when Meta retries the webhook or the task is retried after
    a transient failure.

    Args:
        provider_message_id: Meta wamid of the inbound message.
        from_address: Sender's E.164 phone number.
        text_body: Plain text body (max 500 chars stored as encrypted snippet).
        context_id: wamid of the outbound we sent that this message replies to.
                    None for fresh conversations (Sprint 17B phone-lookup path).
        contact_name: Display name from Meta contacts[] array, if present.
        timestamp: Unix epoch string from Meta webhook; falls back to now().
        request_id: Correlation ID from the originating HTTP request.
    """
    task_key = f"wa:inbound:{provider_message_id}"
    try:
        return asyncio.run(
            _persist_wa_inbound(
                provider_message_id=provider_message_id,
                from_address=from_address,
                text_body=text_body,
                context_id=context_id,
                contact_name=contact_name,
                timestamp=timestamp,
                request_id=request_id,
                task_key=task_key,
            )
        )
    except SoftTimeLimitExceeded:
        log.warning(
            "wa_inbox.inbound.soft_timeout",
            provider_message_id=provider_message_id,
        )
        raise self.retry(countdown=30) from None
    except Exception as exc:
        log.error(
            "wa_inbox.inbound.error",
            provider_message_id=provider_message_id,
            error=str(exc),
        )
        raise self.retry(exc=exc) from exc


async def _persist_wa_inbound(
    *,
    provider_message_id: str,
    from_address: str,
    text_body: str,
    context_id: str | None,
    contact_name: str | None,
    timestamp: str | None,
    request_id: str,
    task_key: str,
) -> dict:
    """Async core: Redis dedup → tenant resolution → persistence → classification."""
    # ── Step 1: Redis inbound replay guard ────────────────────────────────────
    # fail-open on Redis outage — the DB unique constraint is the backstop.
    try:
        r = _redis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            was_new = r.set(task_key, "1", ex=_INBOUND_DEDUP_TTL, nx=True)
            if not was_new:
                log.info(
                    "wa_inbox.inbound.replay_skip",
                    provider_message_id=provider_message_id,
                )
                return {"status": "duplicate", "provider_message_id": provider_message_id}
        finally:
            r.close()
    except Exception as exc:
        log.warning("wa_inbox.inbound.redis_guard_error", error=str(exc))

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    try:
        # ── Step 2: Tenant resolution ─────────────────────────────────────────
        if context_id:
            resolved = await _resolve_via_context_id(factory, context_id)
            if resolved is None:
                log.info(
                    "wa_inbox.inbound.outbound_not_found",
                    provider_message_id=provider_message_id,
                    context_id=context_id,
                )
                return {
                    "status": "skipped",
                    "provider_message_id": provider_message_id,
                    "reason": "outbound_not_found",
                }
            outbound_message_id, tenant_id, workspace_id = resolved
            contact_id_override: uuid.UUID | None = None
            workspace_id_override: uuid.UUID | None = None
        else:
            # Fresh conversation — no context.id from Meta.
            resolved_fresh = await _resolve_via_phone(factory, from_address)
            if resolved_fresh is None:
                log.info(
                    "wa_inbox.inbound.phone_not_resolved",
                    provider_message_id=provider_message_id,
                    from_address=from_address,
                )
                return {
                    "status": "skipped",
                    "provider_message_id": provider_message_id,
                    "reason": "unknown_phone",
                }
            if resolved_fresh == "ambiguous":
                log.info(
                    "wa_inbox.inbound.phone_ambiguous",
                    provider_message_id=provider_message_id,
                    from_address=from_address,
                )
                return {
                    "status": "skipped",
                    "provider_message_id": provider_message_id,
                    "reason": "ambiguous_phone",
                }
            contact_id_fresh, tenant_id, workspace_id = resolved_fresh
            outbound_message_id = None
            contact_id_override = contact_id_fresh
            workspace_id_override = workspace_id

        # ── Step 3: Set tenant context + RLS ─────────────────────────────────
        ctx = TenantContext(
            org_id=tenant_id,
            workspace_id=workspace_id,
            user_id=uuid.UUID(int=0),
            role="system",
            request_id=request_id,
        )
        token = set_tenant_context(ctx)
        try:
            async with factory() as session:
                await set_rls_tenant(session, tenant_id)

                # ── Step 4: Parse received_at from Meta Unix timestamp ────────
                if timestamp:
                    try:
                        received_at = datetime.fromtimestamp(int(timestamp), tz=UTC)
                    except (ValueError, OSError):
                        received_at = datetime.now(UTC)
                else:
                    received_at = datetime.now(UTC)

                # ── Step 5: Get or create WA InboxConnection ─────────────────
                svc = InboxService(session)
                connection_id = await svc.get_or_create_wa_connection(workspace_id)

                # ── Step 6: Build and persist InboxMessage ───────────────────
                snippet: str | None = text_body[:500] if text_body else None
                msg = InboxMessage(
                    connection_id=connection_id,
                    channel="whatsapp",
                    provider_message_id=provider_message_id,
                    from_address=from_address,
                    subject=None,
                    received_at=received_at,
                    body_truncated=len(text_body) > 500 if text_body else False,
                    outbound_message_id=outbound_message_id,
                    match_method="provider_message_id" if outbound_message_id else "phone_lookup",
                )

                was_inserted, msg_out = await svc.create_if_not_exists(msg, body_snippet=snippet)

                if was_inserted:
                    log.info(
                        "wa_inbox.inbound.persisted",
                        provider_message_id=provider_message_id,
                        tenant_id=str(tenant_id),
                        workspace_id=str(workspace_id),
                        outbound_message_id=str(outbound_message_id) if outbound_message_id else None,
                        contact_name=contact_name,
                        request_id=request_id,
                    )

                    # ── Step 7: Best-effort classify + CRM automation ─────────
                    await _classify_wa_and_persist(
                        service=svc,
                        session=session,
                        message_id=msg_out.id,
                        outbound_message_id=outbound_message_id,
                        body_snippet=snippet,
                        from_address=from_address,
                        tenant_uuid=tenant_id,
                        request_id=request_id,
                        contact_id_override=contact_id_override,
                        workspace_id_override=workspace_id_override,
                    )

                    return {
                        "status": "created",
                        "provider_message_id": provider_message_id,
                    }

                log.info(
                    "wa_inbox.inbound.already_exists",
                    provider_message_id=provider_message_id,
                )
                return {
                    "status": "duplicate",
                    "provider_message_id": provider_message_id,
                }
        finally:
            clear_tenant_context(token)
    finally:
        await engine.dispose()


# ── Tenant resolution helpers ─────────────────────────────────────────────────

async def _resolve_via_context_id(
    factory: async_sessionmaker,
    context_id: str,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID] | None:
    """Return (outbound_message_id, tenant_id, workspace_id) or None.

    Cross-tenant query (no RLS GUC) — provider_message_id is globally unique
    (Meta wamid), so there is at most one row across all tenants.
    """
    async with factory() as session:
        row = await session.execute(
            text(
                "SELECT id, tenant_id, workspace_id FROM outbound_messages"
                " WHERE provider_message_id = :pid LIMIT 1"
            ),
            {"pid": context_id},
        )
        result = row.one_or_none()

    if result is None:
        return None
    return result[0], result[1], result[2]


async def _resolve_via_phone(
    factory: async_sessionmaker,
    from_address: str,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID] | Literal["ambiguous"] | None:
    """Resolve a fresh-conversation phone number to (contact_id, tenant_id, workspace_id).

    Returns:
        tuple  — single unambiguous match
        "ambiguous" — phone exists in multiple tenants; skip
        None   — phone not found; skip

    Uses LIMIT 2 to detect ambiguity without scanning every tenant.  Workspace
    is taken from the most recent campaign the contact was in.  A contact with
    no campaign history cannot be routed, so we skip rather than guess.
    """
    async with factory() as session:
        rows = await session.execute(
            text(
                "SELECT id, tenant_id FROM hr_contacts"
                " WHERE phone_e164 = :phone AND is_contactable = true"
                " LIMIT 2"
            ),
            {"phone": from_address},
        )
        contacts = rows.all()

    if len(contacts) == 0:
        return None
    if len(contacts) > 1:
        return "ambiguous"

    contact_id: uuid.UUID = contacts[0][0]
    tenant_id: uuid.UUID = contacts[0][1]

    # Derive workspace from most recent campaign this contact was in.
    async with factory() as session:
        ws_row = await session.execute(
            text(
                "SELECT c.workspace_id FROM campaign_recipients cr"
                " JOIN campaigns c ON c.id = cr.campaign_id"
                " WHERE cr.hr_contact_id = :cid"
                " ORDER BY c.created_at DESC LIMIT 1"
            ),
            {"cid": str(contact_id)},
        )
        ws_result = ws_row.one_or_none()

    if ws_result is None:
        log.info(
            "wa_inbox.inbound.phone_no_campaign",
            contact_id=str(contact_id),
        )
        return None

    workspace_id: uuid.UUID = ws_result[0]
    return contact_id, tenant_id, workspace_id


# ── Classification + automation helpers ──────────────────────────────────────

async def _classify_wa_and_persist(
    *,
    service,
    session,
    message_id: uuid.UUID,
    outbound_message_id: uuid.UUID | None,
    body_snippet: str | None,
    from_address: str,
    tenant_uuid: uuid.UUID,
    request_id: str,
    contact_id_override: uuid.UUID | None,
    workspace_id_override: uuid.UUID | None,
) -> None:
    """Run ReplyClassifierAgent (WA prompt) and persist the result.

    Mirrors inbox.py::_classify_and_persist() but:
      - Uses prompt_name="inbox.classify_wa_reply" (no subject field for WA).
      - Passes contact_id_override / workspace_id_override to CRM automation
        for fresh conversations that have no outbound_message_id.

    Failure policy: swallowed — persistence has already succeeded.  A failed
    classification leaves reply_intent=NULL; the message is re-classifiable later.
    """
    from corpmind.agents.reply_classifier import ReplyClassifierAgent
    from corpmind.ai.euri_client import EuriClient
    from corpmind.modules.inbox.events import (
        ReplyClassificationFailed,
        ReplyClassified,
    )

    try:
        agent = ReplyClassifierAgent(EuriClient(session=session))
        result = await agent.classify(
            subject=None,
            body_snippet=body_snippet,
            from_address=from_address,
            campaign_context=None,
            tenant_id=tenant_uuid,
            request_id=request_id,
            prompt_name=_WA_CLASSIFY_PROMPT,
        )
    except Exception as exc:
        reason = _categorize_classifier_error(exc)
        log.warning(
            "wa_inbox.classify.failed",
            message_id=str(message_id),
            tenant_id=str(tenant_uuid),
            reason=reason,
            error=str(exc)[:200],
        )
        log.info(
            "event.wa_reply.classification_failed",
            inbox_message_id=str(message_id),
            tenant_id=str(tenant_uuid),
            error=reason,
        )
        return

    await service.update_classification(
        message_id,
        intent=result.intent,
        confidence=result.confidence,
        model_name=result.model_name,
    )

    if not (result.intent == "unknown" and result.confidence < 0.5):
        await _run_wa_reply_automation(
            session=session,
            inbox_message_id=message_id,
            tenant_id=tenant_uuid,
            intent=result.intent,
            outbound_message_id=outbound_message_id,
            contact_id_override=contact_id_override,
            workspace_id_override=workspace_id_override,
        )

    if result.intent == "unknown" and result.confidence < 0.5:
        log.info(
            "event.wa_reply.classification_failed",
            inbox_message_id=str(message_id),
            tenant_id=str(tenant_uuid),
            error="malformed_output",
        )
        return

    log.info(
        "event.wa_reply.classified",
        inbox_message_id=str(message_id),
        tenant_id=str(tenant_uuid),
        intent=result.intent,
        confidence=round(result.confidence, 3),
        model_name=result.model_name,
        outbound_message_id=str(outbound_message_id) if outbound_message_id else None,
    )


async def _run_wa_reply_automation(
    *,
    session,
    inbox_message_id: uuid.UUID,
    tenant_id: uuid.UUID,
    intent: str,
    outbound_message_id: uuid.UUID | None,
    contact_id_override: uuid.UUID | None,
    workspace_id_override: uuid.UUID | None,
) -> None:
    """Drive ReplyAutomationService for a classified WA reply.

    For fresh conversations (outbound_message_id=None), contact_id_override and
    workspace_id_override carry the phone-lookup result so the automation service
    can still write the Activity and advance the lead.

    Best-effort: exceptions are swallowed so classification persistence is never
    rolled back.  Idempotency is enforced inside the service.
    """
    from corpmind.modules.crm.automation import ReplyAutomationService

    try:
        svc = ReplyAutomationService(session)
        result = await svc.handle_classified(
            inbox_message_id=inbox_message_id,
            tenant_id=tenant_id,
            intent=intent,
            outbound_message_id=outbound_message_id,
            contact_id_override=contact_id_override,
            workspace_id_override=workspace_id_override,
        )
        log.info(
            "wa_inbox.automation.complete",
            inbox_message_id=str(inbox_message_id),
            intent=intent,
            outcome=result.outcome,
            reason=result.reason,
        )
    except Exception as exc:
        log.error(
            "wa_inbox.automation.error",
            inbox_message_id=str(inbox_message_id),
            intent=intent,
            error=str(exc)[:200],
        )


def _categorize_classifier_error(exc: Exception) -> str:
    name = type(exc).__name__
    if name == "BudgetExceededError":
        return "budget_exceeded"
    if name == "ModelUnavailableError":
        return "models_unavailable"
    if name == "RateLimitError":
        return "rate_limited"
    return "internal_error"
