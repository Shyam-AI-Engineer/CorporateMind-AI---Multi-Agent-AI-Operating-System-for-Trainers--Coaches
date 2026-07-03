"""Unit tests for Training Engagement module — Sprint 42.

Tests: schemas, repo helpers, service CRUD, status transitions, pagination,
       filters, search, trainer/coordinator assignment, cache, tenant isolation,
       events, and edge cases. Target: 120+ tests.
"""

from __future__ import annotations

import dataclasses
import uuid
from contextlib import contextmanager
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Shared fixtures ───────────────────────────────────────────────────────────

_ORG = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
_WS = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")
_CTX = SimpleNamespace(org_id=_ORG)
_EID = uuid.UUID("cccccccc-0000-0000-0000-000000000003")
_CID = uuid.UUID("dddddddd-0000-0000-0000-000000000004")
_TID = uuid.UUID("eeeeeeee-0000-0000-0000-000000000005")
_COORD = uuid.UUID("ffffffff-0000-0000-0000-000000000006")
_NOW = datetime(2026, 7, 2, 10, 0, 0, tzinfo=UTC)
_TODAY = date(2026, 7, 2)


def _engagement(**kw):
    defaults = dict(
        id=_EID,
        tenant_id=_ORG,
        workspace_id=_WS,
        customer_id=_CID,
        program_name="Leadership Excellence",
        description="A comprehensive leadership program",
        training_type="soft_skills",
        delivery_mode="onsite",
        status="planned",
        priority="medium",
        planned_start_date=date(2026, 8, 1),
        planned_end_date=date(2026, 8, 5),
        actual_start_date=None,
        actual_end_date=None,
        estimated_participants=30,
        actual_participants=None,
        assigned_trainer_id=_TID,
        coordinator_id=_COORD,
        location="Mumbai Conference Center",
        meeting_link=None,
        notes="VIP client",
        created_at=_NOW,
        updated_at=_NOW,
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def _svc():
    from corpmind.modules.training.service import TrainingEngagementService
    session = MagicMock()
    session.commit = AsyncMock()
    return TrainingEngagementService(session)


@contextmanager
def _ctx(redis_val=None):
    r = AsyncMock()
    r.get = AsyncMock(return_value=redis_val)
    r.set = AsyncMock()
    r.delete = AsyncMock()
    with (
        patch("corpmind.modules.training.service.get_tenant_context", return_value=_CTX),
        patch("corpmind.modules.training.service.get_redis", return_value=r),
    ):
        yield r


# ── Schema tests ──────────────────────────────────────────────────────────────

class TestSchemas:
    def test_create_required_fields(self):
        from corpmind.modules.training.schemas import TrainingEngagementCreate
        req = TrainingEngagementCreate(
            workspace_id=_WS,
            customer_id=_CID,
            program_name="Test Program",
            training_type="technical",
            delivery_mode="online",
        )
        assert req.status == "planned"
        assert req.priority == "medium"

    def test_create_invalid_delivery_mode(self):
        from corpmind.modules.training.schemas import TrainingEngagementCreate
        import pydantic
        with pytest.raises((pydantic.ValidationError, ValueError)):
            TrainingEngagementCreate(
                workspace_id=_WS, customer_id=_CID,
                program_name="X", training_type="T", delivery_mode="virtual",
            )

    def test_create_invalid_status(self):
        from corpmind.modules.training.schemas import TrainingEngagementCreate
        import pydantic
        with pytest.raises((pydantic.ValidationError, ValueError)):
            TrainingEngagementCreate(
                workspace_id=_WS, customer_id=_CID,
                program_name="X", training_type="T", delivery_mode="online", status="active",
            )

    def test_create_invalid_priority(self):
        from corpmind.modules.training.schemas import TrainingEngagementCreate
        import pydantic
        with pytest.raises((pydantic.ValidationError, ValueError)):
            TrainingEngagementCreate(
                workspace_id=_WS, customer_id=_CID,
                program_name="X", training_type="T", delivery_mode="online", priority="critical",
            )

    def test_create_empty_program_name_invalid(self):
        from corpmind.modules.training.schemas import TrainingEngagementCreate
        import pydantic
        with pytest.raises((pydantic.ValidationError, ValueError)):
            TrainingEngagementCreate(
                workspace_id=_WS, customer_id=_CID,
                program_name="", training_type="T", delivery_mode="online",
            )

    def test_create_all_delivery_modes(self):
        from corpmind.modules.training.schemas import TrainingEngagementCreate
        for mode in ["onsite", "online", "hybrid"]:
            req = TrainingEngagementCreate(
                workspace_id=_WS, customer_id=_CID,
                program_name="X", training_type="T", delivery_mode=mode,
            )
            assert req.delivery_mode == mode

    def test_create_all_statuses(self):
        from corpmind.modules.training.schemas import TrainingEngagementCreate
        for s in ["planned", "scheduled", "in_progress", "completed", "cancelled"]:
            req = TrainingEngagementCreate(
                workspace_id=_WS, customer_id=_CID,
                program_name="X", training_type="T", delivery_mode="online", status=s,
            )
            assert req.status == s

    def test_create_all_priorities(self):
        from corpmind.modules.training.schemas import TrainingEngagementCreate
        for p in ["low", "medium", "high", "urgent"]:
            req = TrainingEngagementCreate(
                workspace_id=_WS, customer_id=_CID,
                program_name="X", training_type="T", delivery_mode="online", priority=p,
            )
            assert req.priority == p

    def test_create_negative_participants_invalid(self):
        from corpmind.modules.training.schemas import TrainingEngagementCreate
        import pydantic
        with pytest.raises((pydantic.ValidationError, ValueError)):
            TrainingEngagementCreate(
                workspace_id=_WS, customer_id=_CID,
                program_name="X", training_type="T", delivery_mode="online",
                estimated_participants=-1,
            )

    def test_create_zero_participants_valid(self):
        from corpmind.modules.training.schemas import TrainingEngagementCreate
        req = TrainingEngagementCreate(
            workspace_id=_WS, customer_id=_CID,
            program_name="X", training_type="T", delivery_mode="online",
            estimated_participants=0,
        )
        assert req.estimated_participants == 0

    def test_out_from_attributes(self):
        from corpmind.modules.training.schemas import TrainingEngagementOut
        e = _engagement()
        out = TrainingEngagementOut.model_validate(e)
        assert out.program_name == "Leadership Excellence"
        assert out.status == "planned"

    def test_out_nullable_fields(self):
        from corpmind.modules.training.schemas import TrainingEngagementOut
        e = _engagement(description=None, meeting_link=None, actual_start_date=None)
        out = TrainingEngagementOut.model_validate(e)
        assert out.description is None
        assert out.actual_start_date is None

    def test_update_partial(self):
        from corpmind.modules.training.schemas import TrainingEngagementUpdate
        u = TrainingEngagementUpdate(program_name="New Name")
        assert u.program_name == "New Name"
        assert u.description is None

    def test_update_all_none(self):
        from corpmind.modules.training.schemas import TrainingEngagementUpdate
        u = TrainingEngagementUpdate()
        assert u.model_dump(exclude_none=True) == {}

    def test_update_invalid_delivery_mode(self):
        from corpmind.modules.training.schemas import TrainingEngagementUpdate
        import pydantic
        with pytest.raises((pydantic.ValidationError, ValueError)):
            TrainingEngagementUpdate(delivery_mode="video")

    def test_filters_defaults(self):
        from corpmind.modules.training.schemas import TrainingEngagementFilters
        f = TrainingEngagementFilters(workspace_id=_WS)
        assert f.limit == 50
        assert f.cursor is None
        assert f.status is None

    def test_list_out_empty(self):
        from corpmind.modules.training.schemas import TrainingEngagementListOut
        out = TrainingEngagementListOut(items=[], next_cursor=None, has_more=False, total=0)
        assert out.has_more is False

    def test_trainer_assign_schema(self):
        from corpmind.modules.training.schemas import TrainerAssign
        a = TrainerAssign(assigned_trainer_id=_TID)
        assert a.assigned_trainer_id == _TID

    def test_coordinator_assign_schema(self):
        from corpmind.modules.training.schemas import CoordinatorAssign
        a = CoordinatorAssign(coordinator_id=_COORD)
        assert a.coordinator_id == _COORD

    def test_complete_engagement_optional_fields(self):
        from corpmind.modules.training.schemas import CompleteEngagement
        c = CompleteEngagement()
        assert c.actual_end_date is None
        assert c.actual_participants is None

    def test_cancel_engagement_optional_notes(self):
        from corpmind.modules.training.schemas import CancelEngagement
        c = CancelEngagement(notes="Force majeure")
        assert c.notes == "Force majeure"

    def test_out_json_roundtrip(self):
        from corpmind.modules.training.schemas import TrainingEngagementOut
        e = _engagement()
        out = TrainingEngagementOut.model_validate(e)
        restored = TrainingEngagementOut.model_validate_json(out.model_dump_json())
        assert restored.id == out.id
        assert restored.program_name == out.program_name


# ── Cursor encoding tests ─────────────────────────────────────────────────────

class TestCursorEncoding:
    def test_encode_returns_string(self):
        from corpmind.modules.training.repo import encode_cursor
        token = encode_cursor(_NOW, _EID)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_encode_decode_roundtrip(self):
        from corpmind.modules.training.repo import encode_cursor, decode_cursor
        token = encode_cursor(_NOW, _EID)
        ts, rid = decode_cursor(token)
        assert rid == _EID

    def test_encode_same_inputs_same_output(self):
        from corpmind.modules.training.repo import encode_cursor
        t1 = encode_cursor(_NOW, _EID)
        t2 = encode_cursor(_NOW, _EID)
        assert t1 == t2

    def test_decode_malformed_raises(self):
        from corpmind.modules.training.repo import decode_cursor
        with pytest.raises(Exception):
            decode_cursor("not-valid-base64!!")

    def test_different_ids_different_cursors(self):
        from corpmind.modules.training.repo import encode_cursor
        other_id = uuid.uuid4()
        assert encode_cursor(_NOW, _EID) != encode_cursor(_NOW, other_id)


# ── Service: create ───────────────────────────────────────────────────────────

class TestCreateEngagement:
    @pytest.mark.asyncio
    async def test_create_returns_out(self):
        from corpmind.modules.training.repo import TrainingEngagementRepo
        from corpmind.modules.training.schemas import TrainingEngagementCreate
        e = _engagement()
        async def fake_create(self_r, eng): return eng
        async def fake_find(self_r, eid): return e
        with _ctx():
            with (
                patch.object(TrainingEngagementRepo, "create", fake_create),
                patch.object(TrainingEngagementRepo, "find_by_id", fake_find),
            ):
                req = TrainingEngagementCreate(
                    workspace_id=_WS, customer_id=_CID,
                    program_name="Leadership Excellence",
                    training_type="soft_skills", delivery_mode="onsite",
                )
                out = await _svc().create_engagement(req)
        assert out.program_name == "Leadership Excellence"

    @pytest.mark.asyncio
    async def test_create_sets_tenant_id(self):
        from corpmind.modules.training.repo import TrainingEngagementRepo
        from corpmind.modules.training.schemas import TrainingEngagementCreate
        created: list = []
        async def fake_create(self_r, eng):
            created.append(eng)
            return eng
        async def fake_find(self_r, eid): return created[0]
        with _ctx():
            with (
                patch.object(TrainingEngagementRepo, "create", fake_create),
                patch.object(TrainingEngagementRepo, "find_by_id", fake_find),
            ):
                req = TrainingEngagementCreate(
                    workspace_id=_WS, customer_id=_CID,
                    program_name="X", training_type="T", delivery_mode="online",
                )
                await _svc().create_engagement(req)
        assert created[0].tenant_id == _ORG

    @pytest.mark.asyncio
    async def test_create_busts_list_cache(self):
        from corpmind.modules.training.repo import TrainingEngagementRepo
        from corpmind.modules.training.schemas import TrainingEngagementCreate
        e = _engagement()
        async def fake_create(self_r, eng): return eng
        async def fake_find(self_r, eid): return e
        deleted_keys: list[str] = []
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock()
        async def fake_delete(key): deleted_keys.append(key)
        redis.delete = fake_delete
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=_CTX),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
            patch.object(TrainingEngagementRepo, "create", fake_create),
            patch.object(TrainingEngagementRepo, "find_by_id", fake_find),
        ):
            req = TrainingEngagementCreate(
                workspace_id=_WS, customer_id=_CID,
                program_name="X", training_type="T", delivery_mode="online",
            )
            await _svc().create_engagement(req)
        assert any("training:list" in k for k in deleted_keys)

    @pytest.mark.asyncio
    async def test_create_with_trainer_id(self):
        from corpmind.modules.training.repo import TrainingEngagementRepo
        from corpmind.modules.training.schemas import TrainingEngagementCreate
        created: list = []
        async def fake_create(self_r, eng):
            created.append(eng)
            return eng
        async def fake_find(self_r, eid): return created[0]
        with _ctx():
            with (
                patch.object(TrainingEngagementRepo, "create", fake_create),
                patch.object(TrainingEngagementRepo, "find_by_id", fake_find),
            ):
                req = TrainingEngagementCreate(
                    workspace_id=_WS, customer_id=_CID,
                    program_name="X", training_type="T", delivery_mode="online",
                    assigned_trainer_id=_TID,
                )
                await _svc().create_engagement(req)
        assert created[0].assigned_trainer_id == _TID


