"""Team module schemas — Sprint 30."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

_VALID_ROLES: frozenset[str] = frozenset({"owner", "admin", "member", "viewer"})
_PROMOTE_RESTRICTED: frozenset[str] = frozenset({"owner"})


# ── Member schemas ─────────────────────────────────────────────────────────────

class MemberInviteIn(BaseModel):
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    role: str = "member"

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in _VALID_ROLES:
            raise ValueError(f"role must be one of {sorted(_VALID_ROLES)}")
        return v


class MemberAcceptIn(BaseModel):
    member_id: uuid.UUID
    workspace_id: uuid.UUID


class MemberRoleUpdate(BaseModel):
    role: str

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in _VALID_ROLES:
            raise ValueError(f"role must be one of {sorted(_VALID_ROLES)}")
        return v


class WorkspaceMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    invited_by: str
    invited_at: datetime
    accepted_at: datetime | None
    removed_at: datetime | None


class MemberListOut(BaseModel):
    items: list[WorkspaceMemberOut]
    total: int


# ── Activity schemas ───────────────────────────────────────────────────────────

class ActivityFeedEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    actor_user_id: str
    entity_type: str
    entity_id: uuid.UUID | None
    action: str
    feed_metadata: dict | None
    created_at: datetime


class ActivityFeedPage(BaseModel):
    items: list[ActivityFeedEntryOut]
    next_cursor: str | None
    has_more: bool


# ── Comment schemas ────────────────────────────────────────────────────────────

class CommentIn(BaseModel):
    body: str

    @field_validator("body")
    @classmethod
    def validate_body(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Comment body cannot be empty")
        if len(v) > 2000:
            raise ValueError("Comment body cannot exceed 2000 characters")
        return v


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID
    workspace_id: uuid.UUID
    author_user_id: str
    body: str
    created_at: datetime


# ── Task assignment ────────────────────────────────────────────────────────────

class TaskAssignIn(BaseModel):
    workspace_id: uuid.UUID
    assigned_user_id: uuid.UUID | None  # None = unassign
