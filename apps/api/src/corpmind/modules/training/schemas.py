"""Training Engagement and Session Pydantic v2 schemas — Sprint 42 / Sprint 43."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, field_validator

VALID_STATUSES: set[str] = {"planned", "scheduled", "in_progress", "completed", "cancelled"}
VALID_DELIVERY_MODES: set[str] = {"onsite", "online", "hybrid"}
VALID_PRIORITIES: set[str] = {"low", "medium", "high", "urgent"}
VALID_SESSION_STATUSES: set[str] = {"planned", "scheduled", "in_progress", "completed", "cancelled"}


class TrainingEngagementOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    customer_id: uuid.UUID
    program_name: str
    description: Optional[str]
    training_type: str
    delivery_mode: str
    status: str
    priority: str
    planned_start_date: Optional[date]
    planned_end_date: Optional[date]
    actual_start_date: Optional[date]
    actual_end_date: Optional[date]
    estimated_participants: Optional[int]
    actual_participants: Optional[int]
    assigned_trainer_id: Optional[uuid.UUID]
    coordinator_id: Optional[uuid.UUID]
    location: Optional[str]
    meeting_link: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime


class TrainingEngagementCreate(BaseModel):
    workspace_id: uuid.UUID
    customer_id: uuid.UUID
    program_name: str
    description: Optional[str] = None
    training_type: str
    delivery_mode: str
    status: str = "planned"
    priority: str = "medium"
    planned_start_date: Optional[date] = None
    planned_end_date: Optional[date] = None
    estimated_participants: Optional[int] = None
    assigned_trainer_id: Optional[uuid.UUID] = None
    coordinator_id: Optional[uuid.UUID] = None
    location: Optional[str] = None
    meeting_link: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("program_name")
    @classmethod
    def program_name_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("program_name must not be empty")
        return v

    @field_validator("delivery_mode")
    @classmethod
    def delivery_mode_valid(cls, v: str) -> str:
        if v not in VALID_DELIVERY_MODES:
            raise ValueError(f"delivery_mode must be one of {VALID_DELIVERY_MODES}")
        return v

    @field_validator("status")
    @classmethod
    def status_valid(cls, v: str) -> str:
        if v not in VALID_STATUSES:
            raise ValueError(f"status must be one of {VALID_STATUSES}")
        return v

    @field_validator("priority")
    @classmethod
    def priority_valid(cls, v: str) -> str:
        if v not in VALID_PRIORITIES:
            raise ValueError(f"priority must be one of {VALID_PRIORITIES}")
        return v

    @field_validator("estimated_participants")
    @classmethod
    def participants_non_negative(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 0:
            raise ValueError("estimated_participants must be non-negative")
        return v


class TrainingEngagementUpdate(BaseModel):
    program_name: Optional[str] = None
    description: Optional[str] = None
    training_type: Optional[str] = None
    delivery_mode: Optional[str] = None
    priority: Optional[str] = None
    planned_start_date: Optional[date] = None
    planned_end_date: Optional[date] = None
    estimated_participants: Optional[int] = None
    location: Optional[str] = None
    meeting_link: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("delivery_mode")
    @classmethod
    def delivery_mode_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_DELIVERY_MODES:
            raise ValueError(f"delivery_mode must be one of {VALID_DELIVERY_MODES}")
        return v

    @field_validator("priority")
    @classmethod
    def priority_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_PRIORITIES:
            raise ValueError(f"priority must be one of {VALID_PRIORITIES}")
        return v


class TrainerAssign(BaseModel):
    assigned_trainer_id: uuid.UUID


class CoordinatorAssign(BaseModel):
    coordinator_id: uuid.UUID


class CompleteEngagement(BaseModel):
    actual_end_date: Optional[date] = None
    actual_participants: Optional[int] = None
    notes: Optional[str] = None


class CancelEngagement(BaseModel):
    notes: Optional[str] = None


class TrainingEngagementListOut(BaseModel):
    items: list[TrainingEngagementOut]
    next_cursor: Optional[str]
    has_more: bool
    total: int


class TrainingEngagementFilters(BaseModel):
    workspace_id: uuid.UUID
    status: Optional[str] = None
    trainer_id: Optional[uuid.UUID] = None
    customer_id: Optional[uuid.UUID] = None
    delivery_mode: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    search: Optional[str] = None
    cursor: Optional[str] = None
    limit: int = 50


# ── Training Session schemas ────────────────────────────────────────────────────

class TrainingSessionOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    engagement_id: uuid.UUID
    session_name: str
    session_number: Optional[int]
    status: str
    scheduled_start: Optional[datetime]
    scheduled_end: Optional[datetime]
    actual_start: Optional[datetime]
    actual_end: Optional[datetime]
    trainer_id: Optional[uuid.UUID]
    location: Optional[str]
    meeting_link: Optional[str]
    capacity: Optional[int]
    expected_attendees: Optional[int]
    actual_attendees: Optional[int]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime


class TrainingSessionCreate(BaseModel):
    workspace_id: uuid.UUID
    engagement_id: uuid.UUID
    session_name: str
    session_number: Optional[int] = None
    status: str = "planned"
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    trainer_id: Optional[uuid.UUID] = None
    location: Optional[str] = None
    meeting_link: Optional[str] = None
    capacity: Optional[int] = None
    expected_attendees: Optional[int] = None
    notes: Optional[str] = None

    @field_validator("session_name")
    @classmethod
    def session_name_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("session_name must not be empty")
        return v

    @field_validator("status")
    @classmethod
    def status_valid(cls, v: str) -> str:
        if v not in VALID_SESSION_STATUSES:
            raise ValueError(f"status must be one of {VALID_SESSION_STATUSES}")
        return v

    @field_validator("capacity", "expected_attendees")
    @classmethod
    def non_negative_int(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 0:
            raise ValueError("value must be non-negative")
        return v

    @field_validator("session_number")
    @classmethod
    def session_number_positive(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 1:
            raise ValueError("session_number must be >= 1")
        return v


class TrainingSessionUpdate(BaseModel):
    session_name: Optional[str] = None
    session_number: Optional[int] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    location: Optional[str] = None
    meeting_link: Optional[str] = None
    capacity: Optional[int] = None
    expected_attendees: Optional[int] = None
    notes: Optional[str] = None

    @field_validator("session_name")
    @classmethod
    def session_name_not_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError("session_name must not be empty")
        return v


class CompleteSession(BaseModel):
    actual_end: Optional[datetime] = None
    actual_attendees: Optional[int] = None
    notes: Optional[str] = None


class CancelSession(BaseModel):
    notes: Optional[str] = None


class SessionTrainerAssign(BaseModel):
    trainer_id: uuid.UUID


class TrainingSessionListOut(BaseModel):
    items: list[TrainingSessionOut]
    next_cursor: Optional[str]
    has_more: bool
    total: int


class TrainingSessionFilters(BaseModel):
    workspace_id: uuid.UUID
    engagement_id: Optional[uuid.UUID] = None
    trainer_id: Optional[uuid.UUID] = None
    status: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    cursor: Optional[str] = None
    limit: int = 50


# ── Attendance schemas ────────────────────────────────────────────────────────

VALID_ATTENDANCE_STATUSES: set[str] = {
    "registered",
    "present",
    "late",
    "absent",
    "left_early",
}


class TrainingAttendanceOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    session_id: uuid.UUID
    participant_name: str
    participant_email: Optional[str]
    participant_phone: Optional[str]
    company: Optional[str]
    designation: Optional[str]
    attendance_status: str
    check_in_time: Optional[datetime]
    check_out_time: Optional[datetime]
    completion_percent: Optional[float]
    certificate_eligible: bool
    remarks: Optional[str]
    created_at: datetime
    updated_at: datetime


class TrainingAttendanceCreate(BaseModel):
    workspace_id: uuid.UUID
    session_id: uuid.UUID
    participant_name: str
    participant_email: Optional[str] = None
    participant_phone: Optional[str] = None
    company: Optional[str] = None
    designation: Optional[str] = None
    attendance_status: str = "registered"
    check_in_time: Optional[datetime] = None
    completion_percent: Optional[float] = None
    certificate_eligible: bool = False
    remarks: Optional[str] = None

    @field_validator("participant_name")
    @classmethod
    def participant_name_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("participant_name must not be empty")
        return v

    @field_validator("attendance_status")
    @classmethod
    def attendance_status_valid(cls, v: str) -> str:
        if v not in VALID_ATTENDANCE_STATUSES:
            raise ValueError(f"attendance_status must be one of {VALID_ATTENDANCE_STATUSES}")
        return v

    @field_validator("completion_percent")
    @classmethod
    def completion_percent_valid(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not (0.0 <= v <= 100.0):
            raise ValueError("completion_percent must be between 0 and 100")
        return v


class TrainingAttendanceUpdate(BaseModel):
    participant_name: Optional[str] = None
    participant_email: Optional[str] = None
    participant_phone: Optional[str] = None
    company: Optional[str] = None
    designation: Optional[str] = None
    check_in_time: Optional[datetime] = None
    check_out_time: Optional[datetime] = None
    completion_percent: Optional[float] = None
    certificate_eligible: Optional[bool] = None
    remarks: Optional[str] = None

    @field_validator("participant_name")
    @classmethod
    def participant_name_not_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError("participant_name must not be empty")
        return v

    @field_validator("completion_percent")
    @classmethod
    def completion_percent_valid(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not (0.0 <= v <= 100.0):
            raise ValueError("completion_percent must be between 0 and 100")
        return v


class CheckOutAttendance(BaseModel):
    check_out_time: Optional[datetime] = None
    completion_percent: Optional[float] = None
    certificate_eligible: Optional[bool] = None

    @field_validator("completion_percent")
    @classmethod
    def completion_percent_valid(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not (0.0 <= v <= 100.0):
            raise ValueError("completion_percent must be between 0 and 100")
        return v


class TrainingAttendanceListOut(BaseModel):
    items: list[TrainingAttendanceOut]
    next_cursor: Optional[str]
    has_more: bool
    total: int


class TrainingAttendanceFilters(BaseModel):
    workspace_id: uuid.UUID
    session_id: Optional[uuid.UUID] = None
    attendance_status: Optional[str] = None
    company: Optional[str] = None
    search: Optional[str] = None
    cursor: Optional[str] = None
    limit: int = 50
