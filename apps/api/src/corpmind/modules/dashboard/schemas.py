"""Dashboard schemas — Sprint 28 Business Health Center.

All schemas are read-only view models; no mutations, no persistence.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class ComponentScore(BaseModel):
    """One weighted component of the overall health score."""

    name: str
    score: float        # 0–100
    weight: float       # proportion (0–1) of overall score


class OperationalAlert(BaseModel):
    """A deterministic operational flag derived from metric thresholds."""

    priority: str       # critical | warning | info
    category: str       # pipeline | revenue | campaign | recommendation | communication
    title: str
    description: str
    recommended_action: str
    created_at: datetime


class BusinessHealthOut(BaseModel):
    """Response for GET /dashboard/business-health."""

    generated_at: datetime
    overall_score: float          # 0–100 weighted aggregate
    pipeline_score: float
    revenue_score: float
    campaign_score: float
    recommendation_score: float
    communication_score: float
    components: list[ComponentScore]
    top_alerts: list[OperationalAlert]
    top_strengths: list[str]
    areas_needing_attention: list[str]
    health_trend: str             # improving | stable | declining


class OperationalAlertsOut(BaseModel):
    """Response for GET /dashboard/operational-alerts."""

    alerts: list[OperationalAlert]
    total: int


class BusinessSummaryOut(BaseModel):
    """Response for GET /dashboard/business-summary."""

    generated_at: datetime
    lines: list[str]
    overall_assessment: str       # excellent | good | fair | poor
