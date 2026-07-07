"""Customer 360 timeline repository — Sprint 49.

All queries use text() SQL to avoid cross-module ORM model imports.
Every query filters by both customer_id and tenant_id for RLS defence-in-depth.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class RawEvent:
    event_id: str
    event_type: str
    occurred_at: datetime
    title: str
    entity_type: str | None = None
    entity_id: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class RawSummaryStats:
    total_trainings: int = 0
    completed_trainings: int = 0
    total_certificates: int = 0
    avg_feedback_rating: float | None = None
    current_health: str | None = None
    renewal_status: str | None = None
    latest_activity_at: datetime | None = None


# ── SQL fragments ──────────────────────────────────────────────────────────────

_SQL_EVENTS = text(
    """
WITH evts AS (
    -- customer_created
    SELECT id::text             AS event_id,
           'customer_created'   AS event_type,
           created_at           AS occurred_at,
           'Customer created'   AS title,
           'customer'           AS entity_type,
           id::text             AS entity_id,
           '{}'::jsonb          AS detail
    FROM customers
    WHERE id = :cid AND tenant_id = :tid

    UNION ALL

    -- training_engagement_created
    SELECT te.id::text,
           'training_engagement_created',
           te.created_at,
           'Training: ' || te.program_name,
           'training_engagement',
           te.id::text,
           jsonb_build_object('program_name', te.program_name, 'status', te.status)
    FROM training_engagements te
    WHERE te.customer_id = :cid AND te.tenant_id = :tid

    UNION ALL

    -- training_session_started
    SELECT ts.id::text,
           'training_session_started',
           ts.actual_start,
           'Session started: ' || ts.session_name,
           'training_session',
           ts.id::text,
           jsonb_build_object('session_name', ts.session_name, 'status', ts.status)
    FROM training_sessions ts
    JOIN training_engagements te ON ts.engagement_id = te.id AND te.tenant_id = :tid
    WHERE te.customer_id = :cid AND ts.tenant_id = :tid AND ts.actual_start IS NOT NULL

    UNION ALL

    -- training_session_completed
    SELECT ts.id::text,
           'training_session_completed',
           ts.actual_end,
           'Session completed: ' || ts.session_name,
           'training_session',
           ts.id::text,
           jsonb_build_object('session_name', ts.session_name)
    FROM training_sessions ts
    JOIN training_engagements te ON ts.engagement_id = te.id AND te.tenant_id = :tid
    WHERE te.customer_id = :cid AND ts.tenant_id = :tid
      AND ts.status = 'completed' AND ts.actual_end IS NOT NULL

    UNION ALL

    -- attendance_recorded
    SELECT ta.id::text,
           'attendance_recorded',
           ta.created_at,
           'Attendance: ' || ta.participant_name,
           'training_attendance',
           ta.id::text,
           jsonb_build_object('participant_name', ta.participant_name, 'status', ta.attendance_status)
    FROM training_attendance ta
    JOIN training_sessions ts ON ta.session_id = ts.id AND ts.tenant_id = :tid
    JOIN training_engagements te ON ts.engagement_id = te.id AND te.tenant_id = :tid
    WHERE te.customer_id = :cid AND ta.tenant_id = :tid

    UNION ALL

    -- certificate_issued
    SELECT tc.id::text,
           'certificate_issued',
           tc.created_at,
           'Certificate: ' || tc.participant_name,
           'training_certificate',
           tc.id::text,
           jsonb_build_object(
               'participant_name', tc.participant_name,
               'certificate_title', tc.certificate_title,
               'status', tc.status
           )
    FROM training_certificates tc
    JOIN training_sessions ts ON tc.session_id = ts.id AND ts.tenant_id = :tid
    JOIN training_engagements te ON ts.engagement_id = te.id AND te.tenant_id = :tid
    WHERE te.customer_id = :cid AND tc.tenant_id = :tid AND tc.status != 'draft'

    UNION ALL

    -- feedback_submitted
    SELECT tf.id::text,
           'feedback_submitted',
           tf.submitted_at,
           'Feedback submitted',
           'training_feedback',
           tf.id::text,
           jsonb_build_object('overall_rating', tf.overall_rating)
    FROM training_feedback tf
    WHERE tf.customer_id = :cid AND tf.tenant_id = :tid

    UNION ALL

    -- customer_health_updated
    SELECT cs.id::text,
           'customer_health_updated',
           cs.updated_at,
           'Health: ' || cs.health_status,
           'customer_success',
           cs.id::text,
           jsonb_build_object('health_status', cs.health_status)
    FROM customer_success cs
    WHERE cs.customer_id = :cid AND cs.tenant_id = :tid

    UNION ALL

    -- renewal_created
    SELECT cr.id::text,
           'renewal_created',
           cr.created_at,
           'Renewal: ' || COALESCE(cr.contract_name, cr.renewal_type),
           'customer_renewal',
           cr.id::text,
           jsonb_build_object('renewal_status', cr.renewal_status, 'renewal_type', cr.renewal_type)
    FROM customer_renewals cr
    WHERE cr.customer_id = :cid AND cr.tenant_id = :tid

    UNION ALL

    -- renewal_status_changed (only non-default statuses, avoids duplicate with renewal_created)
    SELECT cr.id::text,
           'renewal_status_changed',
           cr.updated_at,
           'Renewal status: ' || cr.renewal_status,
           'customer_renewal',
           cr.id::text,
           jsonb_build_object(
               'renewal_status', cr.renewal_status,
               'contract_name', cr.contract_name
           )
    FROM customer_renewals cr
    WHERE cr.customer_id = :cid AND cr.tenant_id = :tid
      AND cr.renewal_status != 'planned'
)
SELECT event_id, event_type, occurred_at, title, entity_type, entity_id, detail
FROM evts
WHERE occurred_at IS NOT NULL
ORDER BY occurred_at DESC, event_id ASC
"""
)

_SQL_SUMMARY = text(
    """
