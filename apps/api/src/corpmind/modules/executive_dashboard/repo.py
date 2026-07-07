"""Executive Dashboard raw SQL repository — Sprint 50.

All queries use text() SQL against real table names.
No cross-module ORM imports — follows the same pattern as Sprint 49 timeline_repo.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# ── Raw data containers ────────────────────────────────────────────────────────


@dataclass
class RawKPIData:
    total_leads: int = 0
    active_customers: int = 0
    renewals_due: int = 0
    customer_health_distribution: dict[str, int] = field(default_factory=dict)
    total_training_engagements: int = 0
    completed_training_engagements: int = 0
    total_certificate_eligible: int = 0
    total_certificates_issued: int = 0
    avg_feedback_rating: float | None = None
    total_workflow_runs: int = 0
    completed_workflow_runs: int = 0
    open_operations_tasks: int = 0


@dataclass
class RawAlertData:
    renewals_overdue: list[str] = field(default_factory=list)
    customers_at_risk_ids: list[str] = field(default_factory=list)
    training_overdue_ids: list[str] = field(default_factory=list)
    workflow_backlog_ids: list[str] = field(default_factory=list)
    operations_backlog_ids: list[str] = field(default_factory=list)
    low_feedback_session_ids: list[str] = field(default_factory=list)


@dataclass
class RawTrendPoint:
    date: str
    leads_created: int = 0
    customers_created: int = 0
    training_completions: int = 0
    renewals_processed: int = 0


# ── Repository ─────────────────────────────────────────────────────────────────


class ExecutiveDashboardRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    async def fetch_kpis(
        self, tenant_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> RawKPIData:
        params = {"tid": str(tenant_id), "wid": str(workspace_id)}

        leads_r = await self._db.execute(
            text(
                "SELECT COUNT(*) FROM leads "
                "WHERE tenant_id = :tid AND workspace_id = :wid"
            ),
            params,
        )
        total_leads = leads_r.scalar() or 0

        customers_r = await self._db.execute(
            text(
                "SELECT COUNT(*) FROM customers "
                "WHERE tenant_id = :tid AND workspace_id = :wid AND status = 'active'"
            ),
            params,
        )
        active_customers = customers_r.scalar() or 0

        renewals_r = await self._db.execute(
            text(
                "SELECT COUNT(*) FROM customer_renewals "
                "WHERE tenant_id = :tid AND workspace_id = :wid "
                "AND is_archived = false "
                "AND renewal_status NOT IN ('renewed', 'cancelled') "
                "AND renewal_date <= CURRENT_DATE + INTERVAL '30 days'"
            ),
            params,
        )
        renewals_due = renewals_r.scalar() or 0

        health_r = await self._db.execute(
            text(
                "SELECT health_status, COUNT(*) AS cnt FROM customers "
                "WHERE tenant_id = :tid AND workspace_id = :wid "
                "GROUP BY health_status"
            ),
            params,
        )
        health_dist = {row.health_status: int(row.cnt) for row in health_r.fetchall()}

        training_r = await self._db.execute(
            text(
                "SELECT "
                "  COUNT(*) AS total, "
                "  COUNT(*) FILTER (WHERE status = 'completed') AS completed "
                "FROM training_engagements "
                "WHERE tenant_id = :tid AND workspace_id = :wid"
            ),
            params,
        )
        tr = training_r.fetchone()
        total_eng = int(tr.total) if tr else 0
        completed_eng = int(tr.completed) if tr else 0

        eligible_r = await self._db.execute(
            text(
                "SELECT COUNT(*) FROM training_attendance "
                "WHERE tenant_id = :tid AND workspace_id = :wid "
                "AND certificate_eligible = true"
            ),
            params,
        )
        eligible = eligible_r.scalar() or 0

        certs_r = await self._db.execute(
            text(
                "SELECT COUNT(*) FROM training_certificates "
                "WHERE tenant_id = :tid AND workspace_id = :wid AND status = 'issued'"
            ),
            params,
        )
        certs_issued = certs_r.scalar() or 0

        feedback_r = await self._db.execute(
            text(
                "SELECT AVG(overall_rating::float) FROM training_feedback "
                "WHERE tenant_id = :tid AND workspace_id = :wid "
                "AND overall_rating IS NOT NULL"
            ),
            params,
        )
        raw_avg = feedback_r.scalar()
        avg_feedback = float(raw_avg) if raw_avg is not None else None

        wf_r = await self._db.execute(
            text(
                "SELECT "
                "  COUNT(*) AS total, "
                "  COUNT(*) FILTER (WHERE status = 'completed') AS completed "
                "FROM workflow_runs "
                "WHERE tenant_id = :tid AND workspace_id = :wid"
            ),
            params,
        )
        wfr = wf_r.fetchone()
        total_runs = int(wfr.total) if wfr else 0
        completed_runs = int(wfr.completed) if wfr else 0

        tasks_r = await self._db.execute(
            text(
                "SELECT COUNT(*) FROM business_tasks "
                "WHERE tenant_id = :tid AND workspace_id = :wid "
                "AND status NOT IN ('done', 'completed', 'cancelled')"
            ),
            params,
        )
        open_tasks = tasks_r.scalar() or 0

        return RawKPIData(
            total_leads=int(total_leads),
            active_customers=int(active_customers),
            renewals_due=int(renewals_due),
            customer_health_distribution=health_dist,
            total_training_engagements=total_eng,
            completed_training_engagements=completed_eng,
            total_certificate_eligible=int(eligible),
            total_certificates_issued=int(certs_issued),
            avg_feedback_rating=avg_feedback,
            total_workflow_runs=total_runs,
            completed_workflow_runs=completed_runs,
            open_operations_tasks=int(open_tasks),
        )

    async def fetch_alerts(
        self, tenant_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> RawAlertData:
        params = {"tid": str(tenant_id), "wid": str(workspace_id)}

        overdue_r = await self._db.execute(
            text(
                "SELECT id::text FROM customer_renewals "
                "WHERE tenant_id = :tid AND workspace_id = :wid "
                "AND is_archived = false "
                "AND renewal_status NOT IN ('renewed', 'cancelled') "
                "AND renewal_date < CURRENT_DATE "
                "LIMIT 20"
            ),
            params,
        )
        renewals_overdue = [row.id for row in overdue_r.fetchall()]

        at_risk_r = await self._db.execute(
            text(
                "SELECT customer_id::text FROM customer_success "
                "WHERE tenant_id = :tid AND workspace_id = :wid "
                "AND is_archived = false "
                "AND (health_status = 'at_risk' OR risk_level = 'high') "
                "LIMIT 20"
            ),
            params,
        )
        customers_at_risk = [row.customer_id for row in at_risk_r.fetchall()]

        te_overdue_r = await self._db.execute(
            text(
                "SELECT id::text FROM training_engagements "
                "WHERE tenant_id = :tid AND workspace_id = :wid "
                "AND status NOT IN ('completed', 'cancelled') "
                "AND planned_end_date < CURRENT_DATE "
                "LIMIT 20"
            ),
            params,
        )
        training_overdue = [row.id for row in te_overdue_r.fetchall()]

        wf_bl_r = await self._db.execute(
            text(
                "SELECT id::text FROM workflow_runs "
                "WHERE tenant_id = :tid AND workspace_id = :wid "
                "AND status = 'active' "
                "AND started_at < NOW() - INTERVAL '7 days' "
                "LIMIT 20"
            ),
            params,
        )
        workflow_backlog = [row.id for row in wf_bl_r.fetchall()]

        ops_bl_r = await self._db.execute(
            text(
                "SELECT id::text FROM business_tasks "
                "WHERE tenant_id = :tid AND workspace_id = :wid "
                "AND status NOT IN ('done', 'completed', 'cancelled') "
                "AND due_date < CURRENT_DATE "
                "LIMIT 20"
            ),
            params,
        )
        ops_backlog = [row.id for row in ops_bl_r.fetchall()]

        low_fb_r = await self._db.execute(
            text(
                "SELECT session_id::text "
                "FROM training_feedback "
                "WHERE tenant_id = :tid AND workspace_id = :wid "
                "AND overall_rating IS NOT NULL "
                "GROUP BY session_id "
                "HAVING AVG(overall_rating::float) < 3.0 "
                "LIMIT 20"
            ),
            params,
        )
        low_feedback = [row.session_id for row in low_fb_r.fetchall()]

        return RawAlertData(
            renewals_overdue=renewals_overdue,
            customers_at_risk_ids=customers_at_risk,
            training_overdue_ids=training_overdue,
            workflow_backlog_ids=workflow_backlog,
            operations_backlog_ids=ops_backlog,
            low_feedback_session_ids=low_feedback,
        )

    async def fetch_trends(
        self, tenant_id: uuid.UUID, workspace_id: uuid.UUID, days: int
    ) -> list[RawTrendPoint]:
        params = {"tid": str(tenant_id), "wid": str(workspace_id), "days": days}

        result = await self._db.execute(
            text(
                "WITH date_series AS ( "
                "  SELECT generate_series( "
                "    CURRENT_DATE - :days * INTERVAL '1 day', "
                "    CURRENT_DATE, "
                "    INTERVAL '1 day' "
                "  )::date AS d "
                "), "
                "leads_daily AS ( "
                "  SELECT created_at::date AS d, COUNT(*) AS cnt "
                "  FROM leads "
                "  WHERE tenant_id = :tid AND workspace_id = :wid "
                "    AND created_at >= CURRENT_DATE - :days * INTERVAL '1 day' "
                "  GROUP BY 1 "
                "), "
                "customers_daily AS ( "
                "  SELECT created_at::date AS d, COUNT(*) AS cnt "
                "  FROM customers "
                "  WHERE tenant_id = :tid AND workspace_id = :wid "
                "    AND created_at >= CURRENT_DATE - :days * INTERVAL '1 day' "
                "  GROUP BY 1 "
                "), "
                "training_daily AS ( "
                "  SELECT updated_at::date AS d, COUNT(*) AS cnt "
                "  FROM training_engagements "
                "  WHERE tenant_id = :tid AND workspace_id = :wid "
                "    AND status = 'completed' "
                "    AND updated_at >= CURRENT_DATE - :days * INTERVAL '1 day' "
                "  GROUP BY 1 "
                "), "
                "renewals_daily AS ( "
                "  SELECT updated_at::date AS d, COUNT(*) AS cnt "
                "  FROM customer_renewals "
                "  WHERE tenant_id = :tid AND workspace_id = :wid "
                "    AND renewal_status = 'renewed' "
                "    AND updated_at >= CURRENT_DATE - :days * INTERVAL '1 day' "
                "  GROUP BY 1 "
                ") "
                "SELECT "
                "  ds.d::text AS date, "
                "  COALESCE(ld.cnt, 0) AS leads_created, "
                "  COALESCE(cd.cnt, 0) AS customers_created, "
                "  COALESCE(td.cnt, 0) AS training_completions, "
                "  COALESCE(rd.cnt, 0) AS renewals_processed "
                "FROM date_series ds "
                "LEFT JOIN leads_daily ld ON ds.d = ld.d "
                "LEFT JOIN customers_daily cd ON ds.d = cd.d "
                "LEFT JOIN training_daily td ON ds.d = td.d "
                "LEFT JOIN renewals_daily rd ON ds.d = rd.d "
                "ORDER BY ds.d"
            ),
            params,
        )
        return [
            RawTrendPoint(
                date=row.date,
                leads_created=int(row.leads_created),
                customers_created=int(row.customers_created),
                training_completions=int(row.training_completions),
                renewals_processed=int(row.renewals_processed),
            )
            for row in result.fetchall()
        ]
