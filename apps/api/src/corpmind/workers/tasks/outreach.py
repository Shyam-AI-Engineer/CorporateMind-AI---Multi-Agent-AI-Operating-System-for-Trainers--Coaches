"""Outreach Celery tasks — send pipelines."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta, timezone

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
    in_reply_to: str | None = None,
) -> dict:
    """Send a single outbound message via the appropriate channel adapter.

    Idempotency: a Redis key keyed by message_id prevents duplicate sends even
    if the task is re-queued after a worker crash between send and ack.

    `in_reply_to` (Sprint 8B): optional threading anchor (the original outbound's
    smtp_message_id) for follow-up sends.  Default None keeps cold sends identical.
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
                    in_reply_to=in_reply_to,
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


# ── Follow-up cadence (Sprint 8B — ADR-0008) ────────────────────────────────────

# Feature flags (default OFF — flags.is_enabled returns False until set).
FLAG_CADENCE = "outreach.followup.cadence"      # kill switch for the whole cadence
FLAG_AUTO_SEND = "outreach.followup.auto_send"  # gate OoO auto-send vs. park-all

_FOLLOWUP_BATCH_LIMIT = 50          # per-tenant tasks processed per run
_FOLLOWUP_MAX_ATTEMPTS = 5          # claim ceiling → poison rows are cancelled
_FOLLOWUP_LOCK_TTL = 600            # Redis dispatch-guard TTL (seconds)
_QUIET_START_HOUR = 8               # local send window opens 08:00
_QUIET_END_HOUR = 21               # local send window closes 21:00
_TRAINING_WHEELS_DAYS = 7           # week-1 tenants: park everything
_STUCK_PROCESSING_SECONDS = 600     # reaper threshold (≥ task time_limit)


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
def advance_followup_cadence(self: Task) -> dict:
    """Sweep active orgs and fan out one follow-up subtask per tenant.

    Kill switch: gated by the FLAG_CADENCE feature flag (default OFF) — when
    disabled this is a no-op, so flipping the flag pauses all autonomous
    follow-up sends at the next beat (ADR-0008 §12 rollback).

    Cross-tenant sweep WITHOUT BYPASSRLS (ADR-0008 §8 amendment): reads the
    RLS-exempt `orgs` table to enumerate active tenants, then enqueues one
    RLS-scoped `process_tenant_followups` per tenant.  Each subtask self-skips
    when it has no due tasks.  Org.created_at is passed through so the subtask
    can compute the training-wheels signal without re-querying.
    """
    from corpmind.core.flags import is_enabled

    if not is_enabled(FLAG_CADENCE):
        log.info("outreach.cadence.disabled")
        return {"status": "disabled", "orgs_scanned": 0, "subtasks_queued": 0}

    log.info("outreach.cadence.start")
    try:
        return asyncio.run(_run_cadence_fan_out())
    except SoftTimeLimitExceeded:
        log.warning("outreach.cadence.soft_timeout")
        raise self.retry(countdown=60)
    except Exception as exc:
        log.error("outreach.cadence.error", error=str(exc))
        raise self.retry(exc=exc)


@app.task(
    bind=True,
    acks_late=True,
    max_retries=2,
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
    soft_time_limit=270,
    time_limit=300,
    queue="outreach",
    name="corpmind.workers.tasks.outreach.process_tenant_followups",
)
def process_tenant_followups(
    self: Task,
    *,
    tenant_id: str,
    org_created_at: str,
) -> dict:
    """Process due follow-up tasks for a single tenant (RLS-scoped).

    Per task: reap stuck rows → claim (atomic) → quiet-hours gate → hydrate
    context → generate draft → eligibility (auto-send OoO vs. park) → terminal
    transition.  Questions are NEVER auto-sent in 8B (parked for the 8C HITL UI).
    """
    try:
        return asyncio.run(
            _run_process_tenant(tenant_id=tenant_id, org_created_at=org_created_at)
        )
    except SoftTimeLimitExceeded:
        log.warning("outreach.cadence.tenant_soft_timeout", tenant_id=tenant_id)
        raise self.retry(countdown=30)
    except Exception as exc:
        log.error("outreach.cadence.tenant_error", tenant_id=tenant_id, error=str(exc))
        raise self.retry(exc=exc)


# ── Async implementation ───────────────────────────────────────────────────────