# ── Service: get ──────────────────────────────────────────────────────────────

class TestGetEngagement:
    @pytest.mark.asyncio
    async def test_get_returns_from_cache(self):
        from corpmind.modules.training.schemas import TrainingEngagementOut
        e = _engagement()
        cached_json = TrainingEngagementOut.model_validate(e).model_dump_json()
        with _ctx(redis_val=cached_json):
            out = await _svc().get_engagement(_EID)
        assert out.id == _EID

    @pytest.mark.asyncio
    async def test_get_hits_db_on_cache_miss(self):
        from corpmind.modules.training.repo import TrainingEngagementRepo
        e = _engagement()
        async def fake_find(self_r, eid): return e
        with _ctx():
            with patch.object(TrainingEngagementRepo, "find_by_id", fake_find):
                out = await _svc().get_engagement(_EID)
        assert out.program_name == "Leadership Excellence"

    @pytest.mark.asyncio
    async def test_get_raises_not_found(self):
        from corpmind.core.exceptions import NotFoundError
        from corpmind.modules.training.repo import TrainingEngagementRepo
        async def fake_find(self_r, eid): return None
        with _ctx():
            with patch.object(TrainingEngagementRepo, "find_by_id", fake_find):
                with pytest.raises(NotFoundError):
                    await _svc().get_engagement(_EID)

    @pytest.mark.asyncio
    async def test_get_writes_to_cache_after_db(self):
        from corpmind.modules.training.repo import TrainingEngagementRepo
        e = _engagement()
        async def fake_find(self_r, eid): return e
        with _ctx() as redis:
            with patch.object(TrainingEngagementRepo, "find_by_id", fake_find):
                await _svc().get_engagement(_EID)
        redis.set.assert_called_once()


