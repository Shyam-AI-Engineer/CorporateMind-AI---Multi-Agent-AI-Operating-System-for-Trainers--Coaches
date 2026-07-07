"""Executive Dashboard output schemas — Sprint 50.

Pure read-only. No writes. No AI. No LLM.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class ExecutiveKPIsOut(BaseModel):
    """All 10 executive KPIs scoped to the tenant workspace."""

    total_leads: int = Field(0, description="Total leads in the pipeline")
    active_customers: int = Field(0, description="Customers with status=active")
    renewals_due: int = Field(0, description="Renewals due within 30 days")
    training_completion_rate: float = Field(
        0.0, description="Completed engagements / total engagements (0–1)"
    )
    certificate_issuance_rate: float = Field(
        0.0, description="Issued certificates / eligible attendees (0–1)"
    )
    avg_feedback_rating: float | None = Field(
        None, description="Average overall_rating 1–5 across all sessions"
    )
    customer_health_distribution: dict[str, int] = Field(
        default_factory=dict, description="health_status → customer count"
    )
    workflow_completion_rate: float = Field(
        0.0, description="Completed workflow runs / total runs (0–1)"
    )
    open_operations_tasks: int = Field(
        0, description="Business tasks not in done/completed/cancelled"
    )
    business_health_score: int = Field(
        0, description="Composite deterministic score 0–100"
    )


class ExecutiveSummaryOut(BaseModel):
    """Top-level summary counts for the command-center header row."""

    total_leads: int = 0
    active_customers: int = 0
    renewals_due: int = 0
    open_operations_tasks: int = 0
    business_health_score: int = 0


class ExecutiveAlertOut(BaseModel):
    """Single actionable alert card surfaced to the executive dashboard."""

    alert_type: str
    severity: str  # critical | warning | info
    title: str
    description: str
    count: int
    affected_ids: list[str] = Field(default_factory=list)


class ExecutiveTrendOut(BaseModel):
    """One calendar-day data-point in a trend series."""

    date: str  # YYYY-MM-DD
    leads_created: int = 0
    customers_created: int = 0
    training_completions: int = 0
    renewals_processed: int = 0


class ExecutiveDashboardOut(BaseModel):
    """Full composite dashboard payload — all sections in a single response."""

    summary: ExecutiveSummaryOut
    kpis: ExecutiveKPIsOut
    alerts: list[ExecutiveAlertOut]
    trends_30d: list[ExecutiveTrendOut]
    workspace_id: str
    generated_at: str
