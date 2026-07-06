"""Training Engagement, Session, Attendance, Certificate, and Feedback domain events — Sprint 42–46."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class TrainingEngagementCreated:
    engagement_id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    customer_id: uuid.UUID
    program_name: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class TrainingStarted:
    engagement_id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class TrainingCompleted:
    engagement_id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class TrainingCancelled:
    engagement_id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class TrainerAssigned:
    engagement_id: uuid.UUID
    tenant_id: uuid.UUID
    trainer_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class CoordinatorAssigned:
    engagement_id: uuid.UUID
    tenant_id: uuid.UUID
    coordinator_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


# ── Session events ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TrainingSessionCreated:
    session_id: uuid.UUID
    engagement_id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    session_name: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class TrainingSessionStarted:
    session_id: uuid.UUID
    engagement_id: uuid.UUID
    tenant_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class TrainingSessionCompleted:
    session_id: uuid.UUID
    engagement_id: uuid.UUID
    tenant_id: uuid.UUID
    actual_attendees: int | None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class TrainingSessionCancelled:
    session_id: uuid.UUID
    engagement_id: uuid.UUID
    tenant_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class TrainingSessionTrainerAssigned:
    session_id: uuid.UUID
    engagement_id: uuid.UUID
    tenant_id: uuid.UUID
    trainer_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


# ── Attendance events ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ParticipantRegistered:
    attendance_id: uuid.UUID
    session_id: uuid.UUID
    tenant_id: uuid.UUID
    participant_name: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class ParticipantPresent:
    attendance_id: uuid.UUID
    session_id: uuid.UUID
    tenant_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class ParticipantLate:
    attendance_id: uuid.UUID
    session_id: uuid.UUID
    tenant_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class ParticipantAbsent:
    attendance_id: uuid.UUID
    session_id: uuid.UUID
    tenant_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class ParticipantCheckedOut:
    attendance_id: uuid.UUID
    session_id: uuid.UUID
    tenant_id: uuid.UUID
    check_out_time: datetime
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


# ── Certificate events ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CertificateCreated:
    certificate_id: uuid.UUID
    attendance_id: uuid.UUID
    session_id: uuid.UUID
    tenant_id: uuid.UUID
    participant_name: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class CertificateIssued:
    certificate_id: uuid.UUID
    attendance_id: uuid.UUID
    session_id: uuid.UUID
    tenant_id: uuid.UUID
    issued_by: str | None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class CertificateRevoked:
    certificate_id: uuid.UUID
    attendance_id: uuid.UUID
    session_id: uuid.UUID
    tenant_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


# ── Feedback events ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TrainingFeedbackCreated:
    feedback_id: uuid.UUID
    attendance_id: uuid.UUID
    session_id: uuid.UUID
    customer_id: uuid.UUID
    tenant_id: uuid.UUID
    overall_rating: int | None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class TrainingFeedbackUpdated:
    feedback_id: uuid.UUID
    attendance_id: uuid.UUID
    session_id: uuid.UUID
    tenant_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