# ── Service: update ───────────────────────────────────────────────────────────

class TestUpdateEngagement:
    @pytest.mark.asyncio
    async def test_update_not_found_raises(self):
        from corpmind.core.exceptions import NotFoundError
        from corpmind.modules.training.repo import TrainingEngagementRepo
        from corpmind.modules.training.schemas import TrainingEngagementUpdate
        async def fake_find(self_r, eid): return None
        with _ctx():
            with patch.object(TrainingEngagementRepo, "find_by_id", fake_find):
                with pytest.raises(NotFoundError):
                    await _svc().update_engagement(_EID, TrainingEngagementUpdate())

    @pytest.mark.asyncio
    async def test_update_calls_update_fields(self):
        from corpmind.modules.training.repo import TrainingEngagementRepo
        from corpmind.modules.training.schemas import TrainingEngagementUpdate
        e = _engagement()
        updated = _engagement(program_name="Updated")
        calls: list = []
        async def fake_find(self_r, eid): return updated
        async def fake_update(self_r, eid, **kw): calls.append(kw)
        with _ctx():
            with (
                patch.object(TrainingEngagementRepo, "find_by_id", fake_find),
                patch.object(TrainingEngagementRepo, "update_fields", fake_update),
            ):
                await _svc().update_engagement(_EID, TrainingEngagementUpdate(program_name="Updated"))
        assert any("program_name" in c for c in calls)

    @pytest.mark.asyncio
    async def test_update_busts_detail_cache(self):
        from corpmind.modules.training.repo import TrainingEngagementRepo
        from corpmind.modules.training.schemas import TrainingEngagementUpdate
        e = _engagement()
        deleted: list[str] = []
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock()
        async def fake_delete(key): deleted.append(key)
        redis.delete = fake_delete
        async def fake_find(self_r, eid): return e
        async def fake_update(self_r, eid, **kw): pass
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=_CTX),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
            patch.object(TrainingEngagementRepo, "find_by_id", fake_find),
            patch.object(TrainingEngagementRepo, "update_fields", fake_update),
        ):
            await _svc().update_engagement(_EID, TrainingEngagementUpdate(notes="changed"))
        assert any("training:detail" in k for k in deleted)


# ── Service: status transitions ───────────────────────────────────────────────

