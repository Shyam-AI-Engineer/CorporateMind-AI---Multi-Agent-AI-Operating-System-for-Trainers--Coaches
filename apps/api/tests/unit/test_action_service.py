"""Sprint 25B — RecommendationActionService unit tests."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.modules.analytics.models import RecommendationAction
from corpmind.modules.analytics.schemas import (
    AcceptOut,
    DismissRequest,
    RecommendationActionOut,
    RecommendationActionsListOut,
    SnoozeRequest,
)
from corpmind.modules.analytics.service import RecommendationActionService

# ── Fixtures ─────────────────────────────────────────────────────────────────

TENANT_ID = uuid.uuid4()
WORKSPACE_ID = uuid.uuid4()
REC_ID = uuid.uuid4()
NOW = datetime(2026, 6, 26, 10, 0, 0, tzinfo=UTC)
TODAY = date(2026, 6, 26)


def _make_action(
    *,
    action_type: str = "accepted",
    snooze_until: date | None = None,
    reason: str | None = None,
    recommendation_id: uuid.UUID | None = None,
) -> RecommendationAction:
    row = MagicMock(spec=RecommendationAction)
    row.id = uuid.uuid4()
    row.recommendation_id = recommendation_id or REC_ID
    row.action_type = action_type
    row.snooze_until = snooze_until
    row.reason = reason
    row.created_at = NOW
    row.updated_at = NOW
    return row


def _mock_context() -> MagicMock:
    ctx = MagicMock()
    ctx.org_id = TENANT_ID
    return ctx


class _PatchSet:
    """Async context manager that starts all patches needed by the service.

    Exposes `redis` attribute so tests can assert on cache calls without
    going through the patch object (which has no `get_original()` API).
    """

    def __init__(self, snap_result: MagicMock | None, action_result: MagicMock) -> None:
        self._snap = snap_result
        self._action = action_result
        self._patches: list = []
        self.redis: MagicMock = MagicMock(
            get=AsyncMock(return_value=None),
            set=AsyncMock(),
            delete=AsyncMock(),
        )

    async def __aenter__(self) -> "_PatchSet":
        patches = [
            patch(
                "corpmind.modules.analytics.service.get_tenant_context",
                return_value=_mock_context(),
            ),
            patch(
                "corpmind.modules.analytics.service.get_redis",
                return_value=self.redis,
            ),
            patch(
                "corpmind.modules.analytics.repo.RecommendationSnapshotRepo.find_by_id",
                new_callable=AsyncMock,
                return_value=self._snap,
            ),
            patch(
                "corpmind.modules.analytics.repo.RecommendationActionRepo.upsert",
                new_callable=AsyncMock,
                return_value=self._action,
            ),
            patch(
                "corpmind.modules.analytics.repo.RecommendationActionRepo.list_by_workspace",
                new_callable=AsyncMock,
                return_value=[self._action],
            ),
            patch(
                "corpmind.modules.analytics.repo.RecommendationActionRepo.find_by_recommendation",
                new_callable=AsyncMock,
                return_value=self._action,
            ),
        ]
        for p in patches:
            self._patches.append(p)
            p.start()
        return self

    async def __aexit__(self, *_: object) -> None:
        for p in reversed(self._patches):
            p.stop()


def _svc() -> RecommendationActionService:
    return RecommendationActionService(session=AsyncMock())


# ── TestComputeStatus ─────────────────────────────────────────────────────────


class TestComputeStatus:
    def test_accepted_returns_accepted(self) -> None:
        row = _make_action(action_type="accepted")
        assert RecommendationActionService._compute_status(row) == "accepted"

    def test_dismissed_returns_dismissed(self) -> None:
        row = _make_action(action_type="dismissed")
        assert RecommendationActionService._compute_status(row) == "dismissed"

    def test_completed_returns_completed(self) -> None:
        row = _make_action(action_type="completed")
        assert RecommendationActionService._compute_status(row) == "completed"

    def test_snoozed_future_returns_snoozed(self) -> None:
        future = date.today() + timedelta(days=7)
        row = _make_action(action_type="snoozed", snooze_until=future)
        assert RecommendationActionService._compute_status(row) == "snoozed"

    def test_snoozed_past_returns_expired(self) -> None:
        past = date(2025, 1, 1)
        row = _make_action(action_type="snoozed", snooze_until=past)
        assert RecommendationActionService._compute_status(row) == "expired"

    def test_snoozed_today_returns_expired(self) -> None:
        row = _make_action(action_type="snoozed", snooze_until=date.today())
        assert RecommendationActionService._compute_status(row) == "expired"

    def test_snoozed_none_snooze_until_returns_snoozed(self) -> None:
        row = _make_action(action_type="snoozed", snooze_until=None)
        assert RecommendationActionService._compute_status(row) == "snoozed"


# ── TestSnoozeRequestValidation ───────────────────────────────────────────────


class TestSnoozeRequestValidation:
    def test_future_date_is_valid(self) -> None:
        future = date.today() + timedelta(days=1)
        req = SnoozeRequest(until=future)
        assert req.until == future

    def test_today_raises(self) -> None:
        with pytest.raises(Exception):
            SnoozeRequest(until=date.today())

    def test_past_date_raises(self) -> None:
        with pytest.raises(Exception):
            SnoozeRequest(until=date(2020, 1, 1))


# ── TestDismissRequestValidation ─────────────────────────────────────────────


class TestDismissRequestValidation:
    def test_reason_optional(self) -> None:
        req = DismissRequest()
        assert req.reason is None

    def test_reason_provided(self) -> None:
        req = DismissRequest(reason="Not relevant")
        assert req.reason == "Not relevant"


# ── TestAccept ────────────────────────────────────────────────────────────────


class TestAccept:
    @pytest.mark.asyncio
    async def test_returns_accept_out(self) -> None:
        snap = MagicMock()
        row = _make_action(action_type="accepted")
        async with _PatchSet(snap_result=snap, action_result=row):
            result = await _svc().accept(
                workspace_id=WORKSPACE_ID,
                recommendation_id=REC_ID,
            )
        assert isinstance(result, AcceptOut)
        assert result.status == "accepted"
        assert result.recommendation_id == REC_ID

    @pytest.mark.asyncio
    async def test_missing_snapshot_raises_value_error(self) -> None:
        row = _make_action(action_type="accepted")
        async with _PatchSet(snap_result=None, action_result=row):
            with pytest.raises(ValueError, match="not found"):
                await _svc().accept(
                    workspace_id=WORKSPACE_ID,
                    recommendation_id=REC_ID,
                )

    @pytest.mark.asyncio
    async def test_calls_upsert_with_accepted_type(self) -> None:
        snap = MagicMock()
        row = _make_action(action_type="accepted")
        async with _PatchSet(snap_result=snap, action_result=row):
            result = await _svc().accept(workspace_id=WORKSPACE_ID, recommendation_id=REC_ID)
        assert result.status == "accepted"

    @pytest.mark.asyncio
    async def test_invalidates_cache_on_success(self) -> None:
        snap = MagicMock()
        row = _make_action(action_type="accepted")
        async with _PatchSet(snap_result=snap, action_result=row) as ps:
            await _svc().accept(workspace_id=WORKSPACE_ID, recommendation_id=REC_ID)
            ps.redis.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_accepted_at_matches_row_updated_at(self) -> None:
        snap = MagicMock()
        row = _make_action(action_type="accepted")
        async with _PatchSet(snap_result=snap, action_result=row):
            result = await _svc().accept(workspace_id=WORKSPACE_ID, recommendation_id=REC_ID)
        assert result.accepted_at == row.updated_at


# ── TestDismiss ───────────────────────────────────────────────────────────────


class TestDismiss:
    @pytest.mark.asyncio
    async def test_returns_action_out(self) -> None:
        snap = MagicMock()
        row = _make_action(action_type="dismissed", reason="Not relevant")
        async with _PatchSet(snap_result=snap, action_result=row):
            result = await _svc().dismiss(
                workspace_id=WORKSPACE_ID,
                recommendation_id=REC_ID,
                reason="Not relevant",
            )
        assert isinstance(result, RecommendationActionOut)
        assert result.action_type == "dismissed"

    @pytest.mark.asyncio
    async def test_missing_snapshot_raises(self) -> None:
        row = _make_action(action_type="dismissed")
        async with _PatchSet(snap_result=None, action_result=row):
            with pytest.raises(ValueError):
                await _svc().dismiss(
                    workspace_id=WORKSPACE_ID,
                    recommendation_id=REC_ID,
                    reason=None,
                )

    @pytest.mark.asyncio
    async def test_reason_none_is_allowed(self) -> None:
        snap = MagicMock()
        row = _make_action(action_type="dismissed", reason=None)
        async with _PatchSet(snap_result=snap, action_result=row):
            result = await _svc().dismiss(
                workspace_id=WORKSPACE_ID,
                recommendation_id=REC_ID,
                reason=None,
            )
        assert result.reason is None

    @pytest.mark.asyncio
    async def test_status_is_dismissed(self) -> None:
        snap = MagicMock()
        row = _make_action(action_type="dismissed")
        async with _PatchSet(snap_result=snap, action_result=row):
            result = await _svc().dismiss(
                workspace_id=WORKSPACE_ID, recommendation_id=REC_ID, reason=None
            )
        assert result.status == "dismissed"

    @pytest.mark.asyncio
    async def test_invalidates_cache(self) -> None:
        snap = MagicMock()
        row = _make_action(action_type="dismissed")
        async with _PatchSet(snap_result=snap, action_result=row) as ps:
            await _svc().dismiss(
                workspace_id=WORKSPACE_ID, recommendation_id=REC_ID, reason=None
            )
            ps.redis.delete.assert_awaited_once()


# ── TestSnooze ────────────────────────────────────────────────────────────────


class TestSnooze:
    @pytest.mark.asyncio
    async def test_returns_action_out(self) -> None:
        snap = MagicMock()
        future = date.today() + timedelta(days=14)
        row = _make_action(action_type="snoozed", snooze_until=future)
        async with _PatchSet(snap_result=snap, action_result=row):
            result = await _svc().snooze(
                workspace_id=WORKSPACE_ID,
                recommendation_id=REC_ID,
                until=future,
            )
        assert isinstance(result, RecommendationActionOut)
        assert result.action_type == "snoozed"
        assert result.snooze_until == future

    @pytest.mark.asyncio
    async def test_missing_snapshot_raises(self) -> None:
        future = date.today() + timedelta(days=7)
        row = _make_action(action_type="snoozed", snooze_until=future)
        async with _PatchSet(snap_result=None, action_result=row):
            with pytest.raises(ValueError):
                await _svc().snooze(
                    workspace_id=WORKSPACE_ID, recommendation_id=REC_ID, until=future
                )

    @pytest.mark.asyncio
    async def test_status_is_snoozed_for_future_date(self) -> None:
        snap = MagicMock()
        future = date.today() + timedelta(days=30)
        row = _make_action(action_type="snoozed", snooze_until=future)
        async with _PatchSet(snap_result=snap, action_result=row):
            result = await _svc().snooze(
                workspace_id=WORKSPACE_ID, recommendation_id=REC_ID, until=future
            )
        assert result.status == "snoozed"

    @pytest.mark.asyncio
    async def test_invalidates_cache(self) -> None:
        snap = MagicMock()
        future = date.today() + timedelta(days=7)
        row = _make_action(action_type="snoozed", snooze_until=future)
        async with _PatchSet(snap_result=snap, action_result=row) as ps:
            await _svc().snooze(
                workspace_id=WORKSPACE_ID, recommendation_id=REC_ID, until=future
            )
            ps.redis.delete.assert_awaited_once()


# ── TestListActions ───────────────────────────────────────────────────────────


class TestListActions:
    @pytest.mark.asyncio
    async def test_returns_grouped_out(self) -> None:
        row = _make_action(action_type="accepted")
        async with _PatchSet(snap_result=MagicMock(), action_result=row):
            result = await _svc().list_actions(workspace_id=WORKSPACE_ID)
        assert isinstance(result, RecommendationActionsListOut)
        assert len(result.accepted) == 1
        assert result.total == 1

    @pytest.mark.asyncio
    async def test_snoozed_past_date_lands_in_expired(self) -> None:
        past = date(2024, 1, 1)
        row = _make_action(action_type="snoozed", snooze_until=past)
        async with _PatchSet(snap_result=MagicMock(), action_result=row):
            result = await _svc().list_actions(workspace_id=WORKSPACE_ID)
        assert len(result.expired) == 1
        assert len(result.snoozed) == 0

    @pytest.mark.asyncio
    async def test_snoozed_future_date_lands_in_snoozed(self) -> None:
        future = date.today() + timedelta(days=7)
        row = _make_action(action_type="snoozed", snooze_until=future)
        async with _PatchSet(snap_result=MagicMock(), action_result=row):
            result = await _svc().list_actions(workspace_id=WORKSPACE_ID)
        assert len(result.snoozed) == 1
        assert len(result.expired) == 0

    @pytest.mark.asyncio
    async def test_dismissed_lands_in_dismissed(self) -> None:
        row = _make_action(action_type="dismissed", reason="old")
        async with _PatchSet(snap_result=MagicMock(), action_result=row):
            result = await _svc().list_actions(workspace_id=WORKSPACE_ID)
        assert len(result.dismissed) == 1

    @pytest.mark.asyncio
    async def test_completed_lands_in_completed(self) -> None:
        row = _make_action(action_type="completed")
        async with _PatchSet(snap_result=MagicMock(), action_result=row):
            result = await _svc().list_actions(workspace_id=WORKSPACE_ID)
        assert len(result.completed) == 1

    @pytest.mark.asyncio
    async def test_empty_workspace_returns_empty_buckets(self) -> None:
        with (
            patch(
                "corpmind.modules.analytics.service.get_tenant_context",
                return_value=_mock_context(),
            ),
            patch(
                "corpmind.modules.analytics.service.get_redis",
                return_value=MagicMock(
                    get=AsyncMock(return_value=None),
                    set=AsyncMock(),
                    delete=AsyncMock(),
                ),
            ),
            patch(
                "corpmind.modules.analytics.repo.RecommendationActionRepo.list_by_workspace",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            result = await _svc().list_actions(workspace_id=WORKSPACE_ID)
        assert result.total == 0
        assert result.accepted == []
        assert result.dismissed == []

    @pytest.mark.asyncio
    async def test_returns_cache_hit_when_available(self) -> None:
        cached_out = RecommendationActionsListOut(
            accepted=[], dismissed=[], snoozed=[], completed=[], expired=[], total=0
        )
        with (
            patch(
                "corpmind.modules.analytics.service.get_tenant_context",
                return_value=_mock_context(),
            ),
            patch(
                "corpmind.modules.analytics.service.get_redis",
                return_value=MagicMock(
                    get=AsyncMock(return_value=cached_out.model_dump_json()),
                    set=AsyncMock(),
                    delete=AsyncMock(),
                ),
            ),
        ):
            result = await _svc().list_actions(workspace_id=WORKSPACE_ID)
        assert result.total == 0

    @pytest.mark.asyncio
    async def test_redis_error_falls_through_to_db(self) -> None:
        row = _make_action(action_type="accepted")
        async with _PatchSet(snap_result=MagicMock(), action_result=row):
            with patch(
                "corpmind.modules.analytics.service.get_redis",
                return_value=MagicMock(
                    get=AsyncMock(side_effect=Exception("redis down")),
                    set=AsyncMock(side_effect=Exception("redis down")),
                    delete=AsyncMock(side_effect=Exception("redis down")),
                ),
            ):
                result = await _svc().list_actions(workspace_id=WORKSPACE_ID)
        assert isinstance(result, RecommendationActionsListOut)


# ── TestToOut ─────────────────────────────────────────────────────────────────


class TestToOut:
    def test_fields_map_correctly(self) -> None:
        row = _make_action(action_type="accepted")
        svc = _svc()
        out = svc._to_out(row)
        assert out.id == row.id
        assert out.recommendation_id == row.recommendation_id
        assert out.action_type == "accepted"
        assert out.status == "accepted"
        assert out.reason is None
        assert out.snooze_until is None

    def test_expired_status_computed(self) -> None:
        past = date(2024, 6, 1)
        row = _make_action(action_type="snoozed", snooze_until=past)
        out = _svc()._to_out(row)
        assert out.status == "expired"
        assert out.snooze_until == past


# ── TestTenantIsolation ───────────────────────────────────────────────────────


class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_list_actions_uses_tenant_context(self) -> None:
        row = _make_action(action_type="accepted")
        async with _PatchSet(snap_result=MagicMock(), action_result=row):
            result = await _svc().list_actions(workspace_id=WORKSPACE_ID)
        assert isinstance(result, RecommendationActionsListOut)
        assert len(result.accepted) == 1

    @pytest.mark.asyncio
    async def test_accept_uses_tenant_id_from_context(self) -> None:
        snap = MagicMock()
        row = _make_action(action_type="accepted")
        async with _PatchSet(snap_result=snap, action_result=row):
            result = await _svc().accept(workspace_id=WORKSPACE_ID, recommendation_id=REC_ID)
        assert isinstance(result, AcceptOut)
        assert result.recommendation_id == REC_ID

    @pytest.mark.asyncio
    async def test_second_tenant_cannot_accept_first_tenants_rec(self) -> None:
        tenant2 = uuid.uuid4()
        ctx2 = MagicMock()
        ctx2.org_id = tenant2
        # Snapshot not found → raises ValueError → would be 404 in API layer
        with (
            patch(
                "corpmind.modules.analytics.service.get_tenant_context",
                return_value=ctx2,
            ),
            patch(
                "corpmind.modules.analytics.service.get_redis",
                return_value=MagicMock(
                    get=AsyncMock(return_value=None),
                    set=AsyncMock(),
                    delete=AsyncMock(),
                ),
            ),
            patch(
                "corpmind.modules.analytics.repo.RecommendationSnapshotRepo.find_by_id",
                new_callable=AsyncMock,
                return_value=None,  # Not found under tenant2's scope
            ),
        ):
            with pytest.raises(ValueError):
                await _svc().accept(workspace_id=WORKSPACE_ID, recommendation_id=REC_ID)


# ── TestCacheBehavior ─────────────────────────────────────────────────────────


class TestCacheBehavior:
    @pytest.mark.asyncio
    async def test_list_actions_writes_to_cache(self) -> None:
        row = _make_action(action_type="accepted")
        redis_mock = MagicMock(
            get=AsyncMock(return_value=None),
            set=AsyncMock(),
            delete=AsyncMock(),
        )
        with (
            patch(
                "corpmind.modules.analytics.service.get_tenant_context",
                return_value=_mock_context(),
            ),
            patch(
                "corpmind.modules.analytics.service.get_redis",
                return_value=redis_mock,
            ),
            patch(
                "corpmind.modules.analytics.repo.RecommendationActionRepo.list_by_workspace",
                new_callable=AsyncMock,
                return_value=[row],
            ),
        ):
            await _svc().list_actions(workspace_id=WORKSPACE_ID)
        redis_mock.set.assert_awaited_once()
        call_args = redis_mock.set.await_args
        assert call_args[1]["ex"] == 300  # 5-minute TTL

    @pytest.mark.asyncio
    async def test_accept_invalidates_cache_key(self) -> None:
        snap = MagicMock()
        row = _make_action(action_type="accepted")
        redis_mock = MagicMock(
            get=AsyncMock(return_value=None),
            set=AsyncMock(),
            delete=AsyncMock(),
        )
        with (
            patch(
                "corpmind.modules.analytics.service.get_tenant_context",
                return_value=_mock_context(),
            ),
            patch(
                "corpmind.modules.analytics.service.get_redis",
                return_value=redis_mock,
            ),
            patch(
                "corpmind.modules.analytics.repo.RecommendationSnapshotRepo.find_by_id",
                new_callable=AsyncMock,
                return_value=snap,
            ),
            patch(
                "corpmind.modules.analytics.repo.RecommendationActionRepo.upsert",
                new_callable=AsyncMock,
                return_value=row,
            ),
        ):
            await _svc().accept(workspace_id=WORKSPACE_ID, recommendation_id=REC_ID)
        redis_mock.delete.assert_awaited_once()
        deleted_key: str = redis_mock.delete.await_args[0][0]
        assert str(TENANT_ID) in deleted_key
        assert str(WORKSPACE_ID) in deleted_key
        assert "recommendation_actions" in deleted_key


# ── TestStatusTransitions ─────────────────────────────────────────────────────


class TestStatusTransitions:
    """Verifies that action_type can change (snoozed → accepted etc.)."""

    @pytest.mark.asyncio
    async def test_snoozed_to_accepted_transition(self) -> None:
        snap = MagicMock()
        # Row now shows accepted (upsert replaced snoozed)
        row = _make_action(action_type="accepted")
        async with _PatchSet(snap_result=snap, action_result=row):
            result = await _svc().accept(workspace_id=WORKSPACE_ID, recommendation_id=REC_ID)
        assert result.status == "accepted"

    @pytest.mark.asyncio
    async def test_accepted_to_dismissed_transition(self) -> None:
        snap = MagicMock()
        row = _make_action(action_type="dismissed", reason="changed mind")
        async with _PatchSet(snap_result=snap, action_result=row):
            result = await _svc().dismiss(
                workspace_id=WORKSPACE_ID, recommendation_id=REC_ID, reason="changed mind"
            )
        assert result.status == "dismissed"
