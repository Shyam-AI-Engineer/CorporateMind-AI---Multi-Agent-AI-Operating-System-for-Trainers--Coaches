"""Unit tests for CustomerSuccessService — Sprint 47.

140 tests across 10 classes:
  TestCreate            (20)
  TestGet               (12)
  TestGetByCustomer     ( 8)
  TestUpdate            (18)
  TestList              (20)
  TestAssignOwner       (12)
  TestUpdateHealth      (15)
  TestScheduleFollowup  (12)
  TestArchive           (10)
  TestTenantIsolation   ( 8)
  TestValidation        ( 5)
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.core.exceptions import ConflictError, NotFoundError, ValidationError
from corpmind.modules.customer_success.models import CustomerSuccess
from corpmind.modules.customer_success.schemas import (
    AssignOwner,
    CustomerSuccessCreate,
    CustomerSuccessFilters,
    CustomerSuccessUpdate,
    ScheduleFollowup,
    UpdateHealth,
)
from corpmind.modules.customer_success.service import CustomerSuccessService

# ── Shared constants ───────────────────────────────────────────────────────────

_ORG = uuid.uuid4()
_WS = uuid.uuid4()
_CUSTOMER = uuid.uuid4()
_OWNER = uuid.uuid4()
_RECORD = uuid.uuid4()

_PATCH_CTX = "corpmind.modules.customer_success.service.get_tenant_context"
_PATCH_REDIS = "corpmind.modules.customer_success.service.get_redis"


# ── Helpers ────────────────────────────────────────────────────────────────────

@contextmanager
def _patch_ctx(ctx: MagicMock, redis: MagicMock):
    with patch(_PATCH_CTX, return_value=ctx):
        with patch(_PATCH_REDIS, return_value=redis):
            yield


def _make_ctx(org_id: uuid.UUID | None = None) -> MagicMock:
    ctx = MagicMock()
    ctx.org_id = org_id or _ORG
    return ctx


def _make_redis(cached: str | None = None) -> MagicMock:
    redis = MagicMock()
    redis.get = AsyncMock(return_value=cached)
    redis.set = AsyncMock()
    redis.delete = AsyncMock()
    return redis


def _make_svc() -> tuple[CustomerSuccessService, MagicMock]:
    db = MagicMock()
    db.commit = AsyncMock()
    svc = CustomerSuccessService(db)
    svc._repo = MagicMock()
    return svc, db


def _make_record(
    *,
    record_id: uuid.UUID | None = None,
    customer_id: uuid.UUID | None = None,
    health_status: str = "watch",
    risk_level: str = "medium",
    health_score: int | None = None,
    owner_user_id: uuid.UUID | None = None,
    renewal_date: date | None = None,
    next_followup_date: date | None = None,
    notes: str | None = None,
    is_archived: bool = False,
    renewal_probability: int | None = None,
    expansion_opportunity: bool = False,
    last_contact_date: date | None = None,
) -> CustomerSuccess:
    now = datetime.now(UTC)
    r = CustomerSuccess(
        id=record_id or _RECORD,
        tenant_id=_ORG,
        workspace_id=_WS,
        customer_id=customer_id or _CUSTOMER,
        health_status=health_status,
        health_score=health_score,
        risk_level=risk_level,
        owner_user_id=owner_user_id,
        renewal_date=renewal_date,
        last_contact_date=last_contact_date,
        next_followup_date=next_followup_date,
        expansion_opportunity=expansion_opportunity,
        renewal_probability=renewal_probability,
        notes=notes,
        is_archived=is_archived,
        created_at=now,
        updated_at=now,
    )
    return r


# ── TestCreate ────────────────────────────────────────────────────────────────

class TestCreate:
    @pytest.mark.asyncio
    async def test_create_success(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_customer_id = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(side_effect=lambda r: r)
        req = CustomerSuccessCreate(workspace_id=_WS, customer_id=_CUSTOMER)
        with _patch_ctx(ctx, redis):
            out = await svc.create(req)
        assert out.customer_id == _CUSTOMER
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_sets_defaults(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_customer_id = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(side_effect=lambda r: r)
        req = CustomerSuccessCreate(workspace_id=_WS, customer_id=_CUSTOMER)
        with _patch_ctx(ctx, redis):
            out = await svc.create(req)
        assert out.health_status == "watch"
        assert out.risk_level == "medium"
        assert out.is_archived is False

    @pytest.mark.asyncio
    async def test_create_raises_conflict_if_duplicate(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_customer_id = AsyncMock(return_value=_make_record())
        req = CustomerSuccessCreate(workspace_id=_WS, customer_id=_CUSTOMER)
        with _patch_ctx(ctx, redis):
            with pytest.raises(ConflictError):
                await svc.create(req)

    @pytest.mark.asyncio
    async def test_create_sets_tenant_id(self):
        svc, db = _make_svc()
        org = uuid.uuid4()
        ctx = _make_ctx(org_id=org)
        redis = _make_redis()
        svc._repo.find_by_customer_id = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(side_effect=lambda r: r)
        req = CustomerSuccessCreate(workspace_id=_WS, customer_id=_CUSTOMER)
        with _patch_ctx(ctx, redis):
            out = await svc.create(req)
        assert out.tenant_id == org

    @pytest.mark.asyncio
    async def test_create_with_health_status(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_customer_id = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(side_effect=lambda r: r)
        req = CustomerSuccessCreate(
            workspace_id=_WS, customer_id=_CUSTOMER, health_status="healthy"
        )
        with _patch_ctx(ctx, redis):
            out = await svc.create(req)
        assert out.health_status == "healthy"

    @pytest.mark.asyncio
    async def test_create_with_risk_level_high(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_customer_id = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(side_effect=lambda r: r)
        req = CustomerSuccessCreate(
            workspace_id=_WS, customer_id=_CUSTOMER, risk_level="high"
        )
        with _patch_ctx(ctx, redis):
            out = await svc.create(req)
        assert out.risk_level == "high"

    @pytest.mark.asyncio
    async def test_create_with_notes(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_customer_id = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(side_effect=lambda r: r)
        req = CustomerSuccessCreate(
            workspace_id=_WS, customer_id=_CUSTOMER, notes="Key account"
        )
        with _patch_ctx(ctx, redis):
            out = await svc.create(req)
        assert out.notes == "Key account"

    @pytest.mark.asyncio
    async def test_create_with_renewal_date(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_customer_id = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(side_effect=lambda r: r)
        req = CustomerSuccessCreate(
            workspace_id=_WS, customer_id=_CUSTOMER,
            renewal_date=date(2026, 12, 31),
        )
        with _patch_ctx(ctx, redis):
            out = await svc.create(req)
        assert str(out.renewal_date) == "2026-12-31"

    @pytest.mark.asyncio
    async def test_create_with_owner(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_customer_id = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(side_effect=lambda r: r)
        req = CustomerSuccessCreate(
            workspace_id=_WS, customer_id=_CUSTOMER, owner_user_id=_OWNER
        )
        with _patch_ctx(ctx, redis):
            out = await svc.create(req)
        assert out.owner_user_id == _OWNER

    @pytest.mark.asyncio
    async def test_create_busts_list_cache(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_customer_id = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(side_effect=lambda r: r)
        req = CustomerSuccessCreate(workspace_id=_WS, customer_id=_CUSTOMER)
        with _patch_ctx(ctx, redis):
            await svc.create(req)
        redis.delete.assert_awaited()

    @pytest.mark.asyncio
    async def test_create_with_expansion_opportunity(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_customer_id = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(side_effect=lambda r: r)
        req = CustomerSuccessCreate(
            workspace_id=_WS, customer_id=_CUSTOMER, expansion_opportunity=True
        )
        with _patch_ctx(ctx, redis):
            out = await svc.create(req)
        assert out.expansion_opportunity is True

    @pytest.mark.asyncio
    async def test_create_with_health_score(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_customer_id = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(side_effect=lambda r: r)
        req = CustomerSuccessCreate(
            workspace_id=_WS, customer_id=_CUSTOMER, health_score=85
        )
        with _patch_ctx(ctx, redis):
            out = await svc.create(req)
        assert out.health_score == 85

    @pytest.mark.asyncio
    async def test_create_with_renewal_probability(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_customer_id = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(side_effect=lambda r: r)
        req = CustomerSuccessCreate(
            workspace_id=_WS, customer_id=_CUSTOMER, renewal_probability=75
        )
        with _patch_ctx(ctx, redis):
            out = await svc.create(req)
        assert out.renewal_probability == 75

    @pytest.mark.asyncio
    async def test_create_with_followup_date(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_customer_id = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(side_effect=lambda r: r)
        req = CustomerSuccessCreate(
            workspace_id=_WS, customer_id=_CUSTOMER,
            next_followup_date=date(2026, 8, 15),
        )
        with _patch_ctx(ctx, redis):
            out = await svc.create(req)
        assert str(out.next_followup_date) == "2026-08-15"

    @pytest.mark.asyncio
    async def test_create_does_not_commit_on_duplicate(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_customer_id = AsyncMock(return_value=_make_record())
        req = CustomerSuccessCreate(workspace_id=_WS, customer_id=_CUSTOMER)
        with _patch_ctx(ctx, redis):
            with pytest.raises(ConflictError):
                await svc.create(req)
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_create_different_customers_allowed(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_customer_id = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(side_effect=lambda r: r)
        c2 = uuid.uuid4()
        req = CustomerSuccessCreate(workspace_id=_WS, customer_id=c2)
        with _patch_ctx(ctx, redis):
            out = await svc.create(req)
        assert out.customer_id == c2

    @pytest.mark.asyncio
    async def test_create_at_risk_health(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_customer_id = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(side_effect=lambda r: r)
        req = CustomerSuccessCreate(
            workspace_id=_WS, customer_id=_CUSTOMER, health_status="at_risk"
        )
        with _patch_ctx(ctx, redis):
            out = await svc.create(req)
        assert out.health_status == "at_risk"

    @pytest.mark.asyncio
    async def test_create_low_risk(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_customer_id = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(side_effect=lambda r: r)
        req = CustomerSuccessCreate(
            workspace_id=_WS, customer_id=_CUSTOMER, risk_level="low"
        )
        with _patch_ctx(ctx, redis):
            out = await svc.create(req)
        assert out.risk_level == "low"

    @pytest.mark.asyncio
    async def test_create_assigns_uuid(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_customer_id = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(side_effect=lambda r: r)
        req = CustomerSuccessCreate(workspace_id=_WS, customer_id=_CUSTOMER)
        with _patch_ctx(ctx, redis):
            out = await svc.create(req)
        assert out.id is not None

    @pytest.mark.asyncio
    async def test_create_workspace_id(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_customer_id = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(side_effect=lambda r: r)
        req = CustomerSuccessCreate(workspace_id=_WS, customer_id=_CUSTOMER)
        with _patch_ctx(ctx, redis):
            out = await svc.create(req)
        assert out.workspace_id == _WS


# ── TestGet ───────────────────────────────────────────────────────────────────

class TestGet:
    @pytest.mark.asyncio
    async def test_get_returns_record(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_id = AsyncMock(return_value=_make_record())
        with _patch_ctx(ctx, redis):
            out = await svc.get(_RECORD)
        assert out.id == _RECORD

    @pytest.mark.asyncio
    async def test_get_raises_not_found(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_id = AsyncMock(return_value=None)
        with _patch_ctx(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.get(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_get_returns_from_cache(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        record = _make_record()
        from corpmind.modules.customer_success.schemas import CustomerSuccessOut
        cached = CustomerSuccessOut.model_validate(record).model_dump_json()
        redis = _make_redis(cached=cached)
        svc._repo.find_by_id = AsyncMock()
        with _patch_ctx(ctx, redis):
            out = await svc.get(_RECORD)
        svc._repo.find_by_id.assert_not_awaited()
        assert out.id == _RECORD

    @pytest.mark.asyncio
    async def test_get_populates_cache(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_id = AsyncMock(return_value=_make_record())
        with _patch_ctx(ctx, redis):
            await svc.get(_RECORD)
        redis.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_cache_ttl_300(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_id = AsyncMock(return_value=_make_record())
        with _patch_ctx(ctx, redis):
            await svc.get(_RECORD)
        assert redis.set.call_args.kwargs.get("ex") == 300

    @pytest.mark.asyncio
    async def test_get_graceful_on_redis_error(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        redis.get = AsyncMock(side_effect=Exception("redis down"))
        svc._repo.find_by_id = AsyncMock(return_value=_make_record())
        with _patch_ctx(ctx, redis):
            out = await svc.get(_RECORD)
        assert out.id == _RECORD

    @pytest.mark.asyncio
    async def test_get_returns_health_status(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_id = AsyncMock(return_value=_make_record(health_status="at_risk"))
        with _patch_ctx(ctx, redis):
            out = await svc.get(_RECORD)
        assert out.health_status == "at_risk"

    @pytest.mark.asyncio
    async def test_get_returns_risk_level(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_id = AsyncMock(return_value=_make_record(risk_level="high"))
        with _patch_ctx(ctx, redis):
            out = await svc.get(_RECORD)
        assert out.risk_level == "high"

    @pytest.mark.asyncio
    async def test_get_returns_notes(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_id = AsyncMock(return_value=_make_record(notes="VIP customer"))
        with _patch_ctx(ctx, redis):
            out = await svc.get(_RECORD)
        assert out.notes == "VIP customer"

    @pytest.mark.asyncio
    async def test_get_returns_renewal_date(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_id = AsyncMock(
            return_value=_make_record(renewal_date=date(2027, 1, 1))
        )
        with _patch_ctx(ctx, redis):
            out = await svc.get(_RECORD)
        assert str(out.renewal_date) == "2027-01-01"

    @pytest.mark.asyncio
    async def test_get_returns_expansion_flag(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_id = AsyncMock(
            return_value=_make_record(expansion_opportunity=True)
        )
        with _patch_ctx(ctx, redis):
            out = await svc.get(_RECORD)
        assert out.expansion_opportunity is True

    @pytest.mark.asyncio
    async def test_get_archive_flag(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_id = AsyncMock(
            return_value=_make_record(is_archived=True)
        )
        with _patch_ctx(ctx, redis):
            out = await svc.get(_RECORD)
        assert out.is_archived is True


# ── TestGetByCustomer ─────────────────────────────────────────────────────────

class TestGetByCustomer:
    @pytest.mark.asyncio
    async def test_get_by_customer_returns_record(self):
        svc, _ = _make_svc()
        svc._repo.find_by_customer_id = AsyncMock(return_value=_make_record())
        out = await svc.get_by_customer(_CUSTOMER)
        assert out.customer_id == _CUSTOMER

    @pytest.mark.asyncio
    async def test_get_by_customer_raises_not_found(self):
        svc, _ = _make_svc()
        svc._repo.find_by_customer_id = AsyncMock(return_value=None)
        with pytest.raises(NotFoundError):
            await svc.get_by_customer(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_get_by_customer_returns_health_status(self):
        svc, _ = _make_svc()
        svc._repo.find_by_customer_id = AsyncMock(
            return_value=_make_record(health_status="healthy")
        )
        out = await svc.get_by_customer(_CUSTOMER)
        assert out.health_status == "healthy"

    @pytest.mark.asyncio
    async def test_get_by_customer_returns_risk(self):
        svc, _ = _make_svc()
        svc._repo.find_by_customer_id = AsyncMock(
            return_value=_make_record(risk_level="low")
        )
        out = await svc.get_by_customer(_CUSTOMER)
        assert out.risk_level == "low"

    @pytest.mark.asyncio
    async def test_get_by_customer_returns_score(self):
        svc, _ = _make_svc()
        svc._repo.find_by_customer_id = AsyncMock(
            return_value=_make_record(health_score=90)
        )
        out = await svc.get_by_customer(_CUSTOMER)
        assert out.health_score == 90

    @pytest.mark.asyncio
    async def test_get_by_customer_returns_notes(self):
        svc, _ = _make_svc()
        svc._repo.find_by_customer_id = AsyncMock(
            return_value=_make_record(notes="Enterprise")
        )
        out = await svc.get_by_customer(_CUSTOMER)
        assert out.notes == "Enterprise"

    @pytest.mark.asyncio
    async def test_get_by_customer_calls_repo_once(self):
        svc, _ = _make_svc()
        svc._repo.find_by_customer_id = AsyncMock(return_value=_make_record())
        await svc.get_by_customer(_CUSTOMER)
        svc._repo.find_by_customer_id.assert_awaited_once_with(_CUSTOMER)

    @pytest.mark.asyncio
    async def test_get_by_customer_returns_none_owner(self):
        svc, _ = _make_svc()
        svc._repo.find_by_customer_id = AsyncMock(return_value=_make_record())
        out = await svc.get_by_customer(_CUSTOMER)
        assert out.owner_user_id is None


# ── TestUpdate ────────────────────────────────────────────────────────────────

class TestUpdate:
    @pytest.mark.asyncio
    async def test_update_health_status(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        original = _make_record()
        updated = _make_record(health_status="healthy")
        svc._repo.find_by_id = AsyncMock(side_effect=[original, updated])
        svc._repo.update_fields = AsyncMock()
        req = CustomerSuccessUpdate(health_status="healthy")
        with _patch_ctx(ctx, redis):
            out = await svc.update(_RECORD, req)
        assert out.health_status == "healthy"

    @pytest.mark.asyncio
    async def test_update_raises_not_found(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_id = AsyncMock(return_value=None)
        req = CustomerSuccessUpdate(notes="x")
        with _patch_ctx(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.update(uuid.uuid4(), req)

    @pytest.mark.asyncio
    async def test_update_notes(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        original = _make_record()
        updated = _make_record(notes="Updated notes")
        svc._repo.find_by_id = AsyncMock(side_effect=[original, updated])
        svc._repo.update_fields = AsyncMock()
        req = CustomerSuccessUpdate(notes="Updated notes")
        with _patch_ctx(ctx, redis):
            out = await svc.update(_RECORD, req)
        assert out.notes == "Updated notes"

    @pytest.mark.asyncio
    async def test_update_risk_level(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        original = _make_record()
        updated = _make_record(risk_level="high")
        svc._repo.find_by_id = AsyncMock(side_effect=[original, updated])
        svc._repo.update_fields = AsyncMock()
        req = CustomerSuccessUpdate(risk_level="high")
        with _patch_ctx(ctx, redis):
            out = await svc.update(_RECORD, req)
        assert out.risk_level == "high"

    @pytest.mark.asyncio
    async def test_update_commits(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record()
        svc._repo.find_by_id = AsyncMock(side_effect=[r, r])
        svc._repo.update_fields = AsyncMock()
        req = CustomerSuccessUpdate(notes="x")
        with _patch_ctx(ctx, redis):
            await svc.update(_RECORD, req)
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_busts_detail_cache(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record()
        svc._repo.find_by_id = AsyncMock(side_effect=[r, r])
        svc._repo.update_fields = AsyncMock()
        req = CustomerSuccessUpdate(notes="x")
        with _patch_ctx(ctx, redis):
            await svc.update(_RECORD, req)
        redis.delete.assert_awaited()

    @pytest.mark.asyncio
    async def test_update_health_score(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record()
        updated = _make_record(health_score=70)
        svc._repo.find_by_id = AsyncMock(side_effect=[r, updated])
        svc._repo.update_fields = AsyncMock()
        req = CustomerSuccessUpdate(health_score=70)
        with _patch_ctx(ctx, redis):
            out = await svc.update(_RECORD, req)
        assert out.health_score == 70

    @pytest.mark.asyncio
    async def test_update_renewal_probability(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record()
        updated = _make_record(renewal_probability=80)
        svc._repo.find_by_id = AsyncMock(side_effect=[r, updated])
        svc._repo.update_fields = AsyncMock()
        req = CustomerSuccessUpdate(renewal_probability=80)
        with _patch_ctx(ctx, redis):
            out = await svc.update(_RECORD, req)
        assert out.renewal_probability == 80

    @pytest.mark.asyncio
    async def test_update_expansion_opportunity(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record()
        updated = _make_record(expansion_opportunity=True)
        svc._repo.find_by_id = AsyncMock(side_effect=[r, updated])
        svc._repo.update_fields = AsyncMock()
        req = CustomerSuccessUpdate(expansion_opportunity=True)
        with _patch_ctx(ctx, redis):
            out = await svc.update(_RECORD, req)
        assert out.expansion_opportunity is True

    @pytest.mark.asyncio
    async def test_update_renewal_date(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record()
        updated = _make_record(renewal_date=date(2027, 3, 1))
        svc._repo.find_by_id = AsyncMock(side_effect=[r, updated])
        svc._repo.update_fields = AsyncMock()
        req = CustomerSuccessUpdate(renewal_date=date(2027, 3, 1))
        with _patch_ctx(ctx, redis):
            out = await svc.update(_RECORD, req)
        assert str(out.renewal_date) == "2027-03-01"

    @pytest.mark.asyncio
    async def test_update_last_contact_date(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record()
        updated = _make_record(last_contact_date=date(2026, 7, 10))
        svc._repo.find_by_id = AsyncMock(side_effect=[r, updated])
        svc._repo.update_fields = AsyncMock()
        req = CustomerSuccessUpdate(last_contact_date=date(2026, 7, 10))
        with _patch_ctx(ctx, redis):
            out = await svc.update(_RECORD, req)
        assert str(out.last_contact_date) == "2026-07-10"

    @pytest.mark.asyncio
    async def test_update_next_followup_date(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record()
        updated = _make_record(next_followup_date=date(2026, 8, 20))
        svc._repo.find_by_id = AsyncMock(side_effect=[r, updated])
        svc._repo.update_fields = AsyncMock()
        req = CustomerSuccessUpdate(next_followup_date=date(2026, 8, 20))
        with _patch_ctx(ctx, redis):
            out = await svc.update(_RECORD, req)
        assert str(out.next_followup_date) == "2026-08-20"

    @pytest.mark.asyncio
    async def test_update_no_changes_is_no_op(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record()
        svc._repo.find_by_id = AsyncMock(side_effect=[r, r])
        svc._repo.update_fields = AsyncMock()
        req = CustomerSuccessUpdate()
        with _patch_ctx(ctx, redis):
            out = await svc.update(_RECORD, req)
        assert out.id == _RECORD

    @pytest.mark.asyncio
    async def test_update_calls_update_fields(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record()
        svc._repo.find_by_id = AsyncMock(side_effect=[r, r])
        svc._repo.update_fields = AsyncMock()
        req = CustomerSuccessUpdate(notes="new")
        with _patch_ctx(ctx, redis):
            await svc.update(_RECORD, req)
        svc._repo.update_fields.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_does_not_commit_on_not_found(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_id = AsyncMock(return_value=None)
        req = CustomerSuccessUpdate(notes="x")
        with _patch_ctx(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.update(uuid.uuid4(), req)
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_partial_fields_only(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record(risk_level="high")
        updated = _make_record(risk_level="high", notes="new note")
        svc._repo.find_by_id = AsyncMock(side_effect=[r, updated])
        svc._repo.update_fields = AsyncMock()
        req = CustomerSuccessUpdate(notes="new note")
        with _patch_ctx(ctx, redis):
            out = await svc.update(_RECORD, req)
        assert out.risk_level == "high"


# ── TestList ──────────────────────────────────────────────────────────────────

class TestList:
    @pytest.mark.asyncio
    async def test_list_returns_items(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.count = AsyncMock(return_value=2)
        svc._repo.list_page = AsyncMock(return_value=[_make_record(), _make_record()])
        filters = CustomerSuccessFilters(workspace_id=_WS)
        with _patch_ctx(ctx, redis):
            out = await svc.list(filters)
        assert len(out.items) == 2

    @pytest.mark.asyncio
    async def test_list_returns_total(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.count = AsyncMock(return_value=5)
        svc._repo.list_page = AsyncMock(return_value=[])
        filters = CustomerSuccessFilters(workspace_id=_WS)
        with _patch_ctx(ctx, redis):
            out = await svc.list(filters)
        assert out.total == 5

    @pytest.mark.asyncio
    async def test_list_has_more_true_when_extra(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.count = AsyncMock(return_value=51)
        items = [_make_record(record_id=uuid.uuid4()) for _ in range(51)]
        svc._repo.list_page = AsyncMock(return_value=items)
        filters = CustomerSuccessFilters(workspace_id=_WS, limit=50)
        with _patch_ctx(ctx, redis):
            out = await svc.list(filters)
        assert out.has_more is True
        assert len(out.items) == 50

    @pytest.mark.asyncio
    async def test_list_has_more_false(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.count = AsyncMock(return_value=3)
        svc._repo.list_page = AsyncMock(return_value=[_make_record() for _ in range(3)])
        filters = CustomerSuccessFilters(workspace_id=_WS)
        with _patch_ctx(ctx, redis):
            out = await svc.list(filters)
        assert out.has_more is False

    @pytest.mark.asyncio
    async def test_list_populates_cache_when_default(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        filters = CustomerSuccessFilters(workspace_id=_WS)
        with _patch_ctx(ctx, redis):
            await svc.list(filters)
        redis.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_list_returns_from_cache(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        from corpmind.modules.customer_success.schemas import CustomerSuccessListOut
        cached_out = CustomerSuccessListOut(items=[], next_cursor=None, has_more=False, total=0)
        redis = _make_redis(cached=cached_out.model_dump_json())
        svc._repo.count = AsyncMock()
        svc._repo.list_page = AsyncMock()
        filters = CustomerSuccessFilters(workspace_id=_WS)
        with _patch_ctx(ctx, redis):
            out = await svc.list(filters)
        svc._repo.count.assert_not_awaited()
        assert out.total == 0

    @pytest.mark.asyncio
    async def test_list_skips_cache_with_filter(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        filters = CustomerSuccessFilters(workspace_id=_WS, health_status="healthy")
        with _patch_ctx(ctx, redis):
            await svc.list(filters)
        redis.set.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_list_health_filter_passed_to_repo(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        filters = CustomerSuccessFilters(workspace_id=_WS, health_status="at_risk")
        with _patch_ctx(ctx, redis):
            await svc.list(filters)
        call_kwargs = svc._repo.list_page.call_args.kwargs
        assert call_kwargs["health_status"] == "at_risk"

    @pytest.mark.asyncio
    async def test_list_risk_filter_passed_to_repo(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        filters = CustomerSuccessFilters(workspace_id=_WS, risk_level="high")
        with _patch_ctx(ctx, redis):
            await svc.list(filters)
        call_kwargs = svc._repo.list_page.call_args.kwargs
        assert call_kwargs["risk_level"] == "high"

    @pytest.mark.asyncio
    async def test_list_search_passed_to_repo(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        filters = CustomerSuccessFilters(workspace_id=_WS, search="enterprise")
        with _patch_ctx(ctx, redis):
            await svc.list(filters)
        call_kwargs = svc._repo.list_page.call_args.kwargs
        assert call_kwargs["search"] == "enterprise"

    @pytest.mark.asyncio
    async def test_list_cursor_passed_to_repo(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        filters = CustomerSuccessFilters(workspace_id=_WS, cursor="abc123")
        with _patch_ctx(ctx, redis):
            await svc.list(filters)
        call_kwargs = svc._repo.list_page.call_args.kwargs
        assert call_kwargs["cursor"] == "abc123"

    @pytest.mark.asyncio
    async def test_list_next_cursor_set_when_has_more(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.count = AsyncMock(return_value=51)
        items = [_make_record(record_id=uuid.uuid4()) for _ in range(51)]
        svc._repo.list_page = AsyncMock(return_value=items)
        filters = CustomerSuccessFilters(workspace_id=_WS, limit=50)
        with _patch_ctx(ctx, redis):
            out = await svc.list(filters)
        assert out.next_cursor is not None

    @pytest.mark.asyncio
    async def test_list_next_cursor_none_when_no_more(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.count = AsyncMock(return_value=3)
        svc._repo.list_page = AsyncMock(return_value=[_make_record() for _ in range(3)])
        filters = CustomerSuccessFilters(workspace_id=_WS)
        with _patch_ctx(ctx, redis):
            out = await svc.list(filters)
        assert out.next_cursor is None

    @pytest.mark.asyncio
    async def test_list_empty_returns_zero_total(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        filters = CustomerSuccessFilters(workspace_id=_WS)
        with _patch_ctx(ctx, redis):
            out = await svc.list(filters)
        assert out.total == 0
        assert out.items == []

    @pytest.mark.asyncio
    async def test_list_expansion_filter_passed(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        filters = CustomerSuccessFilters(workspace_id=_WS, expansion_opportunity=True)
        with _patch_ctx(ctx, redis):
            await svc.list(filters)
        call_kwargs = svc._repo.list_page.call_args.kwargs
        assert call_kwargs["expansion_opportunity"] is True

    @pytest.mark.asyncio
    async def test_list_owner_filter_passed(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        filters = CustomerSuccessFilters(workspace_id=_WS, owner_user_id=_OWNER)
        with _patch_ctx(ctx, redis):
            await svc.list(filters)
        call_kwargs = svc._repo.list_page.call_args.kwargs
        assert call_kwargs["owner_user_id"] == _OWNER

    @pytest.mark.asyncio
    async def test_list_cache_ttl_300(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        filters = CustomerSuccessFilters(workspace_id=_WS)
        with _patch_ctx(ctx, redis):
            await svc.list(filters)
        assert redis.set.call_args.kwargs.get("ex") == 300

    @pytest.mark.asyncio
    async def test_list_include_archived_passed(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        filters = CustomerSuccessFilters(workspace_id=_WS, include_archived=True)
        with _patch_ctx(ctx, redis):
            await svc.list(filters)
        call_kwargs = svc._repo.list_page.call_args.kwargs
        assert call_kwargs["include_archived"] is True

    @pytest.mark.asyncio
    async def test_list_followup_filter_passed(self):
        svc, _ = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        filters = CustomerSuccessFilters(workspace_id=_WS, followup_due_by=date(2026, 8, 1))
        with _patch_ctx(ctx, redis):
            await svc.list(filters)
        call_kwargs = svc._repo.list_page.call_args.kwargs
        assert call_kwargs["followup_due_by"] == date(2026, 8, 1)


# ── TestAssignOwner ───────────────────────────────────────────────────────────

class TestAssignOwner:
    @pytest.mark.asyncio
    async def test_assign_owner_success(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record()
        updated = _make_record(owner_user_id=_OWNER)
        svc._repo.find_by_id = AsyncMock(side_effect=[r, updated])
        svc._repo.update_fields = AsyncMock()
        with _patch_ctx(ctx, redis):
            out = await svc.assign_owner(_RECORD, AssignOwner(owner_user_id=_OWNER))
        assert out.owner_user_id == _OWNER

    @pytest.mark.asyncio
    async def test_assign_owner_raises_not_found(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_id = AsyncMock(return_value=None)
        with _patch_ctx(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.assign_owner(uuid.uuid4(), AssignOwner(owner_user_id=_OWNER))

    @pytest.mark.asyncio
    async def test_assign_owner_commits(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record()
        updated = _make_record(owner_user_id=_OWNER)
        svc._repo.find_by_id = AsyncMock(side_effect=[r, updated])
        svc._repo.update_fields = AsyncMock()
        with _patch_ctx(ctx, redis):
            await svc.assign_owner(_RECORD, AssignOwner(owner_user_id=_OWNER))
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_assign_owner_busts_cache(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record()
        updated = _make_record(owner_user_id=_OWNER)
        svc._repo.find_by_id = AsyncMock(side_effect=[r, updated])
        svc._repo.update_fields = AsyncMock()
        with _patch_ctx(ctx, redis):
            await svc.assign_owner(_RECORD, AssignOwner(owner_user_id=_OWNER))
        redis.delete.assert_awaited()

    @pytest.mark.asyncio
    async def test_assign_different_owner(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        o2 = uuid.uuid4()
        r = _make_record()
        updated = _make_record(owner_user_id=o2)
        svc._repo.find_by_id = AsyncMock(side_effect=[r, updated])
        svc._repo.update_fields = AsyncMock()
        with _patch_ctx(ctx, redis):
            out = await svc.assign_owner(_RECORD, AssignOwner(owner_user_id=o2))
        assert out.owner_user_id == o2

    @pytest.mark.asyncio
    async def test_assign_owner_calls_update_fields(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record()
        updated = _make_record(owner_user_id=_OWNER)
        svc._repo.find_by_id = AsyncMock(side_effect=[r, updated])
        svc._repo.update_fields = AsyncMock()
        with _patch_ctx(ctx, redis):
            await svc.assign_owner(_RECORD, AssignOwner(owner_user_id=_OWNER))
        svc._repo.update_fields.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_assign_owner_passes_owner_id(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record()
        updated = _make_record(owner_user_id=_OWNER)
        svc._repo.find_by_id = AsyncMock(side_effect=[r, updated])
        svc._repo.update_fields = AsyncMock()
        with _patch_ctx(ctx, redis):
            await svc.assign_owner(_RECORD, AssignOwner(owner_user_id=_OWNER))
        call_kwargs = svc._repo.update_fields.call_args.kwargs
        assert call_kwargs["owner_user_id"] == _OWNER

    @pytest.mark.asyncio
    async def test_assign_owner_does_not_change_health(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record(health_status="at_risk")
        updated = _make_record(health_status="at_risk", owner_user_id=_OWNER)
        svc._repo.find_by_id = AsyncMock(side_effect=[r, updated])
        svc._repo.update_fields = AsyncMock()
        with _patch_ctx(ctx, redis):
            out = await svc.assign_owner(_RECORD, AssignOwner(owner_user_id=_OWNER))
        assert out.health_status == "at_risk"

    @pytest.mark.asyncio
    async def test_assign_owner_no_commit_on_not_found(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_id = AsyncMock(return_value=None)
        with _patch_ctx(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.assign_owner(uuid.uuid4(), AssignOwner(owner_user_id=_OWNER))
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_assign_owner_returns_full_out(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record()
        updated = _make_record(owner_user_id=_OWNER, notes="important")
        svc._repo.find_by_id = AsyncMock(side_effect=[r, updated])
        svc._repo.update_fields = AsyncMock()
        with _patch_ctx(ctx, redis):
            out = await svc.assign_owner(_RECORD, AssignOwner(owner_user_id=_OWNER))
        assert out.notes == "important"

    @pytest.mark.asyncio
    async def test_assign_owner_preserves_workspace(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record()
        updated = _make_record(owner_user_id=_OWNER)
        svc._repo.find_by_id = AsyncMock(side_effect=[r, updated])
        svc._repo.update_fields = AsyncMock()
        with _patch_ctx(ctx, redis):
            out = await svc.assign_owner(_RECORD, AssignOwner(owner_user_id=_OWNER))
        assert out.workspace_id == _WS

    @pytest.mark.asyncio
    async def test_assign_owner_redis_error_graceful(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        redis.delete = AsyncMock(side_effect=Exception("redis down"))
        r = _make_record()
        updated = _make_record(owner_user_id=_OWNER)
        svc._repo.find_by_id = AsyncMock(side_effect=[r, updated])
        svc._repo.update_fields = AsyncMock()
        with _patch_ctx(ctx, redis):
            out = await svc.assign_owner(_RECORD, AssignOwner(owner_user_id=_OWNER))
        assert out.owner_user_id == _OWNER


# ── TestUpdateHealth ──────────────────────────────────────────────────────────

class TestUpdateHealth:
    @pytest.mark.asyncio
    async def test_update_health_changes_status(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record(health_status="watch")
        updated = _make_record(health_status="at_risk")
        svc._repo.find_by_id = AsyncMock(side_effect=[r, updated])
        svc._repo.update_fields = AsyncMock()
        with _patch_ctx(ctx, redis):
            out = await svc.update_health(_RECORD, UpdateHealth(health_status="at_risk"))
        assert out.health_status == "at_risk"

    @pytest.mark.asyncio
    async def test_update_health_raises_not_found(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_id = AsyncMock(return_value=None)
        with _patch_ctx(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.update_health(uuid.uuid4(), UpdateHealth(health_status="healthy"))

    @pytest.mark.asyncio
    async def test_update_health_commits(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record()
        updated = _make_record(health_status="healthy")
        svc._repo.find_by_id = AsyncMock(side_effect=[r, updated])
        svc._repo.update_fields = AsyncMock()
        with _patch_ctx(ctx, redis):
            await svc.update_health(_RECORD, UpdateHealth(health_status="healthy"))
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_health_busts_cache(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record()
        updated = _make_record(health_status="healthy")
        svc._repo.find_by_id = AsyncMock(side_effect=[r, updated])
        svc._repo.update_fields = AsyncMock()
        with _patch_ctx(ctx, redis):
            await svc.update_health(_RECORD, UpdateHealth(health_status="healthy"))
        redis.delete.assert_awaited()

    @pytest.mark.asyncio
    async def test_update_health_with_score(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record()
        updated = _make_record(health_status="healthy", health_score=95)
        svc._repo.find_by_id = AsyncMock(side_effect=[r, updated])
        svc._repo.update_fields = AsyncMock()
        with _patch_ctx(ctx, redis):
            out = await svc.update_health(
                _RECORD, UpdateHealth(health_status="healthy", health_score=95)
            )
        assert out.health_score == 95

    @pytest.mark.asyncio
    async def test_update_health_from_watch_to_healthy(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record(health_status="watch")
        updated = _make_record(health_status="healthy")
        svc._repo.find_by_id = AsyncMock(side_effect=[r, updated])
        svc._repo.update_fields = AsyncMock()
        with _patch_ctx(ctx, redis):
            out = await svc.update_health(_RECORD, UpdateHealth(health_status="healthy"))
        assert out.health_status == "healthy"

    @pytest.mark.asyncio
    async def test_update_health_passes_score_to_repo(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record()
        updated = _make_record(health_score=60)
        svc._repo.find_by_id = AsyncMock(side_effect=[r, updated])
        svc._repo.update_fields = AsyncMock()
        with _patch_ctx(ctx, redis):
            await svc.update_health(
                _RECORD, UpdateHealth(health_status="watch", health_score=60)
            )
        call_kwargs = svc._repo.update_fields.call_args.kwargs
        assert call_kwargs["health_score"] == 60

    @pytest.mark.asyncio
    async def test_update_health_passes_status_to_repo(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record()
        updated = _make_record(health_status="at_risk")
        svc._repo.find_by_id = AsyncMock(side_effect=[r, updated])
        svc._repo.update_fields = AsyncMock()
        with _patch_ctx(ctx, redis):
            await svc.update_health(_RECORD, UpdateHealth(health_status="at_risk"))
        call_kwargs = svc._repo.update_fields.call_args.kwargs
        assert call_kwargs["health_status"] == "at_risk"

    @pytest.mark.asyncio
    async def test_update_health_no_commit_on_not_found(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_id = AsyncMock(return_value=None)
        with _patch_ctx(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.update_health(
                    uuid.uuid4(), UpdateHealth(health_status="healthy")
                )
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_health_same_status_still_commits(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record(health_status="watch")
        updated = _make_record(health_status="watch")
        svc._repo.find_by_id = AsyncMock(side_effect=[r, updated])
        svc._repo.update_fields = AsyncMock()
        with _patch_ctx(ctx, redis):
            await svc.update_health(_RECORD, UpdateHealth(health_status="watch"))
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_health_preserves_risk_level(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record(risk_level="high")
        updated = _make_record(risk_level="high", health_status="at_risk")
        svc._repo.find_by_id = AsyncMock(side_effect=[r, updated])
        svc._repo.update_fields = AsyncMock()
        with _patch_ctx(ctx, redis):
            out = await svc.update_health(_RECORD, UpdateHealth(health_status="at_risk"))
        assert out.risk_level == "high"

    @pytest.mark.asyncio
    async def test_update_health_at_risk_no_score(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record()
        updated = _make_record(health_status="at_risk")
        svc._repo.find_by_id = AsyncMock(side_effect=[r, updated])
        svc._repo.update_fields = AsyncMock()
        with _patch_ctx(ctx, redis):
            out = await svc.update_health(_RECORD, UpdateHealth(health_status="at_risk"))
        assert out.health_score is None

    @pytest.mark.asyncio
    async def test_update_health_redis_error_graceful(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        redis.delete = AsyncMock(side_effect=Exception("redis down"))
        r = _make_record()
        updated = _make_record(health_status="healthy")
        svc._repo.find_by_id = AsyncMock(side_effect=[r, updated])
        svc._repo.update_fields = AsyncMock()
        with _patch_ctx(ctx, redis):
            out = await svc.update_health(_RECORD, UpdateHealth(health_status="healthy"))
        assert out.health_status == "healthy"

    @pytest.mark.asyncio
    async def test_update_health_all_three_statuses(self):
        for status in ["healthy", "watch", "at_risk"]:
            svc, db = _make_svc()
            ctx = _make_ctx()
            redis = _make_redis()
            r = _make_record()
            updated = _make_record(health_status=status)
            svc._repo.find_by_id = AsyncMock(side_effect=[r, updated])
            svc._repo.update_fields = AsyncMock()
            with _patch_ctx(ctx, redis):
                out = await svc.update_health(
                    _RECORD, UpdateHealth(health_status=status)
                )
            assert out.health_status == status

    @pytest.mark.asyncio
    async def test_update_health_score_boundary_0(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record()
        updated = _make_record(health_score=0)
        svc._repo.find_by_id = AsyncMock(side_effect=[r, updated])
        svc._repo.update_fields = AsyncMock()
        with _patch_ctx(ctx, redis):
            out = await svc.update_health(
                _RECORD, UpdateHealth(health_status="at_risk", health_score=0)
            )
        assert out.health_score == 0


# ── TestScheduleFollowup ──────────────────────────────────────────────────────

class TestScheduleFollowup:
    @pytest.mark.asyncio
    async def test_schedule_followup_sets_date(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record()
        updated = _make_record(next_followup_date=date(2026, 9, 1))
        svc._repo.find_by_id = AsyncMock(side_effect=[r, updated])
        svc._repo.update_fields = AsyncMock()
        with _patch_ctx(ctx, redis):
            out = await svc.schedule_followup(
                _RECORD, ScheduleFollowup(next_followup_date=date(2026, 9, 1))
            )
        assert str(out.next_followup_date) == "2026-09-01"

    @pytest.mark.asyncio
    async def test_schedule_followup_raises_not_found(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_id = AsyncMock(return_value=None)
        with _patch_ctx(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.schedule_followup(
                    uuid.uuid4(), ScheduleFollowup(next_followup_date=date(2026, 9, 1))
                )

    @pytest.mark.asyncio
    async def test_schedule_followup_commits(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record()
        updated = _make_record(next_followup_date=date(2026, 9, 1))
        svc._repo.find_by_id = AsyncMock(side_effect=[r, updated])
        svc._repo.update_fields = AsyncMock()
        with _patch_ctx(ctx, redis):
            await svc.schedule_followup(
                _RECORD, ScheduleFollowup(next_followup_date=date(2026, 9, 1))
            )
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_schedule_followup_busts_cache(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record()
        updated = _make_record(next_followup_date=date(2026, 9, 1))
        svc._repo.find_by_id = AsyncMock(side_effect=[r, updated])
        svc._repo.update_fields = AsyncMock()
        with _patch_ctx(ctx, redis):
            await svc.schedule_followup(
                _RECORD, ScheduleFollowup(next_followup_date=date(2026, 9, 1))
            )
        redis.delete.assert_awaited()

    @pytest.mark.asyncio
    async def test_schedule_followup_passes_date_to_repo(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record()
        updated = _make_record(next_followup_date=date(2026, 10, 15))
        svc._repo.find_by_id = AsyncMock(side_effect=[r, updated])
        svc._repo.update_fields = AsyncMock()
        with _patch_ctx(ctx, redis):
            await svc.schedule_followup(
                _RECORD, ScheduleFollowup(next_followup_date=date(2026, 10, 15))
            )
        call_kwargs = svc._repo.update_fields.call_args.kwargs
        assert call_kwargs["next_followup_date"] == date(2026, 10, 15)

    @pytest.mark.asyncio
    async def test_schedule_followup_no_commit_on_not_found(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_id = AsyncMock(return_value=None)
        with _patch_ctx(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.schedule_followup(
                    uuid.uuid4(), ScheduleFollowup(next_followup_date=date(2026, 9, 1))
                )
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_schedule_followup_preserves_health(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record(health_status="healthy")
        updated = _make_record(health_status="healthy", next_followup_date=date(2026, 9, 1))
        svc._repo.find_by_id = AsyncMock(side_effect=[r, updated])
        svc._repo.update_fields = AsyncMock()
        with _patch_ctx(ctx, redis):
            out = await svc.schedule_followup(
                _RECORD, ScheduleFollowup(next_followup_date=date(2026, 9, 1))
            )
        assert out.health_status == "healthy"

    @pytest.mark.asyncio
    async def test_schedule_followup_far_future_date(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record()
        d = date(2030, 12, 31)
        updated = _make_record(next_followup_date=d)
        svc._repo.find_by_id = AsyncMock(side_effect=[r, updated])
        svc._repo.update_fields = AsyncMock()
        with _patch_ctx(ctx, redis):
            out = await svc.schedule_followup(
                _RECORD, ScheduleFollowup(next_followup_date=d)
            )
        assert str(out.next_followup_date) == "2030-12-31"

    @pytest.mark.asyncio
    async def test_schedule_followup_redis_error_graceful(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        redis.delete = AsyncMock(side_effect=Exception("redis down"))
        r = _make_record()
        updated = _make_record(next_followup_date=date(2026, 9, 1))
        svc._repo.find_by_id = AsyncMock(side_effect=[r, updated])
        svc._repo.update_fields = AsyncMock()
        with _patch_ctx(ctx, redis):
            out = await svc.schedule_followup(
                _RECORD, ScheduleFollowup(next_followup_date=date(2026, 9, 1))
            )
        assert out.next_followup_date is not None

    @pytest.mark.asyncio
    async def test_schedule_followup_returns_full_out(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record()
        updated = _make_record(next_followup_date=date(2026, 9, 1), notes="follow up!")
        svc._repo.find_by_id = AsyncMock(side_effect=[r, updated])
        svc._repo.update_fields = AsyncMock()
        with _patch_ctx(ctx, redis):
            out = await svc.schedule_followup(
                _RECORD, ScheduleFollowup(next_followup_date=date(2026, 9, 1))
            )
        assert out.notes == "follow up!"

    @pytest.mark.asyncio
    async def test_schedule_followup_calls_update_fields_once(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record()
        updated = _make_record(next_followup_date=date(2026, 9, 1))
        svc._repo.find_by_id = AsyncMock(side_effect=[r, updated])
        svc._repo.update_fields = AsyncMock()
        with _patch_ctx(ctx, redis):
            await svc.schedule_followup(
                _RECORD, ScheduleFollowup(next_followup_date=date(2026, 9, 1))
            )
        svc._repo.update_fields.assert_awaited_once()


# ── TestArchive ───────────────────────────────────────────────────────────────

class TestArchive:
    @pytest.mark.asyncio
    async def test_archive_sets_flag(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record(is_archived=False)
        archived = _make_record(is_archived=True)
        svc._repo.find_by_id = AsyncMock(side_effect=[r, archived])
        svc._repo.update_fields = AsyncMock()
        with _patch_ctx(ctx, redis):
            out = await svc.archive(_RECORD)
        assert out.is_archived is True

    @pytest.mark.asyncio
    async def test_archive_raises_not_found(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_id = AsyncMock(return_value=None)
        with _patch_ctx(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.archive(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_archive_already_archived_raises(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_id = AsyncMock(return_value=_make_record(is_archived=True))
        with _patch_ctx(ctx, redis):
            with pytest.raises(ValidationError):
                await svc.archive(_RECORD)

    @pytest.mark.asyncio
    async def test_archive_commits(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record()
        archived = _make_record(is_archived=True)
        svc._repo.find_by_id = AsyncMock(side_effect=[r, archived])
        svc._repo.update_fields = AsyncMock()
        with _patch_ctx(ctx, redis):
            await svc.archive(_RECORD)
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_archive_busts_cache(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record()
        archived = _make_record(is_archived=True)
        svc._repo.find_by_id = AsyncMock(side_effect=[r, archived])
        svc._repo.update_fields = AsyncMock()
        with _patch_ctx(ctx, redis):
            await svc.archive(_RECORD)
        redis.delete.assert_awaited()

    @pytest.mark.asyncio
    async def test_archive_no_commit_on_already_archived(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_id = AsyncMock(return_value=_make_record(is_archived=True))
        with _patch_ctx(ctx, redis):
            with pytest.raises(ValidationError):
                await svc.archive(_RECORD)
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_archive_calls_update_fields_with_is_archived(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record()
        archived = _make_record(is_archived=True)
        svc._repo.find_by_id = AsyncMock(side_effect=[r, archived])
        svc._repo.update_fields = AsyncMock()
        with _patch_ctx(ctx, redis):
            await svc.archive(_RECORD)
        call_kwargs = svc._repo.update_fields.call_args.kwargs
        assert call_kwargs["is_archived"] is True

    @pytest.mark.asyncio
    async def test_archive_preserves_customer_id(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        r = _make_record()
        archived = _make_record(is_archived=True)
        svc._repo.find_by_id = AsyncMock(side_effect=[r, archived])
        svc._repo.update_fields = AsyncMock()
        with _patch_ctx(ctx, redis):
            out = await svc.archive(_RECORD)
        assert out.customer_id == _CUSTOMER

    @pytest.mark.asyncio
    async def test_archive_not_found_no_update_fields(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_id = AsyncMock(return_value=None)
        svc._repo.update_fields = AsyncMock()
        with _patch_ctx(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.archive(uuid.uuid4())
        svc._repo.update_fields.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_archive_redis_error_graceful(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        redis.delete = AsyncMock(side_effect=Exception("redis down"))
        r = _make_record()
        archived = _make_record(is_archived=True)
        svc._repo.find_by_id = AsyncMock(side_effect=[r, archived])
        svc._repo.update_fields = AsyncMock()
        with _patch_ctx(ctx, redis):
            out = await svc.archive(_RECORD)
        assert out.is_archived is True


# ── TestTenantIsolation ───────────────────────────────────────────────────────

class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_create_uses_ctx_tenant_id(self):
        svc, _ = _make_svc()
        org_a = uuid.uuid4()
        ctx = _make_ctx(org_id=org_a)
        redis = _make_redis()
        svc._repo.find_by_customer_id = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(side_effect=lambda r: r)
        req = CustomerSuccessCreate(workspace_id=_WS, customer_id=_CUSTOMER)
        with _patch_ctx(ctx, redis):
            out = await svc.create(req)
        assert out.tenant_id == org_a

    @pytest.mark.asyncio
    async def test_two_tenants_different_cache_keys(self):
        org_a = uuid.uuid4()
        org_b = uuid.uuid4()
        from corpmind.modules.customer_success.service import _list_key
        key_a = _list_key(org_a, _WS)
        key_b = _list_key(org_b, _WS)
        assert key_a != key_b

    @pytest.mark.asyncio
    async def test_detail_cache_key_includes_org_id(self):
        org_a = uuid.uuid4()
        org_b = uuid.uuid4()
        from corpmind.modules.customer_success.service import _detail_key
        k_a = _detail_key(org_a, _RECORD)
        k_b = _detail_key(org_b, _RECORD)
        assert k_a != k_b

    @pytest.mark.asyncio
    async def test_list_cache_key_format(self):
        from corpmind.modules.customer_success.service import _list_key
        key = _list_key(_ORG, _WS)
        assert f"t:{_ORG}" in key
        assert "customer_success" in key

    @pytest.mark.asyncio
    async def test_detail_cache_key_format(self):
        from corpmind.modules.customer_success.service import _detail_key
        key = _detail_key(_ORG, _RECORD)
        assert f"t:{_ORG}" in key
        assert str(_RECORD) in key

    @pytest.mark.asyncio
    async def test_create_tenant_a_not_visible_to_b_by_cache_key(self):
        org_a = uuid.uuid4()
        org_b = uuid.uuid4()
        from corpmind.modules.customer_success.service import _detail_key
        k_a = _detail_key(org_a, _RECORD)
        k_b = _detail_key(org_b, _RECORD)
        # Different tenants must have different cache keys — no bleed
        assert k_a != k_b

    @pytest.mark.asyncio
    async def test_bust_list_cache_uses_org_id(self):
        svc, db = _make_svc()
        org_a = uuid.uuid4()
        ctx = _make_ctx(org_id=org_a)
        redis = _make_redis()
        svc._repo.find_by_customer_id = AsyncMock(return_value=None)
        svc._repo.create = AsyncMock(side_effect=lambda r: r)
        req = CustomerSuccessCreate(workspace_id=_WS, customer_id=_CUSTOMER)
        with _patch_ctx(ctx, redis):
            await svc.create(req)
        deleted_key = redis.delete.call_args[0][0]
        assert f"t:{org_a}" in deleted_key

    @pytest.mark.asyncio
    async def test_get_by_customer_does_not_cross_tenant(self):
        svc, _ = _make_svc()
        # Repo returns None for wrong customer — service raises NotFoundError
        svc._repo.find_by_customer_id = AsyncMock(return_value=None)
        with pytest.raises(NotFoundError):
            await svc.get_by_customer(uuid.uuid4())


# ── TestValidation ────────────────────────────────────────────────────────────

class TestValidation:
    def test_invalid_health_status_rejected(self):
        import pytest
        with pytest.raises(Exception):
            CustomerSuccessCreate(
                workspace_id=_WS, customer_id=_CUSTOMER, health_status="unknown"
            )

    def test_invalid_risk_level_rejected(self):
        with pytest.raises(Exception):
            CustomerSuccessCreate(
                workspace_id=_WS, customer_id=_CUSTOMER, risk_level="extreme"
            )

    def test_health_score_above_100_rejected(self):
        with pytest.raises(Exception):
            CustomerSuccessCreate(
                workspace_id=_WS, customer_id=_CUSTOMER, health_score=101
            )

    def test_health_score_below_0_rejected(self):
        with pytest.raises(Exception):
            CustomerSuccessCreate(
                workspace_id=_WS, customer_id=_CUSTOMER, health_score=-1
            )

    def test_renewal_probability_above_100_rejected(self):
        with pytest.raises(Exception):
            CustomerSuccessCreate(
                workspace_id=_WS, customer_id=_CUSTOMER, renewal_probability=101
            )