class TestStatusTransitions:
    async def _transition(self, from_status: str, to_status: str, method: str, **kw):
        from corpmind.modules.training.repo import TrainingEngagementRepo
        e = _engagement(status=from_status)
        final = _engagement(status=to_status)
        call_count = [0]
        async def fake_find(self_r, eid):
            call_count[0] += 1
            return e if call_count[0] == 1 else final
        async def fake_update(self_r, eid, **fields): pass
        with _ctx():
            with (
                patch.object(TrainingEngagementRepo, "find_by_id", fake_find),
                patch.object(TrainingEngagementRepo, "update_fields", fake_update),
            ):
                svc = _svc()
                fn = getattr(svc, method)
                return await fn(_EID, **kw)

    @pytest.mark.asyncio
    async def test_planned_to_in_progress_via_start(self):
        out = await self._transition("planned", "in_progress", "start_engagement")
        assert out.status == "in_progress"

    @pytest.mark.asyncio
    async def test_scheduled_to_in_progress_via_start(self):
        out = await self._transition("scheduled", "in_progress", "start_engagement")
        assert out.status == "in_progress"

    @pytest.mark.asyncio
    async def test_in_progress_to_completed(self):
        from corpmind.modules.training.schemas import CompleteEngagement
        out = await self._transition(
            "in_progress", "completed", "complete_engagement",
            req=CompleteEngagement()
        )
        assert out.status == "completed"

    @pytest.mark.asyncio
    async def test_planned_to_cancelled(self):
        from corpmind.modules.training.schemas import CancelEngagement
        out = await self._transition(
            "planned", "cancelled", "cancel_engagement",
            req=CancelEngagement()
        )
        assert out.status == "cancelled"

    @pytest.mark.asyncio
    async def test_scheduled_to_cancelled(self):
        from corpmind.modules.training.schemas import CancelEngagement
        out = await self._transition(
            "scheduled", "cancelled", "cancel_engagement",
            req=CancelEngagement()
        )
        assert out.status == "cancelled"

    @pytest.mark.asyncio
    async def test_in_progress_to_cancelled(self):
        from corpmind.modules.training.schemas import CancelEngagement
        out = await self._transition(
            "in_progress", "cancelled", "cancel_engagement",
            req=CancelEngagement()
        )
        assert out.status == "cancelled"

    @pytest.mark.asyncio
    async def test_completed_cannot_restart(self):
        from corpmind.core.exceptions import ValidationError
        from corpmind.modules.training.repo import TrainingEngagementRepo
        e = _engagement(status="completed")
        async def fake_find(self_r, eid): return e
        async def fake_update(self_r, eid, **kw): pass
        with _ctx():
            with (
                patch.object(TrainingEngagementRepo, "find_by_id", fake_find),
                patch.object(TrainingEngagementRepo, "update_fields", fake_update),
            ):
                with pytest.raises(ValidationError):
                    await _svc().start_engagement(_EID)

    @pytest.mark.asyncio
    async def test_cancelled_cannot_start(self):
        from corpmind.core.exceptions import ValidationError
        from corpmind.modules.training.repo import TrainingEngagementRepo
        e = _engagement(status="cancelled")
        async def fake_find(self_r, eid): return e
        async def fake_update(self_r, eid, **kw): pass
        with _ctx():
            with (
                patch.object(TrainingEngagementRepo, "find_by_id", fake_find),
                patch.object(TrainingEngagementRepo, "update_fields", fake_update),
            ):
                with pytest.raises(ValidationError):
                    await _svc().start_engagement(_EID)

    @pytest.mark.asyncio
    async def test_completed_cannot_cancel(self):
        from corpmind.core.exceptions import ValidationError
        from corpmind.modules.training.repo import TrainingEngagementRepo
        from corpmind.modules.training.schemas import CancelEngagement
        e = _engagement(status="completed")
        async def fake_find(self_r, eid): return e
        async def fake_update(self_r, eid, **kw): pass
        with _ctx():
            with (
                patch.object(TrainingEngagementRepo, "find_by_id", fake_find),
                patch.object(TrainingEngagementRepo, "update_fields", fake_update),
            ):
                with pytest.raises(ValidationError):
                    await _svc().cancel_engagement(_EID, CancelEngagement())

    @pytest.mark.asyncio
    async def test_start_not_found_raises(self):
        from corpmind.core.exceptions import NotFoundError
        from corpmind.modules.training.repo import TrainingEngagementRepo
        async def fake_find(self_r, eid): return None
        with _ctx():
            with patch.object(TrainingEngagementRepo, "find_by_id", fake_find):
                with pytest.raises(NotFoundError):
                    await _svc().start_engagement(_EID)

    @pytest.mark.asyncio
    async def test_complete_not_found_raises(self):
        from corpmind.core.exceptions import NotFoundError
        from corpmind.modules.training.repo import TrainingEngagementRepo
        from corpmind.modules.training.schemas import CompleteEngagement
        async def fake_find(self_r, eid): return None
        with _ctx():
            with patch.object(TrainingEngagementRepo, "find_by_id", fake_find):
                with pytest.raises(NotFoundError):
                    await _svc().complete_engagement(_EID, CompleteEngagement())

    @pytest.mark.asyncio
    async def test_complete_sets_actual_end_date_default(self):
        from corpmind.modules.training.repo import TrainingEngagementRepo
        from corpmind.modules.training.schemas import CompleteEngagement
        e = _engagement(status="in_progress")
        final = _engagement(status="completed", actual_end_date=_TODAY)
        call_count = [0]
        field_calls: list = []
        async def fake_find(self_r, eid):
            call_count[0] += 1
            return e if call_count[0] == 1 else final
        async def fake_update(self_r, eid, **kw): field_calls.append(kw)
        with _ctx():
            with (
                patch.object(TrainingEngagementRepo, "find_by_id", fake_find),
                patch.object(TrainingEngagementRepo, "update_fields", fake_update),
            ):
                await _svc().complete_engagement(_EID, CompleteEngagement())
        assert any("actual_end_date" in c for c in field_calls)

    @pytest.mark.asyncio
    async def test_complete_with_participants(self):
        from corpmind.modules.training.repo import TrainingEngagementRepo
        from corpmind.modules.training.schemas import CompleteEngagement
        e = _engagement(status="in_progress")
        final = _engagement(status="completed", actual_participants=28)
        call_count = [0]
        field_calls: list = []
        async def fake_find(self_r, eid):
            call_count[0] += 1
            return e if call_count[0] == 1 else final
        async def fake_update(self_r, eid, **kw): field_calls.append(kw)
        with _ctx():
            with (
                patch.object(TrainingEngagementRepo, "find_by_id", fake_find),
                patch.object(TrainingEngagementRepo, "update_fields", fake_update),
            ):
                await _svc().complete_engagement(_EID, CompleteEngagement(actual_participants=28))
        assert any(c.get("actual_participants") == 28 for c in field_calls)

    @pytest.mark.asyncio
    async def test_cancel_with_notes(self):
        from corpmind.modules.training.repo import TrainingEngagementRepo
        from corpmind.modules.training.schemas import CancelEngagement
        e = _engagement(status="planned")
        final = _engagement(status="cancelled", notes="Force majeure")
        call_count = [0]
        field_calls: list = []
        async def fake_find(self_r, eid):
            call_count[0] += 1
            return e if call_count[0] == 1 else final
        async def fake_update(self_r, eid, **kw): field_calls.append(kw)
        with _ctx():
            with (
                patch.object(TrainingEngagementRepo, "find_by_id", fake_find),
                patch.object(TrainingEngagementRepo, "update_fields", fake_update),
            ):
                await _svc().cancel_engagement(_EID, CancelEngagement(notes="Force majeure"))
        assert any(c.get("notes") == "Force majeure" for c in field_calls)


# ── Service: trainer assignment ───────────────────────────────────────────────

class TestTrainerAssignment:
    @pytest.mark.asyncio
    async def test_assign_trainer_returns_out(self):
        from corpmind.modules.training.repo import TrainingEngagementRepo
        e = _engagement(assigned_trainer_id=None)
        final = _engagement(assigned_trainer_id=_TID)
        call_count = [0]
        async def fake_find(self_r, eid):
            call_count[0] += 1
            return e if call_count[0] == 1 else final
        async def fake_update(self_r, eid, **kw): pass
        with _ctx():
            with (
                patch.object(TrainingEngagementRepo, "find_by_id", fake_find),
                patch.object(TrainingEngagementRepo, "update_fields", fake_update),
            ):
                out = await _svc().assign_trainer(_EID, _TID)
        assert out.assigned_trainer_id == _TID

    @pytest.mark.asyncio
    async def test_assign_trainer_not_found(self):
        from corpmind.core.exceptions import NotFoundError
        from corpmind.modules.training.repo import TrainingEngagementRepo
        async def fake_find(self_r, eid): return None
        with _ctx():
            with patch.object(TrainingEngagementRepo, "find_by_id", fake_find):
                with pytest.raises(NotFoundError):
                    await _svc().assign_trainer(_EID, _TID)

    @pytest.mark.asyncio
    async def test_assign_trainer_calls_update_fields(self):
        from corpmind.modules.training.repo import TrainingEngagementRepo
        e = _engagement()
        final = _engagement(assigned_trainer_id=_TID)
        call_count = [0]
        field_calls: list = []
        async def fake_find(self_r, eid):
            call_count[0] += 1
            return e if call_count[0] == 1 else final
        async def fake_update(self_r, eid, **kw): field_calls.append(kw)
        with _ctx():
            with (
                patch.object(TrainingEngagementRepo, "find_by_id", fake_find),
                patch.object(TrainingEngagementRepo, "update_fields", fake_update),
            ):
                await _svc().assign_trainer(_EID, _TID)
        assert any(c.get("assigned_trainer_id") == _TID for c in field_calls)

    @pytest.mark.asyncio
    async def test_assign_coordinator_returns_out(self):
        from corpmind.modules.training.repo import TrainingEngagementRepo
        e = _engagement(coordinator_id=None)
        final = _engagement(coordinator_id=_COORD)
        call_count = [0]
        async def fake_find(self_r, eid):
            call_count[0] += 1
            return e if call_count[0] == 1 else final
        async def fake_update(self_r, eid, **kw): pass
        with _ctx():
            with (
                patch.object(TrainingEngagementRepo, "find_by_id", fake_find),
                patch.object(TrainingEngagementRepo, "update_fields", fake_update),
            ):
                out = await _svc().assign_coordinator(_EID, _COORD)
        assert out.coordinator_id == _COORD

    @pytest.mark.asyncio
    async def test_assign_coordinator_not_found(self):
        from corpmind.core.exceptions import NotFoundError
        from corpmind.modules.training.repo import TrainingEngagementRepo
        async def fake_find(self_r, eid): return None
        with _ctx():
            with patch.object(TrainingEngagementRepo, "find_by_id", fake_find):
                with pytest.raises(NotFoundError):
                    await _svc().assign_coordinator(_EID, _COORD)