async def _run_send(
    *,
    message_id: str,
    tenant_id: str,
    channel: str,
    request_id: str,
    in_reply_to: str | None = None,
) -> dict:
    """Fetch the message, run compliance, dispatch via channel adapter."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from sqlalchemy import text

    from ulid import ULID

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

            # ── Resolve recipient address by channel ──────────────────────────
            if channel == "email":
                # Write-before-send: generate smtp_message_id once and persist it
                # before any network I/O.  On retry the existing value is reused so
                # the same Message-ID header is sent (idempotency).
                if msg.smtp_message_id is None:
                    smtp_message_id = f"<{ULID()}@{settings.MAIL_DOMAIN}>"
                    await repo.set_smtp_message_id(msg_uuid, smtp_message_id)
                    await session.commit()
                    log.info(
                        "outreach.send.smtp_message_id_generated",
                        message_id=message_id,
                        smtp_message_id=smtp_message_id,
                    )
                else:
                    smtp_message_id = msg.smtp_message_id
                    log.info(
                        "outreach.send.smtp_message_id_reused",
                        message_id=message_id,
                        smtp_message_id=smtp_message_id,
                    )
                result = await session.execute(
                    text(
                        "SELECT email FROM hr_contacts"
                        " WHERE id = :cid AND tenant_id = :tid"
                    ),
                    {"cid": str(msg.contact_id), "tid": str(tenant_uuid)},
                )
                row = result.one_or_none()
                recipient_address = row[0] if row else None
                if not recipient_address:
                    await repo.update_status(msg_uuid, "blocked")
                    await session.commit()
                    log.warning("outreach.send.no_email", message_id=message_id)
                    return {"status": "blocked", "message_id": message_id, "reason": "no_email"}
                smtp_message_id_val: str | None = smtp_message_id
            else:
                # WhatsApp (and future channels): use phone_e164 as recipient.
                result = await session.execute(
                    text(
                        "SELECT phone_e164 FROM hr_contacts"
                        " WHERE id = :cid AND tenant_id = :tid"
                    ),
                    {"cid": str(msg.contact_id), "tid": str(tenant_uuid)},
                )
                row = result.one_or_none()
                recipient_address = row[0] if row else None
                if not recipient_address:
                    await repo.update_status(msg_uuid, "blocked")
                    await session.commit()
                    log.warning("outreach.send.no_phone_e164", message_id=message_id)
                    return {"status": "blocked", "message_id": message_id, "reason": "no_phone_e164"}
                smtp_message_id_val = None

            rhash = recipient_hmac(recipient_address, tenant_uuid)
            comp_req = ComplianceCheckRequest(
                contact_id=msg.contact_id,
                channel=msg.channel,
                content_hash=_content_hash(msg.contact_id, msg.channel),
                campaign_id=msg.campaign_id,
                recipient_hash=rhash,
            )
            compliance = ComplianceService(session)
            checks = [
                compliance.check_opt_in,
                compliance.check_frequency_cap,
                compliance.check_unsubscribe,
            ]
            if channel == "whatsapp":
                checks.append(compliance.check_whatsapp_opt_in)
            for check_fn in checks:
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

            # Dispatch via channel adapter (registry resolves by channel name).
            send_metadata: dict = {}
            if channel == "email":
                send_metadata["smtp_message_id"] = smtp_message_id_val
                if in_reply_to:
                    send_metadata["in_reply_to"] = in_reply_to
                    send_metadata["references"] = in_reply_to
            elif channel == "whatsapp":
                # Template name stored in prompt_version (e.g. "outreach_intro_v1").
                # Template params are empty for Sprint 16A static templates.
                send_metadata["template_language"] = "en"
                send_metadata["template_params"] = []
            channel_msg = ChannelMessage(
                message_id=message_id,
                recipient_id=str(msg.contact_id),
                recipient_address=recipient_address,
                channel=channel,
                subject=msg.subject,
                body=msg.body,
                template_id=msg.prompt_version if channel == "whatsapp" else None,
                tenant_id=tenant_id,
                request_id=request_id,
                metadata=send_metadata,
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
                # Increment outreach send counter for billing/tier enforcement.
                from sqlalchemy import select as sa_select
                from corpmind.modules.billing.models import Subscription
                from corpmind.modules.billing.repo import UsageMeterRepo

                sub_row = await session.execute(
                    sa_select(Subscription).where(
                        Subscription.tenant_id == tenant_uuid,
                        Subscription.status == "active",
                    )
                )
                subscription = sub_row.scalar_one_or_none()
                if subscription is not None:
                    await UsageMeterRepo(session).increment_outreach_sends(subscription.id)

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
    from corpmind.channels.registry import get as registry_get

    return registry_get(channel)


# ── Follow-up cadence async implementation (Sprint 8B) ──────────────────────────

async def _run_cadence_fan_out() -> dict:
    """Enumerate active orgs (RLS-exempt) and enqueue one subtask per tenant.

    No BYPASSRLS: `orgs` has no RLS policy, so it is readable with the app role
    and no app.tenant_id GUC.  Org.created_at rides along to the subtask so the
    training-wheels check needs no extra query (ADR-0008 §8 amendment).
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from corpmind.core.config import settings

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    orgs_scanned = 0
    subtasks_queued = 0
    try:
        async with factory() as session:
            result = await session.execute(
                text("SELECT id, created_at FROM orgs WHERE is_active = true")
            )
            rows = result.all()

        orgs_scanned = len(rows)
        for org_id, created_at in rows:
            process_tenant_followups.apply_async(
                kwargs={
                    "tenant_id": str(org_id),
                    "org_created_at": created_at.isoformat(),
                },
                queue="outreach",
            )
            subtasks_queued += 1
    finally:
        await engine.dispose()

    log.info(
        "outreach.cadence.fan_out_complete",
        orgs_scanned=orgs_scanned,
        subtasks_queued=subtasks_queued,
    )
    return {
        "status": "ok",
        "orgs_scanned": orgs_scanned,
        "subtasks_queued": subtasks_queued,
    }


