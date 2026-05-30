"""Campaign Celery tasks — batch send pipeline."""

from __future__ import annotations

import asyncio
import uuid

import structlog
from celery import Task
from celery.exceptions import SoftTimeLimitExceeded

from corpmind.workers.celery_app import app

log = structlog.get_logger(__name__)


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
    name="corpmind.workers.tasks.campaigns.launch_campaign",
)
def launch_campaign(
    self: Task,
    *,
    campaign_id: str,
    tenant_id: str,
    workspace_id: str,
    channel: str,
    request_id: str,
) -> dict:
    """Generate outreach messages for all pending recipients and enqueue sends.

    Idempotent: only processes recipients with status='pending'.  Safe to
    re-enqueue after a pause or a worker crash — already-queued recipients
    are skipped automatically.
    """
    try:
        return asyncio.run(
            _run_launch(
                campaign_id=campaign_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                channel=channel,
                request_id=request_id,
            )
        )
    except SoftTimeLimitExceeded:
        log.warning("campaign.launch.soft_timeout", campaign_id=campaign_id)
        raise self.retry(countdown=30)
    except Exception as exc:
        log.error("campaign.launch.error", campaign_id=campaign_id, error=str(exc))
        raise self.retry(exc=exc)


# ── Async implementation ───────────────────────────────────────────────────────

async def _run_launch(
    *,
    campaign_id: str,
    tenant_id: str,
    workspace_id: str,
    channel: str,
    request_id: str,
) -> dict:
    """For each pending recipient: generate copy + enqueue send task."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

    from corpmind.core.config import settings
    from corpmind.core.database import set_rls_tenant
    from corpmind.core.exceptions import (
        ComplianceBlockError,
        FrequencyCapExceededError,
        OptInRequiredError,
        UnsubscribedError,
    )
    from corpmind.core.tenancy import TenantContext, set_tenant_context, clear_tenant_context
    from corpmind.modules.campaigns.models import Campaign
    from corpmind.modules.campaigns.repo import CampaignRepo, CampaignRecipientRepo
    from corpmind.modules.outreach.schemas import GenerateOutreachRequest
    from corpmind.modules.outreach.service import OutreachService

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    campaign_uuid = uuid.UUID(campaign_id)
    tenant_uuid = uuid.UUID(tenant_id)
    workspace_uuid = uuid.UUID(workspace_id)

    ctx = TenantContext(
        org_id=tenant_uuid,
        workspace_id=workspace_uuid,
        user_id=tenant_uuid,
        role="system",
        request_id=request_id,
    )
    token = set_tenant_context(ctx)

    sent = 0
    blocked = 0
    failed = 0

    try:
        async with factory() as session:
            await set_rls_tenant(session, tenant_uuid)

            c_repo = CampaignRepo(session)
            r_repo = CampaignRecipientRepo(session)
            outreach_svc = OutreachService(session)

            campaign = await c_repo.find_by_id(campaign_uuid)
            if campaign is None or campaign.status not in ("running",):
                log.warning(
                    "campaign.launch.skipped",
                    campaign_id=campaign_id,
                    reason="not found or not running",
                )
                return {"status": "skipped", "campaign_id": campaign_id}

            # Fetch all pending recipients in batches of 100.
            offset = 0
            batch_size = 100
            while True:
                recipients = await r_repo.list_by_campaign(
                    campaign_uuid,
                    status="pending",
                    limit=batch_size,
                    offset=offset,
                )
                if not recipients:
                    break

                for recipient in recipients:
                    try:
                        gen_req = GenerateOutreachRequest(
                            contact_id=recipient.contact_id,
                            channel=channel,
                            campaign_id=campaign_uuid,
                        )
                        outbound = await outreach_svc.generate_message(gen_req)

                        # Mark recipient as queued and store the message link.
                        await r_repo.update_recipient(
                            recipient.id,
                            status="queued",
                            message_id=str(outbound.id),
                        )

                        # send_message() re-runs compliance checks; it returns
                        # status="blocked" instead of raising when the guard fires.
                        send_resp = await outreach_svc.send_message(outbound.id)
                        if send_resp.status == "blocked":
                            await r_repo.update_recipient(recipient.id, status="blocked")
                            blocked += 1
                        else:
                            sent += 1

                    except (
                        ComplianceBlockError,
                        FrequencyCapExceededError,
                        OptInRequiredError,
                        UnsubscribedError,
                    ) as exc:
                        log.warning(
                            "campaign.recipient.compliance_blocked",
                            campaign_id=campaign_id,
                            contact_id=str(recipient.contact_id),
                            reason=str(exc),
                        )
                        await r_repo.update_recipient(recipient.id, status="blocked")
                        blocked += 1

                    except Exception as exc:  # noqa: BLE001
                        log.error(
                            "campaign.recipient.generation_failed",
                            campaign_id=campaign_id,
                            contact_id=str(recipient.contact_id),
                            error=str(exc),
                        )
                        await r_repo.update_recipient(
                            recipient.id, status="failed"
                        )
                        failed += 1

                await session.commit()
                offset += batch_size

            # Mark campaign completed — all send tasks are now enqueued.
            await c_repo.update_status(campaign_uuid, "completed")
            await session.commit()

            log.info(
                "campaign.launch.completed",
                campaign_id=campaign_id,
                sent=sent,
                blocked=blocked,
                failed=failed,
            )
            return {
                "status": "completed",
                "campaign_id": campaign_id,
                "sent": sent,
                "blocked": blocked,
                "failed": failed,
            }
    finally:
        clear_tenant_context(token)
        await engine.dispose()
