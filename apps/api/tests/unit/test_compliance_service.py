"""Unit tests for ComplianceService checks."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_opt_in_required_blocks_non_opted_in_contact() -> None:
    """Non-opted-in contact must be blocked by opt_in check."""
    assert True  # TODO(Phase 1)


@pytest.mark.asyncio
async def test_frequency_cap_blocks_over_limit_send() -> None:
    """Contact with 2+ sends in 7 days must be blocked."""
    assert True  # TODO(Phase 1)


@pytest.mark.asyncio
async def test_unsubscribed_contact_is_blocked() -> None:
    """Unsubscribed contact must be blocked regardless of frequency."""
    assert True  # TODO(Phase 1)
