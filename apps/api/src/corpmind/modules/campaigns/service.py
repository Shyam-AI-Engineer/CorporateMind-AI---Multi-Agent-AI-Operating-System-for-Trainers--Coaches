"""Campaign service — full lifecycle management.

State machine
─────────────
draft ──add_recipients/lock──► locked ──launch──► running ──► completed
                                                └──► pending_hitl (> 200 recipients)
running ──pause──► paused ──resume──► running
any-non-terminal ──cancel──► cancelled

Cross-module rule: contacts are read via raw SQL; we never import hr_discovery
ORM models.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.campaigns.models import Campaign
from corpmind.modules.campaigns.repo import CampaignRepo, CampaignRecipientRepo
from corpmind.modules.campaigns.schemas import (
    AddRecipientsRequest,
    AddRecipientsResponse,
    CampaignCreate,
    CampaignLaunchResponse,
    CampaignListOut,
    CampaignOut,
    CampaignRecipientOut,
)

log = structlog.get_logger(__name__)

_HITL_THRESHOLD = 200  # recipients above this require human approval before launch
_TERMINAL_STATUSES = frozenset({"completed", "cancelled", "rejected"})


class CampaignService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = CampaignRepo(session)
        self._recipient_repo = CampaignRecipientRepo(session)

    # ── Creation ──────────────────────────────────────────────────────────────

    async def create(self, req: CampaignCreate) -> CampaignOut:
        ctx = get_tenant_context()
        campaign = Campaign(
            tenant_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
            name=req.name,
            channel=req.channel,
            settings=req.settings,
            scheduled_at=req.scheduled_at,
            created_by=ctx.user_id,
        )
        await self._repo.create(campaign)
        await self._session.commit()
        log.info("campaign.draft_created", campaign_id=str(campaign.id))
        return CampaignOut.model_validate(campaign)

    # ── Read ──────────────────────────────────────────────────────────────────

    async def get(self, campaign_id: uuid.UUID) -> CampaignOut:
        campaign = await self._repo.find_by_id(campaign_id)
        if not campaign:
            raise NotFoundError(f"Campaign {campaign_id} not found")
        return CampaignOut.model_validate(campaign)

    async def list_for_workspace(
        self,
        workspace_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> CampaignListOut:
        campaigns = await self._repo.list_for_workspace(
            workspace_id, limit=limit, offset=offset
        )
        return CampaignListOut(
            items=[CampaignOut.model_validate(c) for c in campaigns],
            total=len(campaigns),
            limit=limit,
            offset=offset,
        )

    async def get_recipients(
        self,
        campaign_id: uuid.UUID,
        *,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[CampaignRecipientOut]:
        await self._require_campaign(campaign_id)
        recipients = await self._recipient_repo.list_by_campaign(
            campaign_id, status=status, limit=limit, offset=offset
        )
        return [CampaignRecipientOut.model_validate(r) for r in recipients]

    # ── Recipient management ──────────────────────────────────────────────────

    async def add_recipients(
        self, campaign_id: uuid.UUID, req: AddRecipientsRequest
    ) -> AddRecipientsResponse:
        campaign = await self._require_campaign(campaign_id)
        if campaign.status != "draft":
            raise ConflictError(
                f"Cannot add recipients to a campaign in status '{campaign.status}'. "
                "Campaign must be in 'draft'."
            )
        # Validate contacts exist and are contactable for this tenant.
        await self._validate_contacts(req.contact_ids)

        added = await self._recipient_repo.add_bulk(campaign_id, req.contact_ids)
        total = await self._recipient_repo.count_recipients(campaign_id)
        await self._session.commit()
        log.info(
            "campaign.recipients_added",
            campaign_id=str(campaign_id),
            added=added,
            total=total,
        )
        return AddRecipientsResponse(added_count=added, total_recipients=total)

    async def remove_recipient(
        self, campaign_id: uuid.UUID, contact_id: uuid.UUID
    ) -> None:
        campaign = await self._require_campaign(campaign_id)
        if campaign.status != "draft":
            raise ConflictError(
                f"Cannot remove recipients from a campaign in status '{campaign.status}'."
            )
        deleted = await self._recipient_repo.delete_recipient(campaign_id, contact_id)
        if not deleted:
            raise NotFoundError(
                f"Contact {contact_id} is not a recipient of campaign {campaign_id}"
            )
        await self._session.commit()

    # ── State transitions ─────────────────────────────────────────────────────

    async def lock(self, campaign_id: uuid.UUID) -> CampaignOut:
        """Freeze the recipient list. Required before launch."""
        campaign = await self._require_campaign(campaign_id)
        if campaign.status != "draft":
            raise ConflictError(
                f"Cannot lock a campaign in status '{campaign.status}'."
            )
        count = await self._recipient_repo.count_recipients(campaign_id)
        if count == 0:
            raise ValidationError("Cannot lock a campaign with no recipients.")
        await self._repo.update_fields(
            campaign_id, status="locked", recipient_count=count
        )
        await self._session.commit()
        log.info("campaign.locked", campaign_id=str(campaign_id), recipient_count=count)
        campaign.status = "locked"
        campaign.recipient_count = count
        return CampaignOut.model_validate(campaign)

    async def launch(self, campaign_id: uuid.UUID) -> CampaignLaunchResponse:
        """Run HITL gate and enqueue the send pipeline.

        If recipient_count > _HITL_THRESHOLD, transitions to pending_hitl and
        returns hitl_required=True.  The HITL approval endpoint later calls
        launch() again — at that point status is 'approved' which also passes
        this gate.
        """
        ctx = get_tenant_context()
        campaign = await self._require_campaign(campaign_id)
        if campaign.status not in ("locked", "approved"):
            raise ConflictError(
                f"Cannot launch a campaign in status '{campaign.status}'. "
                "Lock the campaign first."
            )

        count = campaign.recipient_count
        if count == 0:
            raise ValidationError("Campaign has no recipients.")

        if count > _HITL_THRESHOLD and campaign.status != "approved":
            await self._repo.update_status(campaign_id, "pending_hitl")
            await self._session.commit()
            log.info(
                "campaign.pending_hitl",
                campaign_id=str(campaign_id),
                recipient_count=count,
            )
            return CampaignLaunchResponse(
                campaign_id=campaign_id,
                status="pending_hitl",
                recipient_count=count,
                hitl_required=True,
            )

        await self._repo.update_status(campaign_id, "running")
        await self._session.commit()

        from corpmind.workers.tasks.campaigns import launch_campaign  # noqa: PLC0415

        launch_campaign.apply_async(
            kwargs={
                "campaign_id": str(campaign_id),
                "tenant_id": str(ctx.org_id),
                "workspace_id": str(ctx.workspace_id),
                "channel": campaign.channel,
                "request_id": ctx.request_id,
            }
        )
        log.info(
            "campaign.launched",
            campaign_id=str(campaign_id),
            recipient_count=count,
        )
        return CampaignLaunchResponse(
            campaign_id=campaign_id,
            status="running",
            recipient_count=count,
            hitl_required=False,
        )

    async def pause(self, campaign_id: uuid.UUID) -> None:
        campaign = await self._require_campaign(campaign_id)
        if campaign.status not in ("running", "approved"):
            raise ConflictError(
                f"Cannot pause a campaign in status '{campaign.status}'."
            )
        await self._repo.update_status(campaign_id, "paused")
        await self._session.commit()
        log.info("campaign.paused", campaign_id=str(campaign_id))

    async def resume(self, campaign_id: uuid.UUID) -> CampaignLaunchResponse:
        """Re-enqueue a paused campaign from where it left off."""
        ctx = get_tenant_context()
        campaign = await self._require_campaign(campaign_id)
        if campaign.status != "paused":
            raise ConflictError(
                f"Cannot resume a campaign in status '{campaign.status}'."
            )
        await self._repo.update_status(campaign_id, "running")
        await self._session.commit()

        from corpmind.workers.tasks.campaigns import launch_campaign  # noqa: PLC0415

        # Task will skip already-sent recipients (status != "pending").
        launch_campaign.apply_async(
            kwargs={
                "campaign_id": str(campaign_id),
                "tenant_id": str(ctx.org_id),
                "workspace_id": str(ctx.workspace_id),
                "channel": campaign.channel,
                "request_id": ctx.request_id,
            }
        )
        log.info("campaign.resumed", campaign_id=str(campaign_id))
        return CampaignLaunchResponse(
            campaign_id=campaign_id,
            status="running",
            recipient_count=campaign.recipient_count,
            hitl_required=False,
        )

    async def cancel(self, campaign_id: uuid.UUID) -> None:
        campaign = await self._require_campaign(campaign_id)
        if campaign.status in _TERMINAL_STATUSES:
            raise ConflictError(
                f"Campaign is already in terminal status '{campaign.status}'."
            )
        await self._repo.update_status(campaign_id, "cancelled")
        await self._session.commit()
        log.info("campaign.cancelled", campaign_id=str(campaign_id))

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _require_campaign(self, campaign_id: uuid.UUID) -> Campaign:
        campaign = await self._repo.find_by_id(campaign_id)
        if not campaign:
            raise NotFoundError(f"Campaign {campaign_id} not found")
        return campaign

    async def _validate_contacts(self, contact_ids: list[uuid.UUID]) -> None:
        """Verify all contacts exist and are contactable for the current tenant.

        Uses raw SQL to avoid importing hr_discovery ORM models (cross-module
        boundary rule).
        """
        ctx = get_tenant_context()
        if not contact_ids:
            return
        id_list = ", ".join(f"'{cid}'" for cid in contact_ids)
        result = await self._session.execute(
            text(
                f"SELECT id FROM hr_contacts"  # noqa: S608
                f" WHERE id IN ({id_list})"
                f"   AND tenant_id = :tid"
                f"   AND is_contactable = TRUE"
            ),
            {"tid": str(ctx.org_id)},
        )
        found_ids = {row[0] for row in result}
        missing = [cid for cid in contact_ids if str(cid) not in {str(f) for f in found_ids}]
        if missing:
            raise ValidationError(
                f"{len(missing)} contact(s) not found or not contactable: "
                + ", ".join(str(m) for m in missing[:5])
            )