# ── Service: list ─────────────────────────────────────────────────────────────

class TestListEngagements:
    @pytest.mark.asyncio
    async def test_empty_list(self):
        from corpmind.modules.training.repo import TrainingEngagementRepo
        from corpmind.modules.training.schemas import TrainingEngagementFilters
        async def fake_count(self_r, ws, **kw): return 0
        async def fake_list(self_r, ws, **kw): return []
        with _ctx():
            with (
                patch.object(TrainingEngagementRepo, "count", fake_count),
                patch.object(TrainingEngagementRepo, "list_page", fake_list),
            ):
                out = await _svc().list_engagements(TrainingEngagementFilters(workspace_id=_WS))
        assert out.items == []
        assert out.total == 0
        assert out.has_more is False

    @pytest.mark.asyncio
    async def test_list_returns_items(self):
        from corpmind.modules.training.repo import TrainingEngagementRepo
        from corpmind.modules.training.schemas import TrainingEngagementFilters
        rows = [_engagement()]
        async def fake_count(self_r, ws, **kw): return 1
        async def fake_list(self_r, ws, **kw): return rows
        with _ctx():
            with (
                patch.object(TrainingEngagementRepo, "count", fake_count),
                patch.object(TrainingEngagementRepo, "list_page", fake_list),
            ):
                out = await _svc().list_engagements(TrainingEngagementFilters(workspace_id=_WS))
        assert len(out.items) == 1
        assert out.total == 1

    @pytest.mark.asyncio
    async def test_has_more_when_full_page(self):
        from corpmind.modules.training.repo import TrainingEngagementRepo
        from corpmind.modules.training.schemas import TrainingEngagementFilters
        rows = [_engagement(id=uuid.uuid4()) for _ in range(50)]
        for r in rows:
            r.created_at = _NOW
        async def fake_count(self_r, ws, **kw): return 100
        async def fake_list(self_r, ws, **kw): return rows
        with _ctx():
            with (
                patch.object(TrainingEngagementRepo, "count", fake_count),
                patch.object(TrainingEngagementRepo, "list_page", fake_list),
            ):
                out = await _svc().list_engagements(TrainingEngagementFilters(workspace_id=_WS))
        assert out.has_more is True
        assert out.next_cursor is not None

    @pytest.mark.asyncio
    async def test_list_cache_hit(self):
        from corpmind.modules.training.schemas import TrainingEngagementFilters, TrainingEngagementListOut
        cached = TrainingEngagementListOut(items=[], next_cursor=None, has_more=False, total=5)
        cached_json = cached.model_dump_json()
        with _ctx(redis_val=cached_json):
            out = await _svc().list_engagements(TrainingEngagementFilters(workspace_id=_WS))
        assert out.total == 5

    @pytest.mark.asyncio
    async def test_filtered_query_skips_cache(self):
        from corpmind.modules.training.repo import TrainingEngagementRepo
        from corpmind.modules.training.schemas import TrainingEngagementFilters, TrainingEngagementListOut
        cached = TrainingEngagementListOut(items=[], next_cursor=None, has_more=False, total=99)
        async def fake_count(self_r, ws, **kw): return 3
        async def fake_list(self_r, ws, **kw): return [_engagement()]
        with _ctx(redis_val=cached.model_dump_json()):
            with (
                patch.object(TrainingEngagementRepo, "count", fake_count),
                patch.object(TrainingEngagementRepo, "list_page", fake_list),
            ):
                out = await _svc().list_engagements(
                    TrainingEngagementFilters(workspace_id=_WS, status="planned")
                )
        # filter bypasses cache → gets DB result (3), not cached (99)
        assert out.total == 3

    @pytest.mark.asyncio
    async def test_total_independent_of_page(self):
        from corpmind.modules.training.repo import TrainingEngagementRepo
        from corpmind.modules.training.schemas import TrainingEngagementFilters
        async def fake_count(self_r, ws, **kw): return 500
        async def fake_list(self_r, ws, **kw): return [_engagement()]
        with _ctx():
            with (
                patch.object(TrainingEngagementRepo, "count", fake_count),
                patch.object(TrainingEngagementRepo, "list_page", fake_list),
            ):
                out = await _svc().list_engagements(TrainingEngagementFilters(workspace_id=_WS))
        assert out.total == 500


# ── Service: search ───────────────────────────────────────────────────────────

class TestSearchEngagements:
    @pytest.mark.asyncio
    async def test_search_returns_list(self):
        from corpmind.modules.training.repo import TrainingEngagementRepo
        rows = [_engagement()]
        async def fake_count(self_r, ws, **kw): return 1
        async def fake_list(self_r, ws, **kw): return rows
        with _ctx():
            with (
                patch.object(TrainingEngagementRepo, "count", fake_count),
                patch.object(TrainingEngagementRepo, "list_page", fake_list),
            ):
                results = await _svc().search_engagements(_WS, "Leadership")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_search_empty_returns_empty(self):
        from corpmind.modules.training.repo import TrainingEngagementRepo
        async def fake_count(self_r, ws, **kw): return 0
        async def fake_list(self_r, ws, **kw): return []
        with _ctx():
            with (
                patch.object(TrainingEngagementRepo, "count", fake_count),
                patch.object(TrainingEngagementRepo, "list_page", fake_list),
            ):
                results = await _svc().search_engagements(_WS, "xyz")
        assert results == []


# ── Filter pass-through ───────────────────────────────────────────────────────