async def _run_process_tenant(*, tenant_id: str, org_created_at: str) -> dict:
    """Process this tenant's due follow-up tasks, RLS-scoped."""
    from datetime import timedelta

    import redis as _redis
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from corpmind.core.config import settings
    from corpmind.core.database import set_rls_tenant
    from corpmind.core.flags import is_enabled
    from corpmind.core.tenancy import (
        TenantContext,
        clear_tenant_context,
        set_tenant_context,
    )
    from corpmind.modules.crm.repo import FollowUpTaskRepo

    tenant_uuid = uuid.UUID(tenant_id)
    created_at = datetime.fromisoformat(org_created_at)
    now_utc = datetime.now(UTC)
    is_training_wheels = (now_utc - created_at) < timedelta(days=_TRAINING_WHEELS_DAYS)
    auto_send_enabled = is_enabled(FLAG_AUTO_SEND, tenant=tenant_uuid)

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    r = _redis.from_url(settings.REDIS_URL, decode_responses=True)

    # Org-level context for repo/reaper calls (org_id is what every filter uses).
    base_ctx = TenantContext(
        org_id=tenant_uuid,
        workspace_id=tenant_uuid,
        user_id=tenant_uuid,
        role="system",
        request_id=str(uuid.uuid4()),
    )
    base_token = set_tenant_context(base_ctx)

    counts = {"due": 0, "sent": 0, "parked": 0, "cancelled": 0, "deferred": 0, "skipped": 0}
    try:
        async with factory() as session:
            await set_rls_tenant(session, tenant_uuid)
            repo = FollowUpTaskRepo(session)

            # Reaper: reclaim rows stuck in 'processing' past the time limit.
            cutoff = now_utc - timedelta(seconds=_STUCK_PROCESSING_SECONDS)
            reset = await repo.reset_stuck_processing(older_than=cutoff)
            if reset:
                await session.commit()
                log.info("outreach.cadence.reaped", tenant_id=tenant_id, reset=reset)

            due = await repo.list_due(limit=_FOLLOWUP_BATCH_LIMIT)
            counts["due"] = len(due)
            if not due:
                return {"status": "no_due", "tenant_id": tenant_id, **counts}

            for task in due:
                lock_key = f"followup:processing:{task.id}"
                if not r.set(lock_key, "1", ex=_FOLLOWUP_LOCK_TTL, nx=True):
                    counts["skipped"] += 1
                    continue
                try:
                    await _process_one(
                        session=session,
                        repo=repo,
                        task=task,
                        tenant_uuid=tenant_uuid,
                        base_ctx=base_ctx,
                        now_utc=now_utc,
                        is_training_wheels=is_training_wheels,
                        auto_send_enabled=auto_send_enabled,
                        counts=counts,
                    )
                except Exception as exc:
                    # Leave the row in 'processing' — the reaper reclaims it next
                    # run and attempts++ will eventually retire a poison row.
                    log.error(
                        "outreach.cadence.task_error",
                        tenant_id=tenant_id,
                        task_id=str(task.id),
                        error=str(exc)[:200],
                    )
                finally:
                    r.delete(lock_key)
    finally:
        clear_tenant_context(base_token)
        await engine.dispose()
        r.close()

    log.info("outreach.cadence.tenant_complete", tenant_id=tenant_id, **counts)
    return {"status": "ok", "tenant_id": tenant_id, **counts}


