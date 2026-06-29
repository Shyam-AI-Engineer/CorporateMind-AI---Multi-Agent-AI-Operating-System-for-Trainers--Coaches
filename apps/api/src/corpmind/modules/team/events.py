"""Team module domain events — Sprint 30."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class MemberInvited:
    member_id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    invited_by: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class MemberAccepted:
    member_id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class MemberRemoved:
    member_id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    removed_by: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class MemberRoleChanged:
    member_id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    old_role: str
    new_role: str
    changed_by: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class TaskAssigned:
    task_id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    assigned_user_id: str | None
    assigned_by: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class CommentAdded:
    comment_id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    task_id: uuid.UUID
    author_user_id: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class CommentDeleted:
    comment_id: uuid.UUID
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    task_id: uuid.UUID
    deleted_by: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