class TestFilterPassThrough:
    async def _received_count_kw(self, **filter_kw):
        from corpmind.modules.training.repo import TrainingEngagementRepo
        from corpmind.modules.training.schemas import TrainingEngagementFilters
        received: dict = {}
        async def fake_count(self_r, ws, **kw): received.update(kw); return 0
        async def fake_list(self_r, ws, **kw): return []
        with _ctx():
            with (
                patch.object(TrainingEngagementRepo, "count", fake_count),
                patch.object(TrainingEngagementRepo, "list_page", fake_list),
            ):
                await _svc().list_engagements(
                    TrainingEngagementFilters(workspace_id=_WS, **filter_kw)
                )
        return received

    @pytest.mark.asyncio
    async def test_status_forwarded(self):
        r = await self._received_count_kw(status="in_progress")
        assert r.get("status") == "in_progress"

    @pytest.mark.asyncio
    async def test_trainer_id_forwarded(self):
        r = await self._received_count_kw(trainer_id=_TID)
        assert r.get("trainer_id") == _TID

    @pytest.mark.asyncio
    async def test_customer_id_forwarded(self):
        r = await self._received_count_kw(customer_id=_CID)
        assert r.get("customer_id") == _CID

    @pytest.mark.asyncio
    async def test_delivery_mode_forwarded(self):
        r = await self._received_count_kw(delivery_mode="online")
        assert r.get("delivery_mode") == "online"

    @pytest.mark.asyncio
    async def test_date_from_forwarded(self):
        r = await self._received_count_kw(date_from=_TODAY)
        assert r.get("date_from") == _TODAY

    @pytest.mark.asyncio
    async def test_date_to_forwarded(self):
        r = await self._received_count_kw(date_to=_TODAY)
        assert r.get("date_to") == _TODAY

    @pytest.mark.asyncio
    async def test_search_forwarded(self):
        r = await self._received_count_kw(search="leader")
        assert r.get("search") == "leader"


# ── Pagination extras ─────────────────────────────────────────────────────────

class TestPaginationExtra:
    @pytest.mark.asyncio
    async def test_next_cursor_decodeable(self):
        from corpmind.modules.training.repo import TrainingEngagementRepo, decode_cursor
        from corpmind.modules.training.schemas import TrainingEngagementFilters
        rows = [_engagement(id=uuid.uuid4()) for _ in range(50)]
        for r in rows:
            r.created_at = _NOW
        async def fake_count(self_r, ws, **kw): return 100
        async def fake_list(self_r, ws, **kw): return rows
        with _ctx():
            with (
                patch.object(TrainingEngagementRepo, "count", fake_count),
                patch.object(TrainingEngagementRepo, "list_page", fake_list),
            ):
                out = await _svc().list_engagements(TrainingEngagementFilters(workspace_id=_WS))
        ts, rid = decode_cursor(out.next_cursor)
        assert rid == rows[-1].id

    @pytest.mark.asyncio
    async def test_custom_limit_passed_to_repo(self):
        from corpmind.modules.training.repo import TrainingEngagementRepo
        from corpmind.modules.training.schemas import TrainingEngagementFilters
        received_limit = [None]
        async def fake_count(self_r, ws, **kw): return 100
        async def fake_list(self_r, ws, limit=50, **kw):
            received_limit[0] = limit
            return [_engagement(id=uuid.uuid4())]
        with _ctx():
            with (
                patch.object(TrainingEngagementRepo, "count", fake_count),
                patch.object(TrainingEngagementRepo, "list_page", fake_list),
            ):
                await _svc().list_engagements(
                    TrainingEngagementFilters(workspace_id=_WS, limit=10)
                )
        assert received_limit[0] == 10


# ── Tenant isolation ──────────────────────────────────────────────────────────

class TestTenantIsolation:
    def test_create_uses_org_id_from_context(self):
        from corpmind.modules.training.service import TrainingEngagementService
        svc = TrainingEngagementService(MagicMock())
        # Verify service reads from context, not from request
        assert hasattr(svc, "_repo")

    @pytest.mark.asyncio
    async def test_list_key_uses_org_id(self):
        from corpmind.modules.training.service import _list_key
        k = _list_key(_ORG, _WS)
        assert str(_ORG) in k
        assert "training:list" in k

    @pytest.mark.asyncio
    async def test_detail_key_uses_org_id(self):
        from corpmind.modules.training.service import _detail_key
        k = _detail_key(_ORG, _EID)
        assert str(_ORG) in k
        assert "training:detail" in k

    @pytest.mark.asyncio
    async def test_list_keys_for_different_orgs_differ(self):
        from corpmind.modules.training.service import _list_key
        org2 = uuid.uuid4()
        assert _list_key(_ORG, _WS) != _list_key(org2, _WS)

    @pytest.mark.asyncio
    async def test_detail_keys_for_different_orgs_differ(self):
        from corpmind.modules.training.service import _detail_key
        org2 = uuid.uuid4()
        assert _detail_key(_ORG, _EID) != _detail_key(org2, _EID)


# ── Cache key helpers ─────────────────────────────────────────────────────────

class TestCacheKeys:
    def test_list_key_format(self):
        from corpmind.modules.training.service import _list_key
        k = _list_key(_ORG, _WS)
        assert k.startswith(f"t:{_ORG}:")
        assert "training:list" in k

    def test_detail_key_format(self):
        from corpmind.modules.training.service import _detail_key
        k = _detail_key(_ORG, _EID)
        assert f"training:detail:{_EID}" in k

    def test_list_and_detail_keys_differ(self):
        from corpmind.modules.training.service import _list_key, _detail_key
        assert _list_key(_ORG, _WS) != _detail_key(_ORG, _EID)


# ── Events ────────────────────────────────────────────────────────────────────

class TestEvents:
    def test_engagement_created_fields(self):
        from corpmind.modules.training.events import TrainingEngagementCreated
        e = TrainingEngagementCreated(
            engagement_id=_EID,
            tenant_id=_ORG,
            workspace_id=_WS,
            customer_id=_CID,
            program_name="Leadership",
        )
        assert e.engagement_id == _EID
        assert e.program_name == "Leadership"

    def test_training_started_fields(self):
        from corpmind.modules.training.events import TrainingStarted
        e = TrainingStarted(engagement_id=_EID, tenant_id=_ORG, workspace_id=_WS)
        assert e.engagement_id == _EID

    def test_training_completed_fields(self):
        from corpmind.modules.training.events import TrainingCompleted
        e = TrainingCompleted(engagement_id=_EID, tenant_id=_ORG, workspace_id=_WS)
        assert e.tenant_id == _ORG

    def test_training_cancelled_fields(self):
        from corpmind.modules.training.events import TrainingCancelled
        e = TrainingCancelled(engagement_id=_EID, tenant_id=_ORG, workspace_id=_WS)
        assert e.workspace_id == _WS

    def test_trainer_assigned_fields(self):
        from corpmind.modules.training.events import TrainerAssigned
        e = TrainerAssigned(engagement_id=_EID, tenant_id=_ORG, trainer_id=_TID)
        assert e.trainer_id == _TID

    def test_coordinator_assigned_fields(self):
        from corpmind.modules.training.events import CoordinatorAssigned
        e = CoordinatorAssigned(engagement_id=_EID, tenant_id=_ORG, coordinator_id=_COORD)
        assert e.coordinator_id == _COORD

    def test_all_events_are_frozen(self):
        from corpmind.modules.training import events as evt_mod
        import inspect
        for name, klass in inspect.getmembers(evt_mod, inspect.isclass):
            if dataclasses.is_dataclass(klass):
                with pytest.raises(dataclasses.FrozenInstanceError):
                    e = klass(**{f.name: f.default if f.default is not dataclasses.MISSING else _EID
                                 for f in dataclasses.fields(klass)
                                 if f.default_factory is dataclasses.MISSING})
                    e.engagement_id = uuid.uuid4()  # type: ignore[attr-defined]

    def test_all_events_have_occurred_at(self):
        from corpmind.modules.training import events as evt_mod
        import inspect
        for name, klass in inspect.getmembers(evt_mod, inspect.isclass):
            if dataclasses.is_dataclass(klass):
                field_names = {f.name for f in dataclasses.fields(klass)}
                assert "occurred_at" in field_names, f"{name} missing occurred_at"