async def _process_one(
    *,
    session,
    repo,
    task,
    tenant_uuid: uuid.UUID,
    base_ctx,
    now_utc: datetime,
    is_training_wheels: bool,
    auto_send_enabled: bool,
    counts: dict,
) -> None:
    """Claim → quiet-hours → generate → eligibility → terminal, for one task."""
    from corpmind.core.tenancy import (
        TenantContext,
        clear_tenant_context,
        set_tenant_context,
    )
    from corpmind.modules.inbox.service import InboxService
    from corpmind.modules.outreach.schemas import GenerateFollowupRequest
    from corpmind.modules.outreach.service import OutreachService

    # ── Atomic claim — commit immediately so the 'processing' state is visible
    #    and no row lock is held across the LLM call (ADR-0008 §8).
    claimed = await repo.claim(task.id)
    await session.commit()
    if not claimed:
        counts["skipped"] += 1
        return

    # Poison-row ceiling (attempts was just incremented by claim).
    if task.attempts + 1 > _FOLLOWUP_MAX_ATTEMPTS:
        await repo.mark_cancelled(task.id, reason="max_attempts_exceeded")
        await session.commit()
        counts["cancelled"] += 1
        return

    # ── Quiet hours — defer (no LLM spend) if outside the recipient window.
    tz_name = await _resolve_workspace_timezone(session, task.workspace_id)
    if not _within_quiet_hours(tz_name, now_utc):
        next_start = _next_window_start_utc(tz_name, now_utc)
        await repo.defer(task.id, scheduled_for=next_start)
        await session.commit()
        counts["deferred"] += 1
        return

    # ── Hydrate context.
    original = await _hydrate_original_outbound(session, task.source_outbound_message_id)
    lead_stage = await _lead_stage(session, task.lead_id)
    reply_text: str | None = None
    try:
        reply_text = await InboxService(session).get_decrypted_snippet(
            task.source_inbox_message_id
        )
    except Exception:
        reply_text = None  # source message gone / unreadable — non-fatal
    days_since = max((now_utc - task.created_at).days, 0) if task.created_at else 0

    # Workspace-scoped context for the trainer-profile lookup inside generate/send.
    task_ctx = TenantContext(
        org_id=tenant_uuid,
        workspace_id=task.workspace_id,
        user_id=tenant_uuid,
        role="system",
        request_id=base_ctx.request_id,
    )

    req = GenerateFollowupRequest(
        contact_id=task.contact_id,
        task_type=task.type,
        reply_text=reply_text,
        original_subject=(original or {}).get("subject"),
        original_body=(original or {}).get("body"),
        lead_stage=lead_stage,
        days_since=days_since,
        campaign_id=None,
    )

    from corpmind.core.exceptions import NotFoundError, OptInRequiredError

    task_token = set_tenant_context(task_ctx)
    try:
        try:
            draft = await OutreachService(session).generate_followup(req)  # commits draft
        except (OptInRequiredError, NotFoundError) as exc:
            # Permanent conditions (contact opted out / gone) — cancel now rather
            # than burn the attempts ceiling. No partial write precedes these
            # (opt-in + contact checks run before any DB write in generate_followup).
            reason = "opt_in" if isinstance(exc, OptInRequiredError) else "contact_not_found"
            await repo.mark_cancelled(task.id, reason=reason)
            await session.commit()
            counts["cancelled"] += 1
            return
        draft_id = draft.message.id

        # ── Eligibility (ADR-0008 §5).  Questions NEVER auto-send in 8B.
        auto_ok = (
            task.type == "out_of_office_followup"
            and auto_send_enabled
            and not is_training_wheels
            and not draft.needs_human_review
        )
        if auto_ok:
            in_reply_to = (original or {}).get("smtp_message_id")
            resp = await OutreachService(session).send_message(
                draft_id, in_reply_to=in_reply_to
            )
            if resp.status == "blocked":
                await repo.mark_cancelled(
                    task.id, reason=f"compliance:{resp.compliance_reason or 'blocked'}"
                )
                await session.commit()
                counts["cancelled"] += 1
            else:
                await repo.mark_done(task.id, result_outbound_message_id=draft_id)
                await session.commit()
                await _write_followup_activity(session, task, draft_id, "followup_sent")
                await session.commit()
                counts["sent"] += 1
        else:
            await repo.mark_awaiting_approval(
                task.id, result_outbound_message_id=draft_id
            )
            await session.commit()
            await _write_followup_activity(session, task, draft_id, "followup_drafted")
            await session.commit()
            counts["parked"] += 1
    finally:
        clear_tenant_context(task_token)


