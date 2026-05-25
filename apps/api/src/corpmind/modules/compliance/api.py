"""Compliance module API routes."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()

# Compliance has no direct API surface for end-users in Phase 0.
# Audit log queries are exposed via the admin API.
# Unsubscribe webhook handlers live in the channel adapters.