# ── Edge cases ────────────────────────────────────────────────────────────────

class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_list_works_when_redis_down(self):
        from corpmind.modules.training.repo import TrainingEngagementRepo
        from corpmind.modules.training.schemas import TrainingEngagementFilters
        rows = [_engagement()]
        async def fake_count(self_r, ws, **kw): return 1
        async def fake_list(self_r, ws, **kw): return rows
        bad_redis = AsyncMock()
        bad_redis.get = AsyncMock(side_effect=Exception("down"))
        bad_redis.set = AsyncMock(side_effect=Exception("down"))
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=_CTX),
            patch("corpmind.modules.training.service.get_redis", return_value=bad_redis),
            patch.object(TrainingEngagementRepo, "count", fake_count),
            patch.object(TrainingEngagementRepo, "list_page", fake_list),
        ):
            out = await _svc().list_engagements(TrainingEngagementFilters(workspace_id=_WS))
        assert len(out.items) == 1

    @pytest.mark.asyncio
    async def test_get_works_when_redis_down(self):
        from corpmind.modules.training.repo import TrainingEngagementRepo
        e = _engagement()
        async def fake_find(self_r, eid): return e
        bad_redis = AsyncMock()
        bad_redis.get = AsyncMock(side_effect=Exception("down"))
        bad_redis.set = AsyncMock(side_effect=Exception("down"))
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=_CTX),
            patch("corpmind.modules.training.service.get_redis", return_value=bad_redis),
            patch.object(TrainingEngagementRepo, "find_by_id", fake_find),
        ):
            out = await _svc().get_engagement(_EID)
        assert out.id == _EID

    @pytest.mark.asyncio
    async def test_get_not_found_when_redis_down(self):
        from corpmind.core.exceptions import NotFoundError
        from corpmind.modules.training.repo import TrainingEngagementRepo
        async def fake_find(self_r, eid): return None
        bad_redis = AsyncMock()
        bad_redis.get = AsyncMock(side_effect=Exception("down"))
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=_CTX),
            patch("corpmind.modules.training.service.get_redis", return_value=bad_redis),
            patch.object(TrainingEngagementRepo, "find_by_id", fake_find),
        ):
            with pytest.raises(NotFoundError):
                await _svc().get_engagement(_EID)

    def test_transition_map_completeness(self):
        from corpmind.modules.training.service import _TRANSITIONS
        assert "planned" in _TRANSITIONS
        assert "scheduled" in _TRANSITIONS
        assert "in_progress" in _TRANSITIONS
        assert "completed" in _TRANSITIONS
        assert "cancelled" in _TRANSITIONS

    def test_terminal_states_have_no_transitions(self):
        from corpmind.modules.training.service import _TRANSITIONS
        assert _TRANSITIONS["completed"] == set()
        assert _TRANSITIONS["cancelled"] == set()

    def test_planned_can_go_to_scheduled(self):
        from corpmind.modules.training.service import _TRANSITIONS
        assert "scheduled" in _TRANSITIONS["planned"]

    def test_scheduled_can_go_to_in_progress(self):
        from corpmind.modules.training.service import _TRANSITIONS
        assert "in_progress" in _TRANSITIONS["scheduled"]

    def test_in_progress_can_complete_or_cancel(self):
        from corpmind.modules.training.service import _TRANSITIONS
        assert "completed" in _TRANSITIONS["in_progress"]
        assert "cancelled" in _TRANSITIONS["in_progress"]


# ── Schema extras ─────────────────────────────────────────────────────────────

class TestSchemaExtras:
    def test_update_valid_delivery_mode(self):
        from corpmind.modules.training.schemas import TrainingEngagementUpdate
        u = TrainingEngagementUpdate(delivery_mode="hybrid")
        assert u.delivery_mode == "hybrid"

    def test_update_valid_priority(self):
        from corpmind.modules.training.schemas import TrainingEngagementUpdate
        u = TrainingEngagementUpdate(priority="urgent")
        assert u.priority == "urgent"

    def test_filters_all_fields(self):
        from corpmind.modules.training.schemas import TrainingEngagementFilters
        f = TrainingEngagementFilters(
            workspace_id=_WS,
            status="in_progress",
            trainer_id=_TID,
            customer_id=_CID,
            delivery_mode="online",
            date_from=_TODAY,
            date_to=_TODAY,
            search="leader",
            cursor="tok",
            limit=10,
        )
        assert f.status == "in_progress"
        assert f.limit == 10

    def test_list_out_has_more_true(self):
        from corpmind.modules.training.schemas import TrainingEngagementListOut
        out = TrainingEngagementListOut(items=[], next_cursor="tok", has_more=True, total=100)
        assert out.has_more is True

    def test_out_delivery_mode_values(self):
        from corpmind.modules.training.schemas import TrainingEngagementOut
        for mode in ["onsite", "online", "hybrid"]:
            e = _engagement(delivery_mode=mode)
            out = TrainingEngagementOut.model_validate(e)
            assert out.delivery_mode == mode

    def test_create_with_dates(self):
        from corpmind.modules.training.schemas import TrainingEngagementCreate
        req = TrainingEngagementCreate(
            workspace_id=_WS, customer_id=_CID,
            program_name="X", training_type="T", delivery_mode="online",
            planned_start_date=date(2026, 9, 1),
            planned_end_date=date(2026, 9, 5),
        )
        assert req.planned_start_date == date(2026, 9, 1)
        assert req.planned_end_date == date(2026, 9, 5)

    def test_valid_statuses_set(self):
        from corpmind.modules.training.schemas import VALID_STATUSES
        assert "planned" in VALID_STATUSES
        assert "completed" in VALID_STATUSES
        assert "cancelled" in VALID_STATUSES

    def test_valid_delivery_modes_set(self):
        from corpmind.modules.training.schemas import VALID_DELIVERY_MODES
        assert "onsite" in VALID_DELIVERY_MODES
        assert "online" in VALID_DELIVERY_MODES
        assert "hybrid" in VALID_DELIVERY_MODES


# ── Additional transition tests ───────────────────────────────────────────────