# ── Cadence helpers ─────────────────────────────────────────────────────────────

_IST = timezone(timedelta(hours=5, minutes=30))  # fallback when tz data unavailable


def _zone(tz_name: str):
    """Resolve a timezone, falling back to a fixed IST offset.

    Worker hosts (Linux) have tz data; the fixed-offset fallback keeps the
    quiet-hours logic deterministic on hosts without the tzdata package and for
    a malformed Workspace.timezone value.
    """
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(tz_name)
    except Exception:
        return _IST


def _within_quiet_hours(tz_name: str, now_utc: datetime) -> bool:
    """True when recipient-local time is inside [08:00, 21:00)."""
    local = now_utc.astimezone(_zone(tz_name))
    return _QUIET_START_HOUR <= local.hour < _QUIET_END_HOUR


def _next_window_start_utc(tz_name: str, now_utc: datetime) -> datetime:
    """Next local 08:00 (today if before the window, else tomorrow), as UTC."""
    from datetime import timedelta

    tz = _zone(tz_name)
    local = now_utc.astimezone(tz)
    target = local.replace(
        hour=_QUIET_START_HOUR, minute=0, second=0, microsecond=0
    )
    if local.hour >= _QUIET_END_HOUR:
        target = target + timedelta(days=1)
    elif local.hour >= _QUIET_START_HOUR:
        # Inside the window — shouldn't be called, but be safe: schedule now.
        target = local
    return target.astimezone(UTC)


async def _resolve_workspace_timezone(session, workspace_id: uuid.UUID) -> str:
    """Read Workspace.timezone (RLS-exempt table); fall back to Asia/Kolkata."""
    from sqlalchemy import text

    result = await session.execute(
        text("SELECT timezone FROM workspaces WHERE id = :wsid"),
        {"wsid": str(workspace_id)},
    )
    row = result.one_or_none()
    return row[0] if row and row[0] else "Asia/Kolkata"


async def _hydrate_original_outbound(session, outbound_id: uuid.UUID | None) -> dict | None:
    """Fetch the original outbound's subject/body/smtp_message_id for threading."""
    if outbound_id is None:
        return None
    from sqlalchemy import text

    from corpmind.core.tenancy import get_tenant_context

    ctx = get_tenant_context()
    result = await session.execute(
        text(
            "SELECT subject, body, smtp_message_id FROM outbound_messages"
            " WHERE id = :oid AND tenant_id = :tid"
        ),
        {"oid": str(outbound_id), "tid": str(ctx.org_id)},
    )
    row = result.one_or_none()
    if row is None:
        return None
    return {"subject": row[0], "body": row[1], "smtp_message_id": row[2]}


async def _lead_stage(session, lead_id: uuid.UUID | None) -> str | None:
    """Fetch the lead's current stage (RLS-scoped)."""
    if lead_id is None:
        return None
    from sqlalchemy import text

    from corpmind.core.tenancy import get_tenant_context

    ctx = get_tenant_context()
    result = await session.execute(
        text("SELECT stage FROM leads WHERE id = :lid AND tenant_id = :tid"),
        {"lid": str(lead_id), "tid": str(ctx.org_id)},
    )
    row = result.one_or_none()
    return row[0] if row else None


async def _write_followup_activity(
    session, task, draft_id: uuid.UUID, activity_type: str
) -> None:
    """Append a crm_activities row so the timeline reflects the follow-up action."""
    from corpmind.core.tenancy import get_tenant_context
    from corpmind.modules.crm.models import Activity
    from corpmind.modules.crm.repo import ActivityRepo

    ctx = get_tenant_context()
    summary = (
        "Follow-up sent automatically."
        if activity_type == "followup_sent"
        else "Follow-up drafted; awaiting approval."
    )
    await ActivityRepo(session).create(
        Activity(
            tenant_id=ctx.org_id,
            workspace_id=task.workspace_id,
            lead_id=task.lead_id,
            contact_id=task.contact_id,
            type=activity_type,
            summary=summary,
            source_inbox_message_id=task.source_inbox_message_id,
            source_outbound_message_id=draft_id,
        )
    )
