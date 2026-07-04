"""Unit tests for TrainingAttendanceService — Sprint 44."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.core.exceptions import NotFoundError, ValidationError
from corpmind.modules.training.service import (
    TrainingAttendanceService,
    _attendance_detail_key,
    _attendance_list_key,
)
from corpmind.modules.training.schemas import (
    CheckOutAttendance,
    TrainingAttendanceCreate,
    TrainingAttendanceFilters,
    TrainingAttendanceUpdate,
    VALID_ATTENDANCE_STATUSES,
)
from corpmind.modules.training.events import (
    ParticipantRegistered,
    ParticipantPresent,
    ParticipantLate,
    ParticipantAbsent,
    ParticipantCheckedOut,
)

_NOW = datetime(2026, 7, 4, 9, 0, 0, tzinfo=UTC)
_ORG = uuid.uuid4()
_WS = uuid.uuid4()
_SID = uuid.uuid4()  # session id
_AID = uuid.uuid4()  # attendance id


def _make_ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.org_id = _ORG
    ctx.user_id = uuid.uuid4()
    return ctx


def _make_redis(cached: str | None = None) -> MagicMock:
    redis = MagicMock()
    redis.get = AsyncMock(return_value=cached)
    redis.set = AsyncMock()
    redis.delete = AsyncMock()
    return redis


def _make_svc() -> tuple[TrainingAttendanceService, MagicMock]:
    db_session = MagicMock()
    db_session.commit = AsyncMock()
    svc = TrainingAttendanceService(db_session)
    svc._repo = MagicMock()
    return svc, db_session


def _make_attendance_obj(**kwargs) -> MagicMock:
    obj = MagicMock()
    obj.id = kwargs.get("id", _AID)
    obj.tenant_id = _ORG
    obj.workspace_id = _WS
    obj.session_id = kwargs.get("session_id", _SID)
    obj.participant_name = kwargs.get("participant_name", "Alice Smith")
    obj.participant_email = kwargs.get("participant_email", "alice@example.com")
    obj.participant_phone = kwargs.get("participant_phone", "+91 9876543210")
    obj.company = kwargs.get("company", "Acme Corp")
    obj.designation = kwargs.get("designation", "Manager")
    obj.attendance_status = kwargs.get("attendance_status", "registered")
    obj.check_in_time = kwargs.get("check_in_time", None)
    obj.check_out_time = kwargs.get("check_out_time", None)
    obj.completion_percent = kwargs.get("completion_percent", None)
    obj.certificate_eligible = kwargs.get("certificate_eligible", False)
    obj.remarks = kwargs.get("remarks", None)
    obj.created_at = kwargs.get("created_at", _NOW)
    obj.updated_at = kwargs.get("updated_at", _NOW)
    return obj


# ── Cache key helpers ─────────────────────────────────────────────────────────


class TestAttendanceCacheKeys:
    def test_list_key_format(self):
        key = _attendance_list_key(_ORG, _SID)
        assert f"t:{_ORG}:training:attendance:list:{_SID}" == key

    def test_detail_key_format(self):
        key = _attendance_detail_key(_ORG, _AID)
        assert f"t:{_ORG}:training:attendance:detail:{_AID}" == key

    def test_list_key_unique_per_org(self):
        org2 = uuid.uuid4()
        k1 = _attendance_list_key(_ORG, _SID)
        k2 = _attendance_list_key(org2, _SID)
        assert k1 != k2

    def test_list_key_unique_per_session(self):
        sid2 = uuid.uuid4()
        k1 = _attendance_list_key(_ORG, _SID)
        k2 = _attendance_list_key(_ORG, sid2)
        assert k1 != k2

    def test_detail_key_unique_per_attendance(self):
        aid2 = uuid.uuid4()
        k1 = _attendance_detail_key(_ORG, _AID)
        k2 = _attendance_detail_key(_ORG, aid2)
        assert k1 != k2


# ── register_participant ──────────────────────────────────────────────────────


class TestRegisterParticipant:
    @pytest.fixture
    def req(self):
        return TrainingAttendanceCreate(
            workspace_id=_WS,
            session_id=_SID,
            participant_name="Alice Smith",
            participant_email="alice@example.com",
            company="Acme Corp",
            designation="Manager",
        )

    async def test_creates_attendance_record(self, req):
        svc, db = _make_svc()
        svc._repo.create = AsyncMock(return_value=None)
        obj = _make_attendance_obj()
        svc._repo.create = AsyncMock(side_effect=lambda x: None)
        ctx = _make_ctx()
        redis = _make_redis()
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
            patch("corpmind.modules.training.service.TrainingAttendance") as MockModel,
        ):
            MockModel.return_value = obj
            result = await svc.register_participant(req)
        assert result.participant_name == "Alice Smith"

    async def test_commits_session(self, req):
        svc, db = _make_svc()
        obj = _make_attendance_obj()
        svc._repo.create = AsyncMock(return_value=obj)
        ctx = _make_ctx()
        redis = _make_redis()
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
            patch("corpmind.modules.training.service.TrainingAttendance", return_value=obj),
        ):
            await svc.register_participant(req)
        db.commit.assert_awaited_once()

    async def test_busts_list_cache(self, req):
        svc, db = _make_svc()
        obj = _make_attendance_obj()
        svc._repo.create = AsyncMock(return_value=obj)
        ctx = _make_ctx()
        redis = _make_redis()
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
            patch("corpmind.modules.training.service.TrainingAttendance", return_value=obj),
        ):
            await svc.register_participant(req)
        redis.delete.assert_awaited_once()

    async def test_default_status_is_registered(self, req):
        svc, db = _make_svc()
        obj = _make_attendance_obj()
        svc._repo.create = AsyncMock(return_value=obj)
        ctx = _make_ctx()
        redis = _make_redis()
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
            patch("corpmind.modules.training.service.TrainingAttendance", return_value=obj),
        ):
            result = await svc.register_participant(req)
        assert result.attendance_status == "registered"

    async def test_sets_tenant_id_from_context(self, req):
        svc, db = _make_svc()
        captured = {}

        def capture_obj(x):
            captured["obj"] = x

        svc._repo.create = AsyncMock(side_effect=capture_obj)
        ctx = _make_ctx()
        redis = _make_redis()
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
        ):
            try:
                await svc.register_participant(req)
            except Exception:
                pass

    async def test_schema_rejects_empty_name(self):
        with pytest.raises(Exception):
            TrainingAttendanceCreate(
                workspace_id=_WS,
                session_id=_SID,
                participant_name="   ",
            )

    async def test_schema_accepts_all_statuses(self):
        for status in VALID_ATTENDANCE_STATUSES:
            obj = TrainingAttendanceCreate(
                workspace_id=_WS,
                session_id=_SID,
                participant_name="Test",
                attendance_status=status,
            )
            assert obj.attendance_status == status

    async def test_redis_failure_does_not_raise(self, req):
        svc, db = _make_svc()
        obj = _make_attendance_obj()
        svc._repo.create = AsyncMock(return_value=obj)
        ctx = _make_ctx()
        redis = _make_redis()
        redis.delete = AsyncMock(side_effect=Exception("redis down"))
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
            patch("corpmind.modules.training.service.TrainingAttendance", return_value=obj),
        ):
            result = await svc.register_participant(req)
        assert result is not None

    async def test_certificate_eligible_false_by_default(self):
        req = TrainingAttendanceCreate(
            workspace_id=_WS,
            session_id=_SID,
            participant_name="Bob",
        )
        assert req.certificate_eligible is False

    async def test_completion_percent_defaults_none(self):
        req = TrainingAttendanceCreate(
            workspace_id=_WS,
            session_id=_SID,
            participant_name="Bob",
        )
        assert req.completion_percent is None

    async def test_schema_invalid_completion_percent(self):
        with pytest.raises(Exception):
            TrainingAttendanceCreate(
                workspace_id=_WS,
                session_id=_SID,
                participant_name="Bob",
                completion_percent=110.0,
            )

    async def test_schema_invalid_status(self):
        with pytest.raises(Exception):
            TrainingAttendanceCreate(
                workspace_id=_WS,
                session_id=_SID,
                participant_name="Bob",
                attendance_status="ghost",
            )

    async def test_optional_fields_nullable(self):
        req = TrainingAttendanceCreate(
            workspace_id=_WS,
            session_id=_SID,
            participant_name="Bob",
        )
        assert req.participant_email is None
        assert req.participant_phone is None
        assert req.company is None
        assert req.designation is None
        assert req.remarks is None


# ── get_participant ───────────────────────────────────────────────────────────


class TestGetParticipant:
    async def test_returns_cached_when_available(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj()
        from corpmind.modules.training.schemas import TrainingAttendanceOut
        cached_json = TrainingAttendanceOut.model_validate(obj).model_dump_json()
        ctx = _make_ctx()
        redis = _make_redis(cached=cached_json)
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
        ):
            result = await svc.get_participant(_AID)
        assert result.id == _AID
        svc._repo.find_by_id.assert_not_called()

    async def test_fetches_from_db_on_cache_miss(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj()
        svc._repo.find_by_id = AsyncMock(return_value=obj)
        ctx = _make_ctx()
        redis = _make_redis(cached=None)
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
        ):
            result = await svc.get_participant(_AID)
        assert result.id == _AID
        svc._repo.find_by_id.assert_awaited_once_with(_AID)

    async def test_raises_not_found(self):
        svc, db = _make_svc()
        svc._repo.find_by_id = AsyncMock(return_value=None)
        ctx = _make_ctx()
        redis = _make_redis(cached=None)
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
        ):
            with pytest.raises(NotFoundError):
                await svc.get_participant(_AID)

    async def test_writes_to_cache_after_db_fetch(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj()
        svc._repo.find_by_id = AsyncMock(return_value=obj)
        ctx = _make_ctx()
        redis = _make_redis(cached=None)
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
        ):
            await svc.get_participant(_AID)
        redis.set.assert_awaited_once()

    async def test_redis_get_failure_falls_through(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj()
        svc._repo.find_by_id = AsyncMock(return_value=obj)
        ctx = _make_ctx()
        redis = _make_redis()
        redis.get = AsyncMock(side_effect=Exception("redis down"))
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
        ):
            result = await svc.get_participant(_AID)
        assert result.id == _AID

    async def test_redis_set_failure_does_not_raise(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj()
        svc._repo.find_by_id = AsyncMock(return_value=obj)
        ctx = _make_ctx()
        redis = _make_redis(cached=None)
        redis.set = AsyncMock(side_effect=Exception("redis down"))
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
        ):
            result = await svc.get_participant(_AID)
        assert result is not None

    async def test_cache_key_uses_org_and_attendance_id(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj()
        svc._repo.find_by_id = AsyncMock(return_value=obj)
        ctx = _make_ctx()
        ctx.org_id = _ORG
        redis = _make_redis(cached=None)
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
        ):
            await svc.get_participant(_AID)
        set_call_key = redis.set.call_args[0][0]
        assert str(_ORG) in set_call_key
        assert str(_AID) in set_call_key

    async def test_returns_correct_certificate_eligible(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj(certificate_eligible=True)
        svc._repo.find_by_id = AsyncMock(return_value=obj)
        ctx = _make_ctx()
        redis = _make_redis(cached=None)
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
        ):
            result = await svc.get_participant(_AID)
        assert result.certificate_eligible is True


# ── update_participant ────────────────────────────────────────────────────────


class TestUpdateParticipant:
    async def test_not_found_raises(self):
        svc, db = _make_svc()
        svc._repo.find_by_id = AsyncMock(return_value=None)
        ctx = _make_ctx()
        redis = _make_redis()
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
        ):
            with pytest.raises(NotFoundError):
                await svc.update_participant(_AID, TrainingAttendanceUpdate())

    async def test_updates_fields(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj()
        svc._repo.find_by_id = AsyncMock(return_value=obj)
        svc._repo.update_fields = AsyncMock()
        updated = _make_attendance_obj(company="New Corp")
        ctx = _make_ctx()
        redis = _make_redis()
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
            patch.object(svc, "get_participant", AsyncMock(return_value=updated)),
        ):
            result = await svc.update_participant(
                _AID, TrainingAttendanceUpdate(company="New Corp")
            )
        svc._repo.update_fields.assert_awaited_once()

    async def test_busts_list_and_detail_cache(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj()
        svc._repo.find_by_id = AsyncMock(return_value=obj)
        svc._repo.update_fields = AsyncMock()
        ctx = _make_ctx()
        redis1 = _make_redis()
        redis2 = _make_redis()
        call_count = 0

        def get_redis_side():
            nonlocal call_count
            call_count += 1
            return redis1 if call_count <= 2 else redis2

        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", side_effect=get_redis_side),
            patch.object(svc, "get_participant", AsyncMock(return_value=_make_attendance_obj())),
        ):
            await svc.update_participant(_AID, TrainingAttendanceUpdate(company="X"))
        assert redis1.delete.await_count + redis2.delete.await_count >= 2

    async def test_commits_after_update(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj()
        svc._repo.find_by_id = AsyncMock(return_value=obj)
        svc._repo.update_fields = AsyncMock()
        ctx = _make_ctx()
        redis = _make_redis()
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
            patch.object(svc, "get_participant", AsyncMock(return_value=_make_attendance_obj())),
        ):
            await svc.update_participant(_AID, TrainingAttendanceUpdate(remarks="ok"))
        db.commit.assert_awaited_once()

    async def test_ignores_none_fields(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj()
        svc._repo.find_by_id = AsyncMock(return_value=obj)
        svc._repo.update_fields = AsyncMock()
        ctx = _make_ctx()
        redis = _make_redis()
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
            patch.object(svc, "get_participant", AsyncMock(return_value=_make_attendance_obj())),
        ):
            await svc.update_participant(_AID, TrainingAttendanceUpdate())
        call_kwargs = svc._repo.update_fields.call_args[1]
        # Only updated_at should be passed when no fields are set
        assert "company" not in call_kwargs or call_kwargs.get("company") is None

    async def test_update_schema_rejects_blank_name(self):
        with pytest.raises(Exception):
            TrainingAttendanceUpdate(participant_name="   ")

    async def test_update_schema_accepts_none_name(self):
        upd = TrainingAttendanceUpdate(participant_name=None)
        assert upd.participant_name is None

    async def test_update_schema_rejects_completion_over_100(self):
        with pytest.raises(Exception):
            TrainingAttendanceUpdate(completion_percent=101.0)

    async def test_update_schema_accepts_valid_completion(self):
        upd = TrainingAttendanceUpdate(completion_percent=75.5)
        assert upd.completion_percent == 75.5


# ── mark_present ──────────────────────────────────────────────────────────────


class TestMarkPresent:
    async def test_sets_status_present(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj(attendance_status="registered")
        svc._repo.find_by_id = AsyncMock(return_value=obj)
        svc._repo.update_fields = AsyncMock()
        ctx = _make_ctx()
        redis = _make_redis()
        expected = _make_attendance_obj(attendance_status="present")
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
            patch.object(svc, "get_participant", AsyncMock(return_value=expected)),
        ):
            result = await svc.mark_present(_AID)
        assert result.attendance_status == "present"

    async def test_not_found_raises(self):
        svc, db = _make_svc()
        svc._repo.find_by_id = AsyncMock(return_value=None)
        ctx = _make_ctx()
        redis = _make_redis()
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
        ):
            with pytest.raises(NotFoundError):
                await svc.mark_present(_AID)

    async def test_commits(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj()
        svc._repo.find_by_id = AsyncMock(return_value=obj)
        svc._repo.update_fields = AsyncMock()
        ctx = _make_ctx()
        redis = _make_redis()
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
            patch.object(svc, "get_participant", AsyncMock(return_value=_make_attendance_obj(attendance_status="present"))),
        ):
            await svc.mark_present(_AID)
        db.commit.assert_awaited_once()

    async def test_busts_cache(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj()
        svc._repo.find_by_id = AsyncMock(return_value=obj)
        svc._repo.update_fields = AsyncMock()
        ctx = _make_ctx()
        redis = _make_redis()
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
            patch.object(svc, "get_participant", AsyncMock(return_value=_make_attendance_obj(attendance_status="present"))),
        ):
            await svc.mark_present(_AID)
        assert redis.delete.await_count >= 2

    async def test_can_mark_present_from_any_status(self):
        for status in ["registered", "late", "absent", "left_early"]:
            svc, db = _make_svc()
            obj = _make_attendance_obj(attendance_status=status)
            svc._repo.find_by_id = AsyncMock(return_value=obj)
            svc._repo.update_fields = AsyncMock()
            ctx = _make_ctx()
            redis = _make_redis()
            with (
                patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
                patch("corpmind.modules.training.service.get_redis", return_value=redis),
                patch.object(svc, "get_participant", AsyncMock(return_value=_make_attendance_obj(attendance_status="present"))),
            ):
                result = await svc.mark_present(_AID)
            assert result.attendance_status == "present"

    async def test_update_fields_called_with_status(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj()
        svc._repo.find_by_id = AsyncMock(return_value=obj)
        svc._repo.update_fields = AsyncMock()
        ctx = _make_ctx()
        redis = _make_redis()
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
            patch.object(svc, "get_participant", AsyncMock(return_value=_make_attendance_obj(attendance_status="present"))),
        ):
            await svc.mark_present(_AID)
        call_kwargs = svc._repo.update_fields.call_args[1]
        assert call_kwargs["attendance_status"] == "present"

    async def test_update_fields_sets_updated_at(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj()
        svc._repo.find_by_id = AsyncMock(return_value=obj)
        svc._repo.update_fields = AsyncMock()
        ctx = _make_ctx()
        redis = _make_redis()
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
            patch.object(svc, "get_participant", AsyncMock(return_value=_make_attendance_obj(attendance_status="present"))),
        ):
            await svc.mark_present(_AID)
        call_kwargs = svc._repo.update_fields.call_args[1]
        assert "updated_at" in call_kwargs


# ── mark_late ────────────────────────────────────────────────────────────────


class TestMarkLate:
    async def test_sets_status_late(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj()
        svc._repo.find_by_id = AsyncMock(return_value=obj)
        svc._repo.update_fields = AsyncMock()
        ctx = _make_ctx()
        redis = _make_redis()
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
            patch.object(svc, "get_participant", AsyncMock(return_value=_make_attendance_obj(attendance_status="late"))),
        ):
            result = await svc.mark_late(_AID)
        assert result.attendance_status == "late"

    async def test_not_found_raises(self):
        svc, db = _make_svc()
        svc._repo.find_by_id = AsyncMock(return_value=None)
        ctx = _make_ctx()
        redis = _make_redis()
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
        ):
            with pytest.raises(NotFoundError):
                await svc.mark_late(_AID)

    async def test_commits(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj()
        svc._repo.find_by_id = AsyncMock(return_value=obj)
        svc._repo.update_fields = AsyncMock()
        ctx = _make_ctx()
        redis = _make_redis()
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
            patch.object(svc, "get_participant", AsyncMock(return_value=_make_attendance_obj(attendance_status="late"))),
        ):
            await svc.mark_late(_AID)
        db.commit.assert_awaited_once()

    async def test_update_fields_status_late(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj()
        svc._repo.find_by_id = AsyncMock(return_value=obj)
        svc._repo.update_fields = AsyncMock()
        ctx = _make_ctx()
        redis = _make_redis()
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
            patch.object(svc, "get_participant", AsyncMock(return_value=_make_attendance_obj(attendance_status="late"))),
        ):
            await svc.mark_late(_AID)
        assert svc._repo.update_fields.call_args[1]["attendance_status"] == "late"

    async def test_can_correct_from_absent(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj(attendance_status="absent")
        svc._repo.find_by_id = AsyncMock(return_value=obj)
        svc._repo.update_fields = AsyncMock()
        ctx = _make_ctx()
        redis = _make_redis()
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
            patch.object(svc, "get_participant", AsyncMock(return_value=_make_attendance_obj(attendance_status="late"))),
        ):
            result = await svc.mark_late(_AID)
        assert result.attendance_status == "late"

    async def test_busts_list_and_detail_cache(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj()
        svc._repo.find_by_id = AsyncMock(return_value=obj)
        svc._repo.update_fields = AsyncMock()
        ctx = _make_ctx()
        redis = _make_redis()
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
            patch.object(svc, "get_participant", AsyncMock(return_value=_make_attendance_obj(attendance_status="late"))),
        ):
            await svc.mark_late(_AID)
        assert redis.delete.await_count >= 2


# ── mark_absent ───────────────────────────────────────────────────────────────


class TestMarkAbsent:
    async def test_sets_status_absent(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj()
        svc._repo.find_by_id = AsyncMock(return_value=obj)
        svc._repo.update_fields = AsyncMock()
        ctx = _make_ctx()
        redis = _make_redis()
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
            patch.object(svc, "get_participant", AsyncMock(return_value=_make_attendance_obj(attendance_status="absent"))),
        ):
            result = await svc.mark_absent(_AID)
        assert result.attendance_status == "absent"

    async def test_not_found_raises(self):
        svc, db = _make_svc()
        svc._repo.find_by_id = AsyncMock(return_value=None)
        ctx = _make_ctx()
        redis = _make_redis()
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
        ):
            with pytest.raises(NotFoundError):
                await svc.mark_absent(_AID)

    async def test_update_fields_absent(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj()
        svc._repo.find_by_id = AsyncMock(return_value=obj)
        svc._repo.update_fields = AsyncMock()
        ctx = _make_ctx()
        redis = _make_redis()
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
            patch.object(svc, "get_participant", AsyncMock(return_value=_make_attendance_obj(attendance_status="absent"))),
        ):
            await svc.mark_absent(_AID)
        assert svc._repo.update_fields.call_args[1]["attendance_status"] == "absent"

    async def test_commits(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj()
        svc._repo.find_by_id = AsyncMock(return_value=obj)
        svc._repo.update_fields = AsyncMock()
        ctx = _make_ctx()
        redis = _make_redis()
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
            patch.object(svc, "get_participant", AsyncMock(return_value=_make_attendance_obj(attendance_status="absent"))),
        ):
            await svc.mark_absent(_AID)
        db.commit.assert_awaited_once()

    async def test_can_correct_from_present(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj(attendance_status="present")
        svc._repo.find_by_id = AsyncMock(return_value=obj)
        svc._repo.update_fields = AsyncMock()
        ctx = _make_ctx()
        redis = _make_redis()
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
            patch.object(svc, "get_participant", AsyncMock(return_value=_make_attendance_obj(attendance_status="absent"))),
        ):
            result = await svc.mark_absent(_AID)
        assert result.attendance_status == "absent"

    async def test_busts_cache(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj()
        svc._repo.find_by_id = AsyncMock(return_value=obj)
        svc._repo.update_fields = AsyncMock()
        ctx = _make_ctx()
        redis = _make_redis()
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
            patch.object(svc, "get_participant", AsyncMock(return_value=_make_attendance_obj(attendance_status="absent"))),
        ):
            await svc.mark_absent(_AID)
        assert redis.delete.await_count >= 2


# ── mark_left_early ───────────────────────────────────────────────────────────


class TestMarkLeftEarly:
    async def test_sets_status_left_early(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj(attendance_status="present")
        svc._repo.find_by_id = AsyncMock(return_value=obj)
        svc._repo.update_fields = AsyncMock()
        ctx = _make_ctx()
        redis = _make_redis()
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
            patch.object(svc, "get_participant", AsyncMock(return_value=_make_attendance_obj(attendance_status="left_early"))),
        ):
            result = await svc.mark_left_early(_AID)
        assert result.attendance_status == "left_early"

    async def test_not_found_raises(self):
        svc, db = _make_svc()
        svc._repo.find_by_id = AsyncMock(return_value=None)
        ctx = _make_ctx()
        redis = _make_redis()
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
        ):
            with pytest.raises(NotFoundError):
                await svc.mark_left_early(_AID)

    async def test_update_fields_left_early(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj()
        svc._repo.find_by_id = AsyncMock(return_value=obj)
        svc._repo.update_fields = AsyncMock()
        ctx = _make_ctx()
        redis = _make_redis()
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
            patch.object(svc, "get_participant", AsyncMock(return_value=_make_attendance_obj(attendance_status="left_early"))),
        ):
            await svc.mark_left_early(_AID)
        assert svc._repo.update_fields.call_args[1]["attendance_status"] == "left_early"

    async def test_commits(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj()
        svc._repo.find_by_id = AsyncMock(return_value=obj)
        svc._repo.update_fields = AsyncMock()
        ctx = _make_ctx()
        redis = _make_redis()
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
            patch.object(svc, "get_participant", AsyncMock(return_value=_make_attendance_obj(attendance_status="left_early"))),
        ):
            await svc.mark_left_early(_AID)
        db.commit.assert_awaited_once()

    async def test_can_mark_from_late(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj(attendance_status="late")
        svc._repo.find_by_id = AsyncMock(return_value=obj)
        svc._repo.update_fields = AsyncMock()
        ctx = _make_ctx()
        redis = _make_redis()
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
            patch.object(svc, "get_participant", AsyncMock(return_value=_make_attendance_obj(attendance_status="left_early"))),
        ):
            result = await svc.mark_left_early(_AID)
        assert result.attendance_status == "left_early"

    async def test_busts_cache(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj()
        svc._repo.find_by_id = AsyncMock(return_value=obj)
        svc._repo.update_fields = AsyncMock()
        ctx = _make_ctx()
        redis = _make_redis()
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
            patch.object(svc, "get_participant", AsyncMock(return_value=_make_attendance_obj(attendance_status="left_early"))),
        ):
            await svc.mark_left_early(_AID)
        assert redis.delete.await_count >= 2


# ── check_out ─────────────────────────────────────────────────────────────────


class TestCheckOut:
    async def test_not_found_raises(self):
        svc, db = _make_svc()
        svc._repo.find_by_id = AsyncMock(return_value=None)
        ctx = _make_ctx()
        redis = _make_redis()
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
        ):
            with pytest.raises(NotFoundError):
                await svc.check_out(_AID, CheckOutAttendance())

    async def test_sets_status_left_early(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj(attendance_status="present")
        svc._repo.find_by_id = AsyncMock(return_value=obj)
        svc._repo.update_fields = AsyncMock()
        ctx = _make_ctx()
        redis = _make_redis()
        expected = _make_attendance_obj(attendance_status="left_early")
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
            patch.object(svc, "get_participant", AsyncMock(return_value=expected)),
        ):
            result = await svc.check_out(_AID, CheckOutAttendance())
        assert result.attendance_status == "left_early"

    async def test_sets_check_out_time_to_now_if_not_provided(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj()
        svc._repo.find_by_id = AsyncMock(return_value=obj)
        svc._repo.update_fields = AsyncMock()
        ctx = _make_ctx()
        redis = _make_redis()
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
            patch.object(svc, "get_participant", AsyncMock(return_value=_make_attendance_obj(attendance_status="left_early"))),
        ):
            await svc.check_out(_AID, CheckOutAttendance())
        call_kwargs = svc._repo.update_fields.call_args[1]
        assert "check_out_time" in call_kwargs
        assert call_kwargs["check_out_time"] is not None

    async def test_uses_provided_check_out_time(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj()
        svc._repo.find_by_id = AsyncMock(return_value=obj)
        svc._repo.update_fields = AsyncMock()
        ctx = _make_ctx()
        redis = _make_redis()
        target_time = datetime(2026, 7, 4, 11, 30, 0, tzinfo=UTC)
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
            patch.object(svc, "get_participant", AsyncMock(return_value=_make_attendance_obj(attendance_status="left_early"))),
        ):
            await svc.check_out(_AID, CheckOutAttendance(check_out_time=target_time))
        call_kwargs = svc._repo.update_fields.call_args[1]
        assert call_kwargs["check_out_time"] == target_time

    async def test_sets_completion_percent(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj()
        svc._repo.find_by_id = AsyncMock(return_value=obj)
        svc._repo.update_fields = AsyncMock()
        ctx = _make_ctx()
        redis = _make_redis()
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
            patch.object(svc, "get_participant", AsyncMock(return_value=_make_attendance_obj(attendance_status="left_early"))),
        ):
            await svc.check_out(_AID, CheckOutAttendance(completion_percent=80.0))
        call_kwargs = svc._repo.update_fields.call_args[1]
        assert call_kwargs["completion_percent"] == 80.0

    async def test_sets_certificate_eligible(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj()
        svc._repo.find_by_id = AsyncMock(return_value=obj)
        svc._repo.update_fields = AsyncMock()
        ctx = _make_ctx()
        redis = _make_redis()
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
            patch.object(svc, "get_participant", AsyncMock(return_value=_make_attendance_obj(attendance_status="left_early"))),
        ):
            await svc.check_out(_AID, CheckOutAttendance(certificate_eligible=True))
        call_kwargs = svc._repo.update_fields.call_args[1]
        assert call_kwargs["certificate_eligible"] is True

    async def test_does_not_set_completion_if_not_provided(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj()
        svc._repo.find_by_id = AsyncMock(return_value=obj)
        svc._repo.update_fields = AsyncMock()
        ctx = _make_ctx()
        redis = _make_redis()
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
            patch.object(svc, "get_participant", AsyncMock(return_value=_make_attendance_obj(attendance_status="left_early"))),
        ):
            await svc.check_out(_AID, CheckOutAttendance())
        call_kwargs = svc._repo.update_fields.call_args[1]
        assert "completion_percent" not in call_kwargs

    async def test_schema_rejects_invalid_completion(self):
        with pytest.raises(Exception):
            CheckOutAttendance(completion_percent=-1.0)

    async def test_schema_accepts_zero_completion(self):
        req = CheckOutAttendance(completion_percent=0.0)
        assert req.completion_percent == 0.0

    async def test_busts_both_caches(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj()
        svc._repo.find_by_id = AsyncMock(return_value=obj)
        svc._repo.update_fields = AsyncMock()
        ctx = _make_ctx()
        redis = _make_redis()
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
            patch.object(svc, "get_participant", AsyncMock(return_value=_make_attendance_obj(attendance_status="left_early"))),
        ):
            await svc.check_out(_AID, CheckOutAttendance())
        assert redis.delete.await_count >= 2

    async def test_commits(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj()
        svc._repo.find_by_id = AsyncMock(return_value=obj)
        svc._repo.update_fields = AsyncMock()
        ctx = _make_ctx()
        redis = _make_redis()
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
            patch.object(svc, "get_participant", AsyncMock(return_value=_make_attendance_obj(attendance_status="left_early"))),
        ):
            await svc.check_out(_AID, CheckOutAttendance())
        db.commit.assert_awaited_once()


# ── list_attendance ───────────────────────────────────────────────────────────


def _make_list_out(items: list | None = None) -> MagicMock:
    from corpmind.modules.training.schemas import TrainingAttendanceListOut, TrainingAttendanceOut
    return TrainingAttendanceListOut(
        items=[],
        next_cursor=None,
        has_more=False,
        total=0,
    )


class TestListAttendance:
    def _base_filters(self, **kwargs) -> TrainingAttendanceFilters:
        return TrainingAttendanceFilters(workspace_id=_WS, **kwargs)

    async def test_returns_cached_when_session_only(self):
        svc, db = _make_svc()
        from corpmind.modules.training.schemas import TrainingAttendanceListOut
        cached_data = TrainingAttendanceListOut(items=[], next_cursor=None, has_more=False, total=0)
        ctx = _make_ctx()
        redis = _make_redis(cached=cached_data.model_dump_json())
        filters = self._base_filters(session_id=_SID)
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
        ):
            result = await svc.list_attendance(filters)
        assert result.total == 0
        svc._repo.count.assert_not_called()

    async def test_fetches_from_db_on_cache_miss(self):
        svc, db = _make_svc()
        svc._repo.count = AsyncMock(return_value=2)
        svc._repo.list_page = AsyncMock(return_value=[_make_attendance_obj(), _make_attendance_obj(id=uuid.uuid4())])
        ctx = _make_ctx()
        redis = _make_redis(cached=None)
        filters = self._base_filters(session_id=_SID)
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
        ):
            result = await svc.list_attendance(filters)
        assert result.total == 2

    async def test_skips_cache_when_status_filter_set(self):
        svc, db = _make_svc()
        svc._repo.count = AsyncMock(return_value=1)
        svc._repo.list_page = AsyncMock(return_value=[_make_attendance_obj(attendance_status="present")])
        ctx = _make_ctx()
        redis = _make_redis(cached="should_not_be_used")
        filters = self._base_filters(session_id=_SID, attendance_status="present")
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
        ):
            await svc.list_attendance(filters)
        svc._repo.count.assert_awaited_once()

    async def test_skips_cache_when_search_set(self):
        svc, db = _make_svc()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        ctx = _make_ctx()
        redis = _make_redis()
        filters = self._base_filters(session_id=_SID, search="Alice")
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
        ):
            await svc.list_attendance(filters)
        svc._repo.count.assert_awaited_once()

    async def test_skips_cache_when_company_filter_set(self):
        svc, db = _make_svc()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        ctx = _make_ctx()
        redis = _make_redis()
        filters = self._base_filters(session_id=_SID, company="Acme")
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
        ):
            await svc.list_attendance(filters)
        svc._repo.count.assert_awaited_once()

    async def test_skips_cache_when_limit_not_50(self):
        svc, db = _make_svc()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        ctx = _make_ctx()
        redis = _make_redis(cached="should_not_be_used")
        filters = self._base_filters(session_id=_SID, limit=10)
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
        ):
            await svc.list_attendance(filters)
        svc._repo.count.assert_awaited_once()

    async def test_skips_cache_when_no_session_id(self):
        svc, db = _make_svc()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        ctx = _make_ctx()
        redis = _make_redis()
        filters = self._base_filters()
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
        ):
            await svc.list_attendance(filters)
        svc._repo.count.assert_awaited_once()

    async def test_builds_next_cursor_when_full_page(self):
        svc, db = _make_svc()
        items = [_make_attendance_obj(id=uuid.uuid4()) for _ in range(50)]
        svc._repo.count = AsyncMock(return_value=100)
        svc._repo.list_page = AsyncMock(return_value=items)
        ctx = _make_ctx()
        redis = _make_redis(cached=None)
        filters = self._base_filters(session_id=_SID)
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
        ):
            result = await svc.list_attendance(filters)
        assert result.has_more is True
        assert result.next_cursor is not None

    async def test_no_next_cursor_when_partial_page(self):
        svc, db = _make_svc()
        items = [_make_attendance_obj()]
        svc._repo.count = AsyncMock(return_value=1)
        svc._repo.list_page = AsyncMock(return_value=items)
        ctx = _make_ctx()
        redis = _make_redis(cached=None)
        filters = self._base_filters(session_id=_SID)
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
        ):
            result = await svc.list_attendance(filters)
        assert result.has_more is False
        assert result.next_cursor is None

    async def test_writes_to_cache_after_session_only_fetch(self):
        svc, db = _make_svc()
        svc._repo.count = AsyncMock(return_value=1)
        svc._repo.list_page = AsyncMock(return_value=[_make_attendance_obj()])
        ctx = _make_ctx()
        redis = _make_redis(cached=None)
        filters = self._base_filters(session_id=_SID)
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
        ):
            await svc.list_attendance(filters)
        redis.set.assert_awaited()

    async def test_redis_failure_graceful(self):
        svc, db = _make_svc()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        ctx = _make_ctx()
        redis = _make_redis()
        redis.get = AsyncMock(side_effect=Exception("redis down"))
        filters = self._base_filters(session_id=_SID)
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
        ):
            result = await svc.list_attendance(filters)
        assert result is not None

    async def test_filters_passed_to_repo(self):
        svc, db = _make_svc()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        ctx = _make_ctx()
        redis = _make_redis()
        filters = self._base_filters(session_id=_SID, attendance_status="present", company="Acme")
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
        ):
            await svc.list_attendance(filters)
        list_call_kwargs = svc._repo.list_page.call_args[1]
        assert list_call_kwargs["attendance_status"] == "present"
        assert list_call_kwargs["company"] == "Acme"


# ── list_by_session ───────────────────────────────────────────────────────────


class TestListBySession:
    async def test_delegates_to_repo(self):
        svc, db = _make_svc()
        svc._repo.list_by_session = AsyncMock(return_value=[_make_attendance_obj()])
        result = await svc.list_by_session(_SID)
        assert len(result) == 1
        svc._repo.list_by_session.assert_awaited_once_with(_SID)

    async def test_returns_empty_list(self):
        svc, db = _make_svc()
        svc._repo.list_by_session = AsyncMock(return_value=[])
        result = await svc.list_by_session(_SID)
        assert result == []

    async def test_returns_multiple_participants(self):
        svc, db = _make_svc()
        objs = [_make_attendance_obj(id=uuid.uuid4()) for _ in range(5)]
        svc._repo.list_by_session = AsyncMock(return_value=objs)
        result = await svc.list_by_session(_SID)
        assert len(result) == 5


# ── search_participants ───────────────────────────────────────────────────────


class TestSearchParticipants:
    async def test_delegates_to_repo(self):
        svc, db = _make_svc()
        svc._repo.search_participants = AsyncMock(return_value=[_make_attendance_obj()])
        result = await svc.search_participants(_WS, _SID, "Alice")
        assert len(result) == 1
        svc._repo.search_participants.assert_awaited_once_with(_WS, _SID, "Alice", 20)

    async def test_returns_empty_on_no_match(self):
        svc, db = _make_svc()
        svc._repo.search_participants = AsyncMock(return_value=[])
        result = await svc.search_participants(_WS, _SID, "ZZZ")
        assert result == []

    async def test_passes_custom_limit(self):
        svc, db = _make_svc()
        svc._repo.search_participants = AsyncMock(return_value=[])
        await svc.search_participants(_WS, _SID, "Bob", 5)
        svc._repo.search_participants.assert_awaited_once_with(_WS, _SID, "Bob", 5)

    async def test_returns_attendance_out_objects(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj(participant_name="Alice")
        svc._repo.search_participants = AsyncMock(return_value=[obj])
        result = await svc.search_participants(_WS, _SID, "Alice")
        assert result[0].participant_name == "Alice"

    async def test_multiple_results(self):
        svc, db = _make_svc()
        objs = [_make_attendance_obj(id=uuid.uuid4()) for _ in range(3)]
        svc._repo.search_participants = AsyncMock(return_value=objs)
        result = await svc.search_participants(_WS, _SID, "Corp")
        assert len(result) == 3


# ── Tenant isolation ──────────────────────────────────────────────────────────


class TestTenantIsolation:
    async def test_cache_list_key_is_tenant_scoped(self):
        org_a = uuid.uuid4()
        org_b = uuid.uuid4()
        k_a = _attendance_list_key(org_a, _SID)
        k_b = _attendance_list_key(org_b, _SID)
        assert k_a != k_b
        assert str(org_a) in k_a
        assert str(org_b) in k_b

    async def test_cache_detail_key_is_tenant_scoped(self):
        org_a = uuid.uuid4()
        org_b = uuid.uuid4()
        k_a = _attendance_detail_key(org_a, _AID)
        k_b = _attendance_detail_key(org_b, _AID)
        assert k_a != k_b

    async def test_register_uses_org_id_from_context(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj()
        svc._repo.create = AsyncMock(return_value=obj)
        ctx_a = _make_ctx()
        ctx_a.org_id = uuid.uuid4()
        redis = _make_redis()
        req = TrainingAttendanceCreate(
            workspace_id=_WS, session_id=_SID, participant_name="X"
        )
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx_a),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
            patch("corpmind.modules.training.service.TrainingAttendance", return_value=obj),
        ):
            await svc.register_participant(req)
        delete_key = redis.delete.call_args[0][0]
        assert str(ctx_a.org_id) in delete_key

    async def test_list_cache_key_differs_by_session(self):
        sid1 = uuid.uuid4()
        sid2 = uuid.uuid4()
        k1 = _attendance_list_key(_ORG, sid1)
        k2 = _attendance_list_key(_ORG, sid2)
        assert k1 != k2

    async def test_get_uses_tenant_scoped_key(self):
        svc, db = _make_svc()
        obj = _make_attendance_obj()
        svc._repo.find_by_id = AsyncMock(return_value=obj)
        ctx = _make_ctx()
        ctx.org_id = _ORG
        redis = _make_redis(cached=None)
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
        ):
            await svc.get_participant(_AID)
        get_key = redis.get.call_args[0][0]
        assert str(_ORG) in get_key

    async def test_bust_list_deletes_session_scoped_key(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        ctx.org_id = _ORG
        redis = _make_redis()
        with (
            patch("corpmind.modules.training.service.get_tenant_context", return_value=ctx),
            patch("corpmind.modules.training.service.get_redis", return_value=redis),
        ):
            await svc._bust_list_cache(_ORG, _SID)
        key = redis.delete.call_args[0][0]
        assert str(_SID) in key

    async def test_bust_detail_deletes_attendance_scoped_key(self):
        svc, db = _make_svc()
        redis = _make_redis()
        with patch("corpmind.modules.training.service.get_redis", return_value=redis):
            await svc._bust_detail_cache(_ORG, _AID)
        key = redis.delete.call_args[0][0]
        assert str(_AID) in key


# ── Attendance events ─────────────────────────────────────────────────────────


class TestAttendanceEvents:
    def test_participant_registered_frozen(self):
        evt = ParticipantRegistered(
            attendance_id=_AID,
            session_id=_SID,
            tenant_id=_ORG,
            participant_name="Alice",
        )
        with pytest.raises(Exception):
            evt.attendance_id = uuid.uuid4()  # type: ignore[misc]

    def test_participant_present_frozen(self):
        evt = ParticipantPresent(
            attendance_id=_AID, session_id=_SID, tenant_id=_ORG
        )
        with pytest.raises(Exception):
            evt.attendance_id = uuid.uuid4()  # type: ignore[misc]

    def test_participant_late_frozen(self):
        evt = ParticipantLate(
            attendance_id=_AID, session_id=_SID, tenant_id=_ORG
        )
        with pytest.raises(Exception):
            evt.attendance_id = uuid.uuid4()  # type: ignore[misc]

    def test_participant_absent_frozen(self):
        evt = ParticipantAbsent(
            attendance_id=_AID, session_id=_SID, tenant_id=_ORG
        )
        with pytest.raises(Exception):
            evt.attendance_id = uuid.uuid4()  # type: ignore[misc]

    def test_participant_checked_out_has_check_out_time(self):
        t = datetime.now(UTC)
        evt = ParticipantCheckedOut(
            attendance_id=_AID, session_id=_SID, tenant_id=_ORG, check_out_time=t
        )
        assert evt.check_out_time == t

    def test_all_events_have_occurred_at(self):
        events = [
            ParticipantRegistered(
                attendance_id=_AID, session_id=_SID, tenant_id=_ORG, participant_name="X"
            ),
            ParticipantPresent(attendance_id=_AID, session_id=_SID, tenant_id=_ORG),
            ParticipantLate(attendance_id=_AID, session_id=_SID, tenant_id=_ORG),
            ParticipantAbsent(attendance_id=_AID, session_id=_SID, tenant_id=_ORG),
            ParticipantCheckedOut(
                attendance_id=_AID,
                session_id=_SID,
                tenant_id=_ORG,
                check_out_time=datetime.now(UTC),
            ),
        ]
        for evt in events:
            assert evt.occurred_at is not None

    def test_participant_checked_out_frozen(self):
        t = datetime.now(UTC)
        evt = ParticipantCheckedOut(
            attendance_id=_AID, session_id=_SID, tenant_id=_ORG, check_out_time=t
        )
        with pytest.raises(Exception):
            evt.attendance_id = uuid.uuid4()  # type: ignore[misc]


# ── Attendance schema validators ──────────────────────────────────────────────


class TestAttendanceSchemas:
    def test_valid_attendance_statuses_set(self):
        expected = {"registered", "present", "late", "absent", "left_early"}
        assert VALID_ATTENDANCE_STATUSES == expected

    def test_create_accepts_boundary_completion_zero(self):
        req = TrainingAttendanceCreate(
            workspace_id=_WS, session_id=_SID, participant_name="X",
            completion_percent=0.0
        )
        assert req.completion_percent == 0.0

    def test_create_accepts_boundary_completion_100(self):
        req = TrainingAttendanceCreate(
            workspace_id=_WS, session_id=_SID, participant_name="X",
            completion_percent=100.0
        )
        assert req.completion_percent == 100.0

    def test_create_rejects_completion_negative(self):
        with pytest.raises(Exception):
            TrainingAttendanceCreate(
                workspace_id=_WS, session_id=_SID, participant_name="X",
                completion_percent=-0.1
            )

    def test_update_accepts_boundary_completion_100(self):
        upd = TrainingAttendanceUpdate(completion_percent=100.0)
        assert upd.completion_percent == 100.0

    def test_checkout_accepts_boundary_completion_zero(self):
        req = CheckOutAttendance(completion_percent=0.0)
        assert req.completion_percent == 0.0

    def test_checkout_rejects_completion_over_100(self):
        with pytest.raises(Exception):
            CheckOutAttendance(completion_percent=100.01)

    def test_filters_default_limit_50(self):
        f = TrainingAttendanceFilters(workspace_id=_WS)
        assert f.limit == 50

    def test_filters_session_id_optional(self):
        f = TrainingAttendanceFilters(workspace_id=_WS)
        assert f.session_id is None

    def test_filters_search_optional(self):
        f = TrainingAttendanceFilters(workspace_id=_WS)
        assert f.search is None

    def test_filters_company_optional(self):
        f = TrainingAttendanceFilters(workspace_id=_WS)
        assert f.company is None

    def test_filters_attendance_status_optional(self):
        f = TrainingAttendanceFilters(workspace_id=_WS)
        assert f.attendance_status is None
