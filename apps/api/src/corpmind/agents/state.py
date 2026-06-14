"""Shared AgentState TypedDict — the ONLY state object passed between LangGraph nodes.

Rules:
- Every new field needs: (a) default value, (b) schema_version bump, (c) checkpoint migration.
- Sub-agents communicate ONLY via this state, never directly.
- schema_version must be bumped on any field addition or type change.
"""

from __future__ import annotations

import uuid
from typing import Any, TypedDict


SCHEMA_VERSION = 3


class PlanStep(TypedDict):
    tool: str
    inputs: dict[str, Any]
    expected_output_schema: dict[str, Any]
    status: str  # pending | running | done | failed
    result: Any | None


class Plan(TypedDict):
    steps: list[PlanStep]
    current_step_index: int
    created_at: str  # ISO 8601


class AgentState(TypedDict, total=False):
    """Shared state for all LangGraph agent nodes in CorporateMind AI.

    Fields are optional (total=False) so nodes can be composed without
    requiring all fields to be pre-populated.
    """

    # ── Schema versioning (required for checkpoint resumption) ────────────────
    schema_version: int  # default: SCHEMA_VERSION

    # ── Request correlation ────────────────────────────────────────────────────
    request_id: str
    run_id: str
    tenant_id: str          # UUID as string
    workspace_id: str       # UUID as string
    user_id: str            # UUID as string

    # ── Intent (set by RootOrchestrator) ─────────────────────────────────────
    intent: str             # outreach | discovery | proposal | social | analytics
    intent_confidence: float
    user_goal: str          # natural-language description from user

    # ── Planning (Planner node output) ────────────────────────────────────────
    plan: Plan | None
    plan_rationale: str     # why this plan was chosen

    # ── Trainer profile context ───────────────────────────────────────────────
    trainer_profile_id: str | None
    trainer_niche: str | None
    trainer_tone: str | None
    trainer_topics: list[str]
    trainer_context: dict[str, Any]   # full SQL trainer profile dict; authoritative
    trainer_qdrant_score: float       # top-1 cosine score from Qdrant; 0.0 if unavailable

    # ── Per-recipient outreach context ────────────────────────────────────────
    contact_id: str | None            # single recipient UUID for OutreachAgent runs
    contact_context: dict[str, Any]   # full SQL contact dict from _fetch_contact

    # ── HR discovery context ──────────────────────────────────────────────────
    target_industries: list[str]
    target_employee_ranges: list[str]
    discovered_company_ids: list[str]   # companies matched in _discover_companies
    discovered_contact_ids: list[str]
    qualified_contact_ids: list[str]
    qualify_score_threshold: int        # minimum score (1–10) a contact must reach; default 5

    # ── Outreach context ──────────────────────────────────────────────────────
    campaign_id: str | None
    channel: str | None
    outreach_message_ids: list[str]
    ab_variants: list[str]

    # ── Compliance ───────────────────────────────────────────────────────────
    compliance_checked: bool
    compliance_outcome: str | None  # allowed | blocked | hitl_required
    compliance_reason: str | None
    compliance_audit_id: str | None

    # ── HITL ─────────────────────────────────────────────────────────────────
    hitl_required: bool
    hitl_reason: str | None
    hitl_approved_by: str | None
    hitl_approved_at: str | None

    # ── Proposal context ──────────────────────────────────────────────────────
    proposal_id: str | None
    proposal_contact_id: str | None

    # ── Cost tracking ─────────────────────────────────────────────────────────
    total_tokens_in: int
    total_tokens_out: int
    total_cost_inr: float

    # ── Errors / retries ─────────────────────────────────────────────────────
    error: str | None
    retry_count: int
    last_node: str | None   # for resumption and debugging

    # ── Output ───────────────────────────────────────────────────────────────
    final_output: dict[str, Any] | None
    status: str             # running | paused_hitl | completed | failed


def default_state(
    *,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    request_id: str,
    run_id: str,
) -> AgentState:
    """Return a properly initialized AgentState with all defaults set."""
    return AgentState(
        schema_version=SCHEMA_VERSION,
        request_id=request_id,
        run_id=run_id,
        tenant_id=str(tenant_id),
        workspace_id=str(workspace_id),
        user_id=str(user_id),
        intent="",
        intent_confidence=0.0,
        user_goal="",
        plan=None,
        plan_rationale="",
        trainer_profile_id=None,
        trainer_niche=None,
        trainer_tone=None,
        trainer_topics=[],
        trainer_context={},
        trainer_qdrant_score=0.0,
        contact_id=None,
        contact_context={},
        target_industries=[],
        target_employee_ranges=[],
        discovered_company_ids=[],
        discovered_contact_ids=[],
        qualified_contact_ids=[],
        qualify_score_threshold=5,
        campaign_id=None,
        channel=None,
        outreach_message_ids=[],
        ab_variants=[],
        compliance_checked=False,
        compliance_outcome=None,
        compliance_reason=None,
        compliance_audit_id=None,
        hitl_required=False,
        hitl_reason=None,
        hitl_approved_by=None,
        hitl_approved_at=None,
        proposal_id=None,
        proposal_contact_id=None,
        total_tokens_in=0,
        total_tokens_out=0,
        total_cost_inr=0.0,
        error=None,
        retry_count=0,
        last_node=None,
        final_output=None,
        status="running",
    )