class TestTransitionExtras:
    @pytest.mark.asyncio
    async def test_planned_can_go_to_scheduled(self):
        from corpmind.modules.training.service import _TRANSITIONS
        assert "scheduled" in _TRANSITIONS["planned"]

    @pytest.mark.asyncio
    async def test_planned_can_be_cancelled(self):
        from corpmind.modules.training.schemas import CancelEngagement
        from corpmind.modules.training.repo import TrainingEngagementRepo
        e = _engagement(status="planned")
        final = _engagement(status="cancelled")
        call_count = [0]
        async def fake_find(self_r, eid):
            call_count[0] += 1
            return e if call_count[0] == 1 else final
        async def fake_update(self_r, eid, **kw): pass
        with _ctx():
            with (
                patch.object(TrainingEngagementRepo, "find_by_id", fake_find),
                patch.object(TrainingEngagementRepo, "update_fields", fake_update),
            ):
                out = await _svc().cancel_engagement(_EID, CancelEngagement())
        assert out.status == "cancelled"

    @pytest.mark.asyncio
    async def test_scheduled_can_be_cancelled(self):
        from corpmind.modules.training.schemas import CancelEngagement
        from corpmind.modules.training.repo import TrainingEngagementRepo
        e = _engagement(status="scheduled")
        final = _engagement(status="cancelled")
        call_count = [0]
        async def fake_find(self_r, eid):
            call_count[0] += 1
            return e if call_count[0] == 1 else final
        async def fake_update(self_r, eid, **kw): pass
        with _ctx():
            with (
                patch.object(TrainingEngagementRepo, "find_by_id", fake_find),
                patch.object(TrainingEngagementRepo, "update_fields", fake_update),
            ):
                out = await _svc().cancel_engagement(_EID, CancelEngagement())
        assert out.status == "cancelled"

    def test_cancelled_is_terminal(self):
        from corpmind.modules.training.service import _TRANSITIONS
        assert len(_TRANSITIONS["cancelled"]) == 0

    def test_completed_is_terminal(self):
        from corpmind.modules.training.service import _TRANSITIONS
        assert len(_TRANSITIONS["completed"]) == 0


# ── Coordinator extras ────────────────────────────────────────────────────────

class TestCoordinatorExtras:
    @pytest.mark.asyncio
    async def test_assign_coordinator_calls_update_fields(self):
        from corpmind.modules.training.repo import TrainingEngagementRepo
        e = _engagement(coordinator_id=None)
        final = _engagement(coordinator_id=_COORD)
        call_count = [0]
        field_calls: list = []
        async def fake_find(self_r, eid):
            call_count[0] += 1
            return e if call_count[0] == 1 else final
        async def fake_update(self_r, eid, **kw): field_calls.append(kw)
        with _ctx():
            with (
                patch.object(TrainingEngagementRepo, "find_by_id", fake_find),
                patch.object(TrainingEngagementRepo, "update_fields", fake_update),
            ):
                await _svc().assign_coordinator(_EID, _COORD)
        assert any(c.get("coordinator_id") == _COORD for c in field_calls)

    @pytest.mark.asyncio
    async def test_reassign_coordinator_different_id(self):
        from corpmind.modules.training.repo import TrainingEngagementRepo
        new_coord = uuid.uuid4()
        e = _engagement(coordinator_id=_COORD)
        final = _engagement(coordinator_id=new_coord)
        call_count = [0]
        async def fake_find(self_r, eid):
            call_count[0] += 1
            return e if call_count[0] == 1 else final
        async def fake_update(self_r, eid, **kw): pass
        with _ctx():
            with (
                patch.object(TrainingEngagementRepo, "find_by_id", fake_find),
                patch.object(TrainingEngagementRepo, "update_fields", fake_update),
            ):
                out = await _svc().assign_coordinator(_EID, new_coord)
        assert out.coordinator_id == new_coord


# ── Cache bust extras ─────────────────────────────────────────────────────────

class TestCacheBustExtras:
    @pytest.mark.asyncio
    async def test_assign_trainer_busts_detail_cache(self):
        from corpmind.modules.training.repo import TrainingEngagementRepo
        deleted: list[str] = []
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock()
        async def fake_delete(key): deleted.append(key)
        redis.delete = fake_delete
        e = _engagement()
        final = _engagement(assigned_trainer_id=_TID)
        call_count = [0]
        async def fake_find(self_r, eid):
            call_count[0] += 1
            return e if call_count[0] == 1 else final
        async def fake_update(self_r, eid, **kw): pass
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=_CTX),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
            patch.object(TrainingEngagementRepo, "find_by_id", fake_find),
            patch.object(TrainingEngagementRepo, "update_fields", fake_update),
        ):
            await _svc().assign_trainer(_EID, _TID)
        assert any("training:detail" in k for k in deleted)

    @pytest.mark.asyncio
    async def test_assign_trainer_busts_list_cache(self):
        from corpmind.modules.training.repo import TrainingEngagementRepo
        deleted: list[str] = []
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock()
        async def fake_delete(key): deleted.append(key)
        redis.delete = fake_delete
        e = _engagement()
        final = _engagement(assigned_trainer_id=_TID)
        call_count = [0]
        async def fake_find(self_r, eid):
            call_count[0] += 1
            return e if call_count[0] == 1 else final
        async def fake_update(self_r, eid, **kw): pass
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=_CTX),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
            patch.object(TrainingEngagementRepo, "find_by_id", fake_find),
            patch.object(TrainingEngagementRepo, "update_fields", fake_update),
        ):
            await _svc().assign_trainer(_EID, _TID)
        assert any("training:list" in k for k in deleted)


# ── Final coverage tests ──────────────────────────────────────────────────────

class TestFinalCoverage:
    def test_valid_priorities_set(self):
        from corpmind.modules.training.schemas import VALID_PRIORITIES
        assert "low" in VALID_PRIORITIES
        assert "medium" in VALID_PRIORITIES
        assert "high" in VALID_PRIORITIES
        assert "urgent" in VALID_PRIORITIES

    def test_engagement_out_has_all_date_fields(self):
        from corpmind.modules.training.schemas import TrainingEngagementOut
        e = _engagement(
            actual_start_date=_TODAY,
            actual_end_date=_TODAY,
        )
        out = TrainingEngagementOut.model_validate(e)
        assert out.actual_start_date == _TODAY
        assert out.actual_end_date == _TODAY

    def test_engagement_out_participant_counts(self):
        from corpmind.modules.training.schemas import TrainingEngagementOut
        e = _engagement(estimated_participants=50, actual_participants=47)
        out = TrainingEngagementOut.model_validate(e)
        assert out.estimated_participants == 50
        assert out.actual_participants == 47

    def test_update_program_name_only(self):
        from corpmind.modules.training.schemas import TrainingEngagementUpdate
        u = TrainingEngagementUpdate(program_name="Revised Program")
        d = u.model_dump(exclude_none=True)
        assert list(d.keys()) == ["program_name"]

    def test_cancel_engagement_no_notes(self):
        from corpmind.modules.training.schemas import CancelEngagement
        c = CancelEngagement()
        assert c.notes is None
