"""Outreach service — message generation and send orchestration.

Phase 1 surface
───────────────
• generate_message() — personalize email copy via EuriClient, save as draft.
• send_message()     — run full compliance gate + enqueue Celery send task.
• get_message()      — fetch a single message for the current tenant.

Cross-module data access
────────────────────────
hr_contacts and trainer_profiles are read via raw text() SQL queries.
We never import ORM models from hr_discovery or trainer_intel — this upholds
the cross-module boundary rule (no repo/model imports across modules).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.ai.euri_client import EuriClient
from corpmind.core.exceptions import (
    ConflictError,
    NotFoundError,
    OptInRequiredError,
    ValidationError,
)
from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.compliance.schemas import (
    ComplianceCheckRequest,
    ComplianceOutcome,
)
from corpmind.modules.compliance.service import ComplianceService
from corpmind.modules.outreach.models import OutboundMessage
from corpmind.modules.outreach.repo import OutboundMessageRepo
from corpmind.modules.outreach.schemas import (
    FollowupDraftOut,
    GenerateFollowupRequest,
    GenerateOutreachRequest,
    OutboundMessageListOut,
    OutboundMessageOut,
    SendMessageResponse,
)

log = structlog.get_logger(__name__)

_SUPPORTED_CHANNELS = frozenset({"email"})

# Follow-up task type → (routing task class, prompt name). Premium tier; see
# ADR-0008 §4 and routing.py.  Both prompts are non-cacheable (euri-gateway.md).
_FOLLOWUP_ROUTING: dict[str, tuple[str, str]] = {
    "question_followup": ("followup_question", "outreach.followup.question"),
    "out_of_office_followup": ("followup_nudge", "outreach.followup.nudge"),
}


class OutreachService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = OutboundMessageRepo(session)
        self._compliance = ComplianceService(session)
        self._llm = EuriClient(session=session)

    # ── Public API ────────────────────────────────────────────────────────────

    async def generate_message(self, req: GenerateOutreachRequest) -> OutboundMessageOut:
        """Personalize outreach copy and save as a draft message.

        Runs opt-in check before the LLM call to avoid spending AI budget on
        contacts that would be blocked anyway.
        """
        if req.channel not in _SUPPORTED_CHANNELS:
            raise ValidationError(
                f"Channel '{req.channel}' is not yet supported. "
                f"Available: {', '.join(sorted(_SUPPORTED_CHANNELS))}"
            )

        ctx = get_tenant_context()

        contact = await self._fetch_contact(req.contact_id, ctx.org_id)
        if contact is None:
            raise NotFoundError(f"Contact {req.contact_id} not found")

        # Fail fast on opt-in before the LLM call.
        comp_req = _build_compliance_req(req.contact_id, req.channel, req.campaign_id, contact, ctx.org_id)
        opt_in = await self._compliance.check_opt_in(comp_req)
        if opt_in.outcome == ComplianceOutcome.BLOCKED:
            raise OptInRequiredError(opt_in.reason or "Contact has not opted in for outreach.")

        trainer = await self._fetch_trainer_profile(ctx.workspace_id, ctx.org_id)

        result = await self._llm.chat(
            task="outreach_copy",
            prompt_name="outreach.email",
            prompt_inputs=_build_prompt_inputs(contact, trainer),
            tenant_id=ctx.org_id,
            request_id=ctx.request_id,
            agent="outreach_service",
        )
        copy = self._parse_copy(result["content"])

        msg = OutboundMessage(
            tenant_id=ctx.org_id,
            campaign_id=req.campaign_id,
            contact_id=req.contact_id,
            channel=req.channel,
            subject=copy.get("subject"),
            body=copy["body"],
            prompt_version="outreach.email.v1",
            ab_variant=req.ab_variant,
            status="draft",
        )
        await self._repo.create(msg)
        await self._session.commit()
        log.info(
            "outreach.draft_created",
            message_id=str(msg.id),
            contact_id=str(req.contact_id),
            channel=req.channel,
        )
        return OutboundMessageOut.model_validate(msg)

    async def generate_followup(self, req: GenerateFollowupRequest) -> FollowupDraftOut:
        """Generate a context-aware follow-up draft (ADR-0008, Sprint 8A).

        Mirrors the structure of generate_message() but selects a follow-up
        prompt by task type and surfaces a HITL signal on the return DTO.  The
        cold-outreach path (generate_message / _parse_copy) is deliberately left
        untouched — this is a sibling method, not a branch through the cold flow.

        Sprint 8A is GENERATION ONLY: this persists a draft OutboundMessage and
        returns it.  It does NOT send, transition status, schedule, or enqueue
        anything — that is Sprint 8B.  ComplianceGuard still runs in full at send
        time; here we only fail-fast on opt-in to avoid spending premium AI
        budget on a contact that would be blocked anyway (same as generate_message).

        needs_human_review is returned, never stored — keeping 8A migration-free.
        For question follow-ups it fails safe to True when the model could not
        answer from trainer-profile facts.
        """
        routing = _FOLLOWUP_ROUTING.get(req.task_type)
        if routing is None:
            # Defensive: the schema pattern already constrains task_type, but a
            # caller using model_construct() could bypass validation.
            raise ValidationError(f"Unknown follow-up task type '{req.task_type}'")
        task, prompt_name = routing

        ctx = get_tenant_context()

        contact = await self._fetch_contact(req.contact_id, ctx.org_id)
        if contact is None:
            raise NotFoundError(f"Contact {req.contact_id} not found")

        # Fail fast on opt-in before the premium LLM call.
        comp_req = _build_compliance_req(
            req.contact_id, "email", req.campaign_id, contact, ctx.org_id
        )
        opt_in = await self._compliance.check_opt_in(comp_req)
        if opt_in.outcome == ComplianceOutcome.BLOCKED:
            raise OptInRequiredError(
                opt_in.reason or "Contact has not opted in for outreach."
            )

        trainer = await self._fetch_trainer_profile(ctx.workspace_id, ctx.org_id)

        result = await self._llm.chat(
            task=task,
            prompt_name=prompt_name,
            prompt_inputs=_build_followup_inputs(req, contact, trainer),
            tenant_id=ctx.org_id,
            request_id=ctx.request_id,
            agent="outreach_followup_service",
        )
        parsed = self._parse_followup(result["content"], req.task_type)

        msg = OutboundMessage(
            tenant_id=ctx.org_id,
            campaign_id=req.campaign_id,
            contact_id=req.contact_id,
            channel="email",
            subject=parsed["subject"],
            body=parsed["body"],
            prompt_version=f"{prompt_name}.v1",
            ab_variant=None,
            status="draft",
        )
        await self._repo.create(msg)
        await self._session.commit()
        log.info(
            "outreach.followup_draft_created",
            message_id=str(msg.id),
            contact_id=str(req.contact_id),
            task_type=req.task_type,
            needs_human_review=parsed["needs_human_review"],
            answered=parsed["answered"],
        )
        return FollowupDraftOut(
            message=OutboundMessageOut.model_validate(msg),
            task_type=req.task_type,
            needs_human_review=parsed["needs_human_review"],
            answered=parsed["answered"],
        )

    async def send_message(self, message_id: uuid.UUID) -> SendMessageResponse:
        """Run full compliance gate and enqueue the Celery send task.

        The Celery task re-runs compliance checks immediately before dispatch —
        conditions (unsubscribe, frequency cap) may change between draft creation
        and the actual send.
        """
        ctx = get_tenant_context()
        msg = await self._repo.find_by_id(message_id)
        if msg is None:
            raise NotFoundError(f"Message {message_id} not found")
        if msg.status != "draft":
            raise ConflictError(f"Message is already {msg.status}")

        contact = await self._fetch_contact(msg.contact_id, ctx.org_id)
        if contact is None:
            raise NotFoundError(f"Contact {msg.contact_id} not found")

        comp_req = _build_compliance_req(
            msg.contact_id, msg.channel, msg.campaign_id, contact, ctx.org_id
        )
        for check_fn in (
            self._compliance.check_opt_in,
            self._compliance.check_frequency_cap,
            self._compliance.check_unsubscribe,
        ):
            result = await check_fn(comp_req)
            if result.outcome == ComplianceOutcome.BLOCKED:
                await self._repo.update_status(message_id, "blocked")
                await self._session.commit()
                log.warning(
                    "outreach.send_blocked",
                    message_id=str(message_id),
                    blocked_by=result.blocked_by,
                )
                return SendMessageResponse(
                    message_id=message_id,
                    status="blocked",
                    compliance_reason=result.reason,
                )

        await self._repo.update_status(message_id, "queued")
        await self._session.commit()

        # Imported here to avoid circular import at module load time.
        from corpmind.workers.tasks.outreach import send_message as send_task  # noqa: PLC0415

        send_task.apply_async(
            kwargs={
                "message_id": str(message_id),
                "tenant_id": str(ctx.org_id),
                "channel": msg.channel,
                "request_id": ctx.request_id,
            }
        )
        log.info("outreach.enqueued", message_id=str(message_id), channel=msg.channel)
        return SendMessageResponse(message_id=message_id, status="queued")

    async def get_message(self, message_id: uuid.UUID) -> OutboundMessageOut:
        msg = await self._repo.find_by_id(message_id)
        if msg is None:
            raise NotFoundError(f"Message {message_id} not found")
        return OutboundMessageOut.model_validate(msg)

    async def list_messages_by_campaign(
        self,
        campaign_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> OutboundMessageListOut:
        items = await self._repo.list_by_campaign(campaign_id, limit=limit, offset=offset)
        total = await self._repo.count_by_campaign(campaign_id)
        return OutboundMessageListOut(
            items=[OutboundMessageOut.model_validate(m) for m in items],
            total=total,
            limit=limit,
            offset=offset,
        )

    # ── Data fetching (raw SQL — no cross-module ORM model imports) ───────────

    async def _fetch_contact(
        self, contact_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> dict | None:
        result = await self._session.execute(
            text(
                "SELECT hc.id, hc.full_name, hc.title, hc.email, hc.is_contactable,"
                "       hc.preferred_language, c.name AS company_name, c.industry"
                " FROM hr_contacts hc"
                " LEFT JOIN companies c"
                "   ON c.id = hc.company_id AND c.tenant_id = :tid"
                " WHERE hc.id = :cid AND hc.tenant_id = :tid"
            ),
            {"cid": str(contact_id), "tid": str(tenant_id)},
        )
        row = result.mappings().one_or_none()
        return dict(row) if row else None

    async def _fetch_trainer_profile(
        self, workspace_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> dict:
        result = await self._session.execute(
            text(
                "SELECT niche, topics, tone, pricing_min_inr, pricing_max_inr,"
                "       bio, usp, target_industries"
                " FROM trainer_profiles"
                " WHERE workspace_id = :wsid AND tenant_id = :tid"
                " ORDER BY locked_at DESC NULLS LAST"
                " LIMIT 1"
            ),
            {"wsid": str(workspace_id), "tid": str(tenant_id)},
        )
        row = result.mappings().one_or_none()
        return dict(row) if row else {}

    # ── Parsing ───────────────────────────────────────────────────────────────

    def _parse_copy(self, raw: str) -> dict:
        stripped = raw.strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`")
            if stripped.startswith("json"):
                stripped = stripped[4:].lstrip()
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"Outreach copy returned non-JSON: {exc}") from exc
        if not data.get("body"):
            raise ValidationError("Outreach copy missing required 'body' field")
        return data

    def _parse_followup(self, raw: str, task_type: str) -> dict:
        """Parse a follow-up LLM response into {subject, body, needs_human_review, answered}.

        Self-contained on purpose — it does NOT reuse _parse_copy so the cold
        outreach parser stays byte-identical.  JSON-fence stripping mirrors
        _parse_copy.  Behaviour differs by task type:

          out_of_office_followup (nudge): requires a non-empty body; never needs
            review; answered is None (no question to answer).

          question_followup: fails safe.  needs_human_review defaults to True when
            the flag is missing/unparseable, and is forced True whenever the model
            reports answered=false (could not answer from profile facts) — this is
            the correctness-over-speed gate from ADR-0008 §5.  An empty body is
            tolerated (the human will write the answer) but still routes to review.
        """
        stripped = raw.strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`")
            if stripped.startswith("json"):
                stripped = stripped[4:].lstrip()
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"Follow-up copy returned non-JSON: {exc}") from exc

        subject = data.get("subject") or ""
        body = data.get("body")

        if task_type == "out_of_office_followup":
            if not body:
                raise ValidationError("Nudge follow-up missing required 'body' field")
            return {
                "subject": subject,
                "body": body,
                "needs_human_review": False,
                "answered": None,
            }

        # question_followup — fail-safe to human review.
        answered = bool(data.get("answered", False))
        review_raw = data.get("needs_human_review")
        needs_review = True if review_raw is None else bool(review_raw)
        if not answered:
            needs_review = True
        return {
            "subject": subject,
            "body": body if body is not None else "",
            "needs_human_review": needs_review,
            "answered": answered,
        }


# ── Module-level helpers ───────────────────────────────────────────────────────

def recipient_hmac(email: str | None, tenant_id: uuid.UUID) -> str | None:
    """HMAC-SHA256(email, org_id) — per-tenant hash, safe for audit/unsubscribe lookups."""
    if not email:
        return None
    key = str(tenant_id).encode()
    return hmac.new(key, email.encode(), hashlib.sha256).hexdigest()


def _content_hash(contact_id: uuid.UUID, channel: str) -> str:
    return hashlib.sha256(f"{contact_id}:{channel}".encode()).hexdigest()


def _build_compliance_req(
    contact_id: uuid.UUID,
    channel: str,
    campaign_id: uuid.UUID | None,
    contact: dict,
    tenant_id: uuid.UUID,
) -> ComplianceCheckRequest:
    return ComplianceCheckRequest(
        contact_id=contact_id,
        channel=channel,
        content_hash=_content_hash(contact_id, channel),
        campaign_id=campaign_id,
        recipient_hash=recipient_hmac(contact.get("email"), tenant_id),
    )


def _format_pricing(trainer: dict) -> str:
    lo = trainer.get("pricing_min_inr")
    hi = trainer.get("pricing_max_inr")
    if lo and hi:
        return f"₹{lo:,.0f} – ₹{hi:,.0f}"
    if lo:
        return f"from ₹{lo:,.0f}"
    return "on request"


def _build_prompt_inputs(contact: dict, trainer: dict) -> dict:
    topics = trainer.get("topics") or []
    industries = trainer.get("target_industries") or []
    return {
        "trainer_niche": trainer.get("niche") or "Corporate Training",
        "trainer_topics": ", ".join(topics) if isinstance(topics, list) else str(topics),
        "trainer_usp": trainer.get("usp") or "",
        "trainer_bio": trainer.get("bio") or "",
        "trainer_pricing": _format_pricing(trainer),
        "trainer_tone": trainer.get("tone") or "semi_formal",
        "trainer_industries": (
            ", ".join(industries) if isinstance(industries, list) else str(industries)
        ),
        "contact_name": contact.get("full_name") or "HR Professional",
        "contact_title": contact.get("title") or "HR Manager",
        "contact_company": contact.get("company_name") or "your organisation",
        "contact_industry": contact.get("industry") or "",
        "contact_language": contact.get("preferred_language") or "en",
    }


def _build_followup_inputs(
    req: GenerateFollowupRequest, contact: dict, trainer: dict
) -> dict:
    """Build prompt inputs for a follow-up: the trainer/contact block plus the
    reply/original-email context.

    Reuses _build_prompt_inputs for the trainer/contact fields (so the two paths
    can never drift on profile rendering), then adds follow-up-specific keys.
    Every key the followup prompts reference MUST be present here — the registry
    uses str.format_map and sends the prompt UNRENDERED if a key is missing.
    Optional context falls back to explicit placeholders so the model is told the
    field is unavailable rather than seeing a literal "{original_body}".
    """
    inputs = _build_prompt_inputs(contact, trainer)
    inputs.update(
        {
            "reply_text": req.reply_text or "(no reply text available)",
            "original_subject": req.original_subject or "(original subject unavailable)",
            "original_body": req.original_body or "(original email body unavailable)",
            "lead_stage": req.lead_stage or "unknown",
            "days_since": str(req.days_since) if req.days_since is not None else "a few",
        }
    )
    return inputs
