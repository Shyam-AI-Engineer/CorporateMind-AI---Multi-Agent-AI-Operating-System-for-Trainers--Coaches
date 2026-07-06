"""Append extra training tests to reach 120+."""
import pathlib

path = pathlib.Path(__file__).parent / "test_training_service.py"

extra = r"""

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
"""

with open(path, "a", encoding="utf-8") as f:
    f.write(extra)
print("ok")
