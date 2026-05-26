"""Outreach Celery tasks — send pipelines."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import redis
import structlog
from celery import Task
from celery.exceptions import SoftTimeLimitExceeded

from corpmind.workers.celery_app import app

log = structlog.get_logger(__name__)


@app.task(
    bind=True,
    acks_late=True,
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
    soft_time_limit=60,
    time_limit=90,
    queue="outreach",
    name="corpmind.workers.tasks.outreach.send_message",
)
def send_message(
    self: Task,
    *,
    message_id: str,
    tenant_id: str,
    channel: str,
    request_id: str,
) -> dict:
    """Send a single outbound message via the appropriate channel adapter.

    Idempotency: a Redis key keyed by message_id prevents duplicate sends even
    if the task is re-queued after a worker crash between send and ack.
    """
    from corpmind.core.config import settings

    task_key = f"outreach:sent:{message_id}"
    r = redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        if r.get(task_key):
            log.info("outreach.send.idempotent_skip", task_key=task_key)
            return {"status": "already_sent", "message_id": message_id}

        try:
            result = asyncio.run(
                _run_send(
                    message_id=message_id,
                    tenant_id=tenant_id,
                    channel=channel,
                    request_id=request_id,
                )
            )
        except SoftTimeLimitExceeded:
            log.warning("outreach.send.soft_timeout", message_id=message_id)
            raise self.retry(countdown=30)
        except Exception as exc:
            log.error("outreach.send.error", message_id=message_id, error=str(exc))
            raise self.retry(exc=exc)

        if result.get("status") == "sent":
            r.setex(task_key, 86400 * 7, "1")  # keep for 7 days

        return result
    finally:
        r.close()


@app.task(
    bind=True,
    acks_late=True,
    max_retries=2,
    retry_backoff=True,
    soft_time_limit=270,
    time_limit=300,
    queue="outreach",
    name="corpmind.workers.tasks.outreach.advance_followup_cadence",
)
def advance_followup_cadence(self: Task) -> None:
    """Advance follow-up sequences for all due messages across tenants."""
    log.info("outreach.cadence.start")
    # TODO(Phase 1): query due follow-ups, enqueue send_message for each


# ── Async implementation ───────────────────────────────────────────────────────

async def _run_send(
    *,
    message_id: str,
    tenant_id: str,
    channel: str,
    request_id: str,
) -> dict:
    """Fetch the message, run compliance, dispatch via channel adapter."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from sqlalchemy import text

    from corpmind.channels.email_smtp import EmailSMTPAdapter
    from corpmind.channels.base import OutboundMessage as ChannelMessage
    from corpmind.core.config import settings
    from corpmind.core.database import set_rls_tenant
    from corpmind.core.tenancy import TenantContext, set_tenant_context, clear_tenant_context
    from corpmind.modules.compliance.schemas import ComplianceCheckRequest, ComplianceOutcome
    from corpmind.modules.compliance.service import ComplianceService
    from corpmind.modules.compliance.models import AuditEvent
    from corpmind.modules.compliance.repo import AuditRepo
    from corpmind.modules.outreach.models import OutboundMessage
    from corpmind.modules.outreach.repo import OutboundMessageRepo
    from corpmind.modules.outreach.service import recipient_hmac, _content_hash

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    msg_uuid = uuid.UUID(message_id)
    tenant_uuid = uuid.UUID(tenant_id)

    ctx = TenantContext(
        org_id=tenant_uuid,
        workspace_id=tenant_uuid,  # task doesn't have workspace_id; tenant-level ops are safe
        user_id=tenant_uuid,
        role="system",
        request_id=request_id,
    )
    token = set_tenant_context(ctx)

    try:
        async with factory() as session:
            await set_rls_tenant(session, tenant_uuid)

            repo = OutboundMessageRepo(session)
            msg = await repo.find_by_id(msg_uuid)
            if msg is None or msg.status not in ("queued",):
                log.warning(
                    "outreach.send.skipped",
                    message_id=message_id,
                    reason="not found or not queued",
                )
                return {"status": "skipped", "message_id": message_id}

            # Fetch contact email for compliance + channel dispatch.
            result = await session.execute(
                text(
                    "SELECT email FROM hr_contacts"
                    " WHERE id = :cid AND tenant_id = :tid"
                ),
                {"cid": str(msg.contact_id), "tid": str(tenant_uuid)},
            )
            contact_row = result.one_or_none()
            contact_email = contact_row[0] if contact_row else None

            if not contact_email:
                await repo.update_status(msg_uuid, "blocked")
                await session.commit()
                log.warning("outreach.send.no_email", message_id=message_id)
                return {"status": "blocked", "message_id": message_id, "reason": "no_email"}

            rhash = recipient_hmac(contact_email, tenant_uuid)
            comp_req = ComplianceCheckRequest(
                contact_id=msg.contact_id,
                channel=msg.channel,
                content_hash=_content_hash(msg.contact_id, msg.channel),
                campaign_id=msg.campaign_id,
                recipient_hash=rhash,
            )
            compliance = ComplianceService(session)
            for check_fn in (
                compliance.check_opt_in,
                compliance.check_frequency_cap,
                compliance.check_unsubscribe,
            ):
                check_result = await check_fn(comp_req)
                if check_result.outcome == ComplianceOutcome.BLOCKED:
                    await repo.update_status(msg_uuid, "blocked")
                    await session.commit()
                    log.warning(
                        "outreach.send.compliance_block",
                        message_id=message_id,
                        blocked_by=check_result.blocked_by,
                    )
                    return {
                        "status": "blocked",
                        "message_id": message_id,
                        "reason": check_result.blocked_by,
                    }

            # Dispatch via channel adapter.
            channel_msg = ChannelMessage(
                message_id=message_id,
                recipient_id=str(msg.contact_id),
                recipient_address=contact_email,
                channel=channel,
                subject=msg.subject,
                body=msg.body,
                template_id=None,
                tenant_id=tenant_id,
                request_id=request_id,
                metadata={},
            )
            adapter = _get_adapter(channel)
            send_result = await adapter.send(channel_msg)

            if send_result.success:
                await repo.update_status(
                    msg_uuid,
                    "sent",
                    provider_message_id=send_result.provider_message_id,
                    sent_at=datetime.now(UTC),
                )
                # Write audit event so frequency-cap queries can count it.
                audit_repo = AuditRepo(session)
                await audit_repo.append(
                    AuditEvent(
                        tenant_id=tenant_uuid,
                        actor_type="system",
                        event_type="message.sent",
                        channel=channel,
                        recipient_hash=rhash,
                        content_hash=comp_req.content_hash,
                        outcome="allowed",
                        event_data={
                            "message_id": message_id,
                            "provider_message_id": send_result.provider_message_id,
                        },
                    )
                )
                await session.commit()
                log.info("outreach.send.success", message_id=message_id, channel=channel)
                return {
                    "status": "sent",
                    "message_id": message_id,
                    "provider_message_id": send_result.provider_message_id,
                }
            else:
                await repo.update_status(msg_uuid, "failed")
                await session.commit()
                log.error(
                    "outreach.send.provider_error",
                    message_id=message_id,
                    error_code=send_result.error_code,
                )
                raise RuntimeError(
                    f"Channel send failed [{send_result.error_code}]: {send_result.error_detail}"
                )
    finally:
        clear_tenant_context(token)
        await engine.dispose()


def _get_adapter(channel: str):
    from corpmind.channels.email_smtp import EmailSMTPAdapter

    if channel == "email":
        return EmailSMTPAdapter()
    raise ValueError(f"No adapter registered for channel: {channel!r}")
