"""Executive Dashboard service — Sprint 50.

Pure read-only. No writes. No LLM. No Celery.
Redis TTL: 900 seconds (15 minutes).
asyncio.gather() used in get_dashboard() for concurrent repo fetches.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from corpmind.core.redis import get_redis
from corpmind.core.tenancy import get_tenant_context
from corpmind.modules.executive_dashboard.repo import (
    ExecutiveDashboardRepo,
    RawAlertData,
    RawKPIData,
)
from corpmind.modules.executive_dashboard.schemas import (
    ExecutiveAlertOut,
    ExecutiveDashboardOut,
    ExecutiveKPIsOut,
    ExecutiveSummaryOut,
    ExecutiveTrendOut,
)

log = structlog.get_logger(__name__)

_CACHE_TTL = 900  # 15 minutes
_VALID_TREND_DAYS = frozenset({30, 90, 365})


# ── Cache key helpers ──────────────────────────────────────────────────────────


def _dashboard_key(org_id: uuid.UUID, workspace_id: uuid.UUID) -> str:
    return f"exec_dashboard:{org_id}:{workspace_id}"


def _kpis_key(org_id: uuid.UUID, workspace_id: uuid.UUID) -> str:
    return f"exec_kpis:{org_id}:{workspace_id}"


def _alerts_key(org_id: uuid.UUID, workspace_id: uuid.UUID) -> str:
    return f"exec_alerts:{org_id}:{workspace_id}"


def _trends_key(org_id: uuid.UUID, workspace_id: uuid.UUID, days: int) -> str:
    return f"exec_trends:{org_id}:{workspace_id}:{days}"


# ── Pure deterministic helpers (no I/O) ───────────────────────────────────────


def compute_health_score(raw: RawKPIData) -> int:
    """Composite 0–100 score from KPI signals. Deterministic, no AI."""
    score = 50  # neutral baseline

    if raw.total_training_engagements > 0:
        rate = raw.completed_training_engagements / raw.total_training_engagements
        score += int(rate * 20)

    if raw.avg_feedback_rating is not None:
        score += int((raw.avg_feedback_rating / 5.0) * 20)

    total_customers = sum(raw.customer_health_distribution.values())
    if total_customers > 0:
        at_risk = raw.customer_health_distribution.get("at_risk", 0)
        if at_risk > 0:
            score -= int((at_risk / total_customers) * 20)

    if raw.total_workflow_runs > 0:
        wf_rate = raw.completed_workflow_runs / raw.total_workflow_runs
        score += int(wf_rate * 10)

    return max(0, min(100, score))


def build_kpis(raw: RawKPIData) -> ExecutiveKPIsOut:
    training_rate = (
        raw.completed_training_engagements / raw.total_training_engagements
        if raw.total_training_engagements > 0
        else 0.0
    )
    cert_rate = (
        raw.total_certificates_issued / raw.total_certificate_eligible
        if raw.total_certificate_eligible > 0
        else 0.0
    )
    wf_rate = (
        raw.completed_workflow_runs / raw.total_workflow_runs
        if raw.total_workflow_runs > 0
        else 0.0
    )
    avg_fb = (
        round(raw.avg_feedback_rating, 2) if raw.avg_feedback_rating is not None else None
    )
    return ExecutiveKPIsOut(
        total_leads=raw.total_leads,
        active_customers=raw.active_customers,
        renewals_due=raw.renewals_due,
        training_completion_rate=round(training_rate, 4),
        certificate_issuance_rate=round(cert_rate, 4),
        avg_feedback_rating=avg_fb,
        customer_health_distribution=raw.customer_health_distribution,
        workflow_completion_rate=round(wf_rate, 4),
        open_operations_tasks=raw.open_operations_tasks,
        business_health_score=compute_health_score(raw),
    )


def build_alerts(raw: RawAlertData) -> list[ExecutiveAlertOut]:
    alerts: list[ExecutiveAlertOut] = []

    if raw.renewals_overdue:
        alerts.append(
            ExecutiveAlertOut(
                alert_type="renewals_overdue",
                severity="critical",
                title="Renewals Overdue",
                description=(
                    f"{len(raw.renewals_overdue)} renewal(s) past their renewal "
                    "date with no action taken."
                ),
                count=len(raw.renewals_overdue),
                affected_ids=raw.renewals_overdue[:20],
            )
        )

    if raw.customers_at_risk_ids:
        alerts.append(
            ExecutiveAlertOut(
                alert_type="customers_at_risk",
                severity="critical",
                title="Customers At Risk",
                description=(
                    f"{len(raw.customers_at_risk_ids)} customer(s) flagged "
                    "as at-risk or high-risk."
                ),
                count=len(raw.customers_at_risk_ids),
                affected_ids=raw.customers_at_risk_ids[:20],
            )
        )

    if raw.training_overdue_ids:
        alerts.append(
            ExecutiveAlertOut(
                alert_type="training_overdue",
                severity="warning",
                title="Training Programs Overdue",
                description=(
                    f"{len(raw.training_overdue_ids)} training program(s) past "
                    "their planned end date."
                ),
                count=len(raw.training_overdue_ids),
                affected_ids=raw.training_overdue_ids[:20],
            )
        )

    if raw.workflow_backlog_ids:
        alerts.append(
            ExecutiveAlertOut(
                alert_type="workflow_backlog",
                severity="warning",
                title="Workflow Backlog",
                description=(
                    f"{len(raw.workflow_backlog_ids)} workflow run(s) have been "
                    "active for over 7 days."
                ),
                count=len(raw.workflow_backlog_ids),
                affected_ids=raw.workflow_backlog_ids[:20],
            )
        )

    if raw.operations_backlog_ids:
        alerts.append(
            ExecutiveAlertOut(
                alert_type="operations_backlog",
                severity="warning",
                title="Operations Tasks Overdue",
                description=(
                    f"{len(raw.operations_backlog_ids)} task(s) past their due date."
                ),
                count=len(raw.operations_backlog_ids),
                affected_ids=raw.operations_backlog_ids[:20],
            )
        )

    if raw.low_feedback_session_ids:
        alerts.append(
            ExecutiveAlertOut(
                alert_type="low_feedback_scores",
                severity="info",
                title="Low Feedback Scores",
                description=(
                    f"{len(raw.low_feedback_session_ids)} training session(s) "
                    "with average rating below 3.0."
                ),
                count=len(raw.low_feedback_session_ids),
                affected_ids=raw.low_feedback_session_ids[:20],
            )
        )

    return alerts


# ── Service ────────────────────────────────────────────────────────────────────


class ExecutiveDashboardService:
    def __init__(self, session: AsyncSession) -> None:
        self._db = session
        self._repo = ExecutiveDashboardRepo(session)

    def _org_and_wid(self, workspace_id: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
        ctx = get_tenant_context()
        return ctx.org_id, workspace_id

    async def get_kpis(self, workspace_id: uuid.UUID) -> ExecutiveKPIsOut:
        org_id, wid = self._org_and_wid(workspace_id)
        key = _kpis_key(org_id, wid)

        try:
            redis = get_redis()
            cached = await redis.get(key)
            if cached:
                return ExecutiveKPIsOut.model_validate_json(cached)
        except Exception:
            log.warning("exec_kpis_cache_get_failed", workspace_id=str(workspace_id))

        raw = await self._repo.fetch_kpis(org_id, wid)
        result = build_kpis(raw)

        try:
            redis = get_redis()
            await redis.set(key, result.model_dump_json(), ex=_CACHE_TTL)
        except Exception:
            log.warning("exec_kpis_cache_set_failed", workspace_id=str(workspace_id))

        return result

    async def get_summary(self, workspace_id: uuid.UUID) -> ExecutiveSummaryOut:
        kpis = await self.get_kpis(workspace_id)
        return ExecutiveSummaryOut(
            total_leads=kpis.total_leads,
            active_customers=kpis.active_customers,
            renewals_due=kpis.renewals_due,
            open_operations_tasks=kpis.open_operations_tasks,
            business_health_score=kpis.business_health_score,
        )

    async def get_alerts(self, workspace_id: uuid.UUID) -> list[ExecutiveAlertOut]:
        org_id, wid = self._org_and_wid(workspace_id)
        key = _alerts_key(org_id, wid)

        try:
            redis = get_redis()
            cached = await redis.get(key)
            if cached:
                data = json.loads(cached)
                return [ExecutiveAlertOut.model_validate(a) for a in data]
        except Exception:
            log.warning("exec_alerts_cache_get_failed", workspace_id=str(workspace_id))

        raw = await self._repo.fetch_alerts(org_id, wid)
        result = build_alerts(raw)

        try:
            redis = get_redis()
            await redis.set(
                key,
                json.dumps([a.model_dump() for a in result]),
                ex=_CACHE_TTL,
            )
        except Exception:
            log.warning("exec_alerts_cache_set_failed", workspace_id=str(workspace_id))

        return result

    async def get_trends(
        self, workspace_id: uuid.UUID, days: int = 30
    ) -> list[ExecutiveTrendOut]:
        if days not in _VALID_TREND_DAYS:
            days = 30
        org_id, wid = self._org_and_wid(workspace_id)
        key = _trends_key(org_id, wid, days)

        try:
            redis = get_redis()
            cached = await redis.get(key)
            if cached:
                data = json.loads(cached)
                return [ExecutiveTrendOut.model_validate(t) for t in data]
        except Exception:
            log.warning("exec_trends_cache_get_failed", workspace_id=str(workspace_id))

        raw = await self._repo.fetch_trends(org_id, wid, days)
        result = [
            ExecutiveTrendOut(
                date=r.date,
                leads_created=r.leads_created,
                customers_created=r.customers_created,
                training_completions=r.training_completions,
                renewals_processed=r.renewals_processed,
            )
            for r in raw
        ]

        try:
            redis = get_redis()
            await redis.set(
                key,
                json.dumps([t.model_dump() for t in result]),
                ex=_CACHE_TTL,
            )
        except Exception:
            log.warning("exec_trends_cache_set_failed", workspace_id=str(workspace_id))

        return result

    async def get_dashboard(self, workspace_id: uuid.UUID) -> ExecutiveDashboardOut:
        org_id, wid = self._org_and_wid(workspace_id)
        key = _dashboard_key(org_id, wid)

        try:
            redis = get_redis()
            cached = await redis.get(key)
            if cached:
                return ExecutiveDashboardOut.model_validate_json(cached)
        except Exception:
            log.warning("exec_dashboard_cache_get_failed", workspace_id=str(workspace_id))

        kpis_raw, alerts_raw, trends_raw = await asyncio.gather(
            self._repo.fetch_kpis(org_id, wid),
            self._repo.fetch_alerts(org_id, wid),
            self._repo.fetch_trends(org_id, wid, 30),
        )

        kpis = build_kpis(kpis_raw)
        summary = ExecutiveSummaryOut(
            total_leads=kpis.total_leads,
            active_customers=kpis.active_customers,
            renewals_due=kpis.renewals_due,
            open_operations_tasks=kpis.open_operations_tasks,
            business_health_score=kpis.business_health_score,
        )
        alerts = build_alerts(alerts_raw)
        trends_30d = [
            ExecutiveTrendOut(
                date=r.date,
                leads_created=r.leads_created,
                customers_created=r.customers_created,
                training_completions=r.training_completions,
                renewals_processed=r.renewals_processed,
            )
            for r in trends_raw
        ]

        result = ExecutiveDashboardOut(
            summary=summary,
            kpis=kpis,
            alerts=alerts,
            trends_30d=trends_30d,
            workspace_id=str(wid),
            generated_at=datetime.now(UTC).isoformat(),
        )

        try:
            redis = get_redis()
            await redis.set(key, result.model_dump_json(), ex=_CACHE_TTL)
        except Exception:
            log.warning("exec_dashboard_cache_set_failed", workspace_id=str(workspace_id))

        return result