WITH
  eng AS (
      SELECT COUNT(*)                                                    AS total,
             COUNT(*) FILTER (WHERE status = 'completed')              AS completed
      FROM training_engagements
      WHERE customer_id = :cid AND tenant_id = :tid
  ),
  certs AS (
      SELECT COUNT(*) AS total
      FROM training_certificates tc
      JOIN training_sessions   ts ON tc.session_id   = ts.id   AND ts.tenant_id = :tid
      JOIN training_engagements te ON ts.engagement_id = te.id  AND te.tenant_id = :tid
      WHERE te.customer_id = :cid AND tc.tenant_id = :tid AND tc.status != 'draft'
  ),
  fb AS (
      SELECT AVG(overall_rating::float) AS avg_rating
      FROM training_feedback
      WHERE customer_id = :cid AND tenant_id = :tid AND overall_rating IS NOT NULL
  ),
  cs AS (
      SELECT health_status
      FROM customer_success
      WHERE customer_id = :cid AND tenant_id = :tid
      ORDER BY updated_at DESC
      LIMIT 1
  ),
  rn AS (
      SELECT renewal_status
      FROM customer_renewals
      WHERE customer_id = :cid AND tenant_id = :tid
      ORDER BY updated_at DESC
      LIMIT 1
  ),
  last_ts AS (
      SELECT MAX(ts) AS latest FROM (
          SELECT created_at AS ts FROM customers WHERE id = :cid AND tenant_id = :tid
          UNION ALL
          SELECT created_at  FROM training_engagements WHERE customer_id = :cid AND tenant_id = :tid
          UNION ALL
          SELECT updated_at  FROM customer_success     WHERE customer_id = :cid AND tenant_id = :tid
          UNION ALL
          SELECT created_at  FROM customer_renewals    WHERE customer_id = :cid AND tenant_id = :tid
          UNION ALL
          SELECT submitted_at FROM training_feedback   WHERE customer_id = :cid AND tenant_id = :tid
      ) sub
  )
SELECT
    eng.total              AS total_trainings,
    eng.completed          AS completed_trainings,
    certs.total            AS total_certificates,
    fb.avg_rating          AS avg_feedback_rating,
    cs.health_status       AS current_health,
    rn.renewal_status      AS renewal_status,
    last_ts.latest         AS latest_activity_at
FROM eng, certs, fb, last_ts
LEFT JOIN cs  ON TRUE
LEFT JOIN rn  ON TRUE
"""
)


class CustomerTimelineRepo:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def fetch_all_events(
        self,
        customer_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> list[RawEvent]:
        result = await self._db.execute(
            _SQL_EVENTS,
            {"cid": str(customer_id), "tid": str(tenant_id)},
        )
        rows = result.mappings().all()
        return [
            RawEvent(
                event_id=str(row["event_id"]),
                event_type=str(row["event_type"]),
                occurred_at=row["occurred_at"],
                title=str(row["title"]),
                entity_type=row["entity_type"],
                entity_id=row["entity_id"],
                detail=dict(row["detail"]) if row["detail"] else {},
            )
            for row in rows
        ]

    async def fetch_summary_stats(
        self,
        customer_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> RawSummaryStats:
        result = await self._db.execute(
            _SQL_SUMMARY,
            {"cid": str(customer_id), "tid": str(tenant_id)},
        )
        row = result.mappings().first()
        if row is None:
            return RawSummaryStats()
        return RawSummaryStats(
            total_trainings=int(row["total_trainings"] or 0),
            completed_trainings=int(row["completed_trainings"] or 0),
            total_certificates=int(row["total_certificates"] or 0),
            avg_feedback_rating=float(row["avg_feedback_rating"])
            if row["avg_feedback_rating"] is not None
            else None,
            current_health=row["current_health"],
            renewal_status=row["renewal_status"],
            latest_activity_at=row["latest_activity_at"],
        )
