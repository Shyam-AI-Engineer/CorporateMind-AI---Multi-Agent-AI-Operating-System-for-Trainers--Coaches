"""HITL (Human-In-The-Loop) gate logic.

All HITL trigger conditions live here so they're auditable in one place.
The RootOrchestrator calls should_require_hitl() after planning.
"""

from __future__ import annotations

from corpmind.agents.state import AgentState


def should_require_hitl(state: AgentState) -> bool:
    """Return True if the planned action requires human approval before execution.

    Triggers (from langgraph-agents.md):
    - Recipient count > 200
    - Enterprise-tier outreach
    - ComplianceGuardAgent flags content
    - Sensitive-content classifier triggers
    - First-week-of-tenant mode is active
    """
    recipient_count = len(state.get("qualified_contact_ids", []))
    if recipient_count > 200:
        return True

    plan_tier = state.get("tenant_id", "")  # TODO: pull from TenantContext
    if plan_tier == "enterprise":
        return True

    if state.get("compliance_outcome") in ("hitl_required", "blocked"):
        return True

    return False
