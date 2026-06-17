"""Identity module Pydantic schemas (request/response DTOs)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1, max_length=255)
    org_name: str = Field(min_length=1, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    org_id: uuid.UUID
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class OrgOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    plan_tier: str
    is_active: bool

    model_config = {"from_attributes": True}


# ── Sprint 14: workspace booking-webhook settings ─────────────────────────────

class WorkspaceBookingWebhookOut(BaseModel):
    workspace_id: uuid.UUID
    webhook_url: str
    has_secret: bool
    # The secret is returned so the trainer can copy it into their booking tool.
    # Only visible to authenticated OrgAdmins; never logged.
    secret: str | None = None
