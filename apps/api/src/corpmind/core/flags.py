"""Feature flag service.

Stage 1: Postgres-backed `feature_flags` table with Redis cache.
Flags are hierarchical dotted names: `<domain>.<feature>.<scope>`.

Usage:
    from corpmind.core.flags import is_enabled
    if is_enabled("agent.outreach.v4", tenant=ctx.tenant_id):
        ...
"""

from __future__ import annotations

import uuid
from functools import lru_cache

import structlog

log = structlog.get_logger(__name__)

# ── In-memory override for tests / local dev ──────────────────────────────────
_overrides: dict[str, bool] = {}


def is_enabled(flag: str, *, tenant: uuid.UUID | None = None) -> bool:
    """Check whether a feature flag is enabled.

    Precedence:
    1. Test/dev in-memory overrides (_overrides dict).
    2. Tenant-specific override in DB (if tenant provided).
    3. Global flag default from DB.
    4. False (safe default — flags default to off).
    """
    if flag in _overrides:
        return _overrides[flag]

    # TODO(Phase 1): query `feature_flags` table via Redis cache
    # For now, all flags default to off in the scaffold.
    log.debug("feature_flag.checked", flag=flag, tenant_id=str(tenant), result=False)
    return False


def override(flag: str, value: bool) -> None:
    """Set an in-memory override — use in tests only."""
    _overrides[flag] = value


def clear_overrides() -> None:
    """Clear all in-memory overrides — use in test teardown."""
    _overrides.clear()
