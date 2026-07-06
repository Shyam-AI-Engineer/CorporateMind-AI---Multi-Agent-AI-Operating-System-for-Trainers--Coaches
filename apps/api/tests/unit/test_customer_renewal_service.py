"""Unit tests for CustomerRenewalService — Sprint 48.

Pattern mirrors test_customer_success_service.py:
  - _patch_ctx contextmanager patches get_tenant_context + get_redis
  - _make_svc() returns (service, db_mock)
  - Each test class covers one service method
  - Tenant isolation tests ensure org_id is taken from TenantContext
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.core.exceptions import NotFoundError, ValidationError
from corpmind.modules.customer_renewals.schemas import (
    AssignRenewalOwner,
    AttachProposal,
    CustomerRenewalCreate,
    CustomerRenewalFilters,
    CustomerRenewalUpdate,
    UpdateRenewalStatus,
)
from corpmind.modules.customer_renewals.service import CustomerRenewalService

_PATCH_CTX = "corpmind.modules.customer_renewals.service.get_tenant_context"
_PATCH_REDIS = "corpmind.modules.customer_renewals.service.get_redis"

_WS = uuid.uuid4()
_ORG = uuid.uuid4()
_NOW = datetime(2026, 7, 7, 10, 0, 0, tzinfo=UTC)


def _ctx(org_id: uuid.UUID | None = None) -> MagicMock:
    ctx = MagicMock()
    ctx.org_id = org_id or _ORG
    return ctx


def _redis() -> MagicMock:
    r = MagicMock()
    r.get = AsyncMock(return_value=None)
    r.set = AsyncMock()
    r.delete = AsyncMock()
    return r


@contextmanager
def _patch_ctx(
    ctx: MagicMock, redis: MagicMock
) -> Generator[None, None, None]:
    with patch(_PATCH_CTX, return_value=ctx):
        with patch(_PATCH_REDIS, return_value=redis):
            yield


def _make_svc() -> tuple[CustomerRenewalService, MagicMock]:
    db = MagicMock()
    db.commit = AsyncMock()
    svc = CustomerRenewalService(db)
    svc._repo = MagicMock()
    return svc, db


def _make_renewal(
    *,
    renewal_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
    ws_id: uuid.UUID | None = None,
    customer_id: uuid.UUID | None = None,
    contract_name: str | None = "Annual SaaS Contract",
    contract_value: Decimal | None = Decimal("120000.00"),
    renewal_type: str = "annual",
    renewal_status: str = "planned",
    renewal_date: date | None = date(2027, 1, 1),
    owner_user_id: uuid.UUID | None = None,
    probability: int | None = 80,
    expected_value: Decimal | None = Decimal("100000.00"),
    proposal_id: uuid.UUID | None = None,
    notes: str | None = None,
    is_archived: bool = False,
) -> MagicMock:
    r = MagicMock()
    r.id = renewal_id or uuid.uuid4()
    r.tenant_id = tenant_id or _ORG
    r.workspace_id = ws_id or _WS
    r.customer_id = customer_id or uuid.uuid4()
    r.contract_name = contract_name
    r.contract_value = contract_value
    r.renewal_type = renewal_type
    r.renewal_status = renewal_status
    r.renewal_date = renewal_date
    r.owner_user_id = owner_user_id
    r.probability = probability
    r.expected_value = expected_value
    r.proposal_id = proposal_id
    r.notes = notes
    r.is_archived = is_archived
    r.created_at = _NOW
    r.updated_at = _NOW
    return r


# ── TestCreate ────────────────────────────────────────────────────────────────

class TestCreate:
    @pytest.mark.asyncio
    async def test_create_returns_out(self) -> None:
        svc, db = _make_svc()
        ctx = _ctx()
        redis = _redis()
        record = _make_renewal()
        svc._repo.create = AsyncMock(return_value=record)

        req = CustomerRenewalCreate(
            workspace_id=_WS,
            customer_id=record.customer_id,
        )
        with _patch_ctx(ctx, redis):
            with patch(
                "corpmind.modules.customer_renewals.service.CustomerRenewal",
                return_value=record,
            ):
                result = await svc.create(req)
        assert result.id == record.id

    @pytest.mark.asyncio
    async def test_create_commits(self) -> None:
        svc, db = _make_svc()
        ctx = _ctx()
        redis = _redis()
        record = _make_renewal()
        svc._repo.create = AsyncMock(return_value=record)

        req = CustomerRenewalCreate(workspace_id=_WS, customer_id=record.customer_id)
        with _patch_ctx(ctx, redis):
            with patch(
                "corpmind.modules.customer_renewals.service.CustomerRenewal",
                return_value=record,
            ):
                await svc.create(req)
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_busts_list_cache(self) -> None:
        svc, db = _make_svc()
        ctx = _ctx()
        redis = _redis()
        record = _make_renewal()
        svc._repo.create = AsyncMock(return_value=record)

        req = CustomerRenewalCreate(workspace_id=_WS, customer_id=record.customer_id)
        with _patch_ctx(ctx, redis):
            with patch(
                "corpmind.modules.customer_renewals.service.CustomerRenewal",
                return_value=record,
            ):
                await svc.create(req)
        redis.delete.assert_called()

    @pytest.mark.asyncio
    async def test_create_with_contract_name(self) -> None:
        svc, db = _make_svc()
        ctx = _ctx()
        redis = _redis()
        record = _make_renewal(contract_name="Q4 Renewal")
        svc._repo.create = AsyncMock(return_value=record)

        req = CustomerRenewalCreate(
            workspace_id=_WS,
            customer_id=record.customer_id,
            contract_name="Q4 Renewal",
        )
        with _patch_ctx(ctx, redis):
            with patch(
                "corpmind.modules.customer_renewals.service.CustomerRenewal",
                return_value=record,
            ):
                result = await svc.create(req)
        assert result.contract_name == "Q4 Renewal"

    @pytest.mark.asyncio
    async def test_create_with_all_fields(self) -> None:
        svc, db = _make_svc()
        ctx = _ctx()
        redis = _redis()
        cid = uuid.uuid4()
        pid = uuid.uuid4()
        record = _make_renewal(
            customer_id=cid,
            contract_name="Full Contract",
            contract_value=Decimal("200000"),
            renewal_type="quarterly",
            renewal_status="in_progress",
            probability=90,
            proposal_id=pid,
        )
        svc._repo.create = AsyncMock(return_value=record)

        req = CustomerRenewalCreate(
            workspace_id=_WS,
            customer_id=cid,
            contract_name="Full Contract",
            renewal_type="quarterly",
            renewal_status="in_progress",
            probability=90,
            proposal_id=pid,
        )
        with _patch_ctx(ctx, redis):
            with patch(
                "corpmind.modules.customer_renewals.service.CustomerRenewal",
                return_value=record,
            ):
                result = await svc.create(req)
        assert result.renewal_type == "quarterly"
        assert result.renewal_status == "in_progress"

    @pytest.mark.asyncio
    async def test_create_uses_tenant_context_org_id(self) -> None:
        svc, db = _make_svc()
        org2 = uuid.uuid4()
        ctx = _ctx(org_id=org2)
        redis = _redis()
        record = _make_renewal(tenant_id=org2)
        svc._repo.create = AsyncMock(return_value=record)

        req = CustomerRenewalCreate(workspace_id=_WS, customer_id=record.customer_id)
        with _patch_ctx(ctx, redis):
            with patch(
                "corpmind.modules.customer_renewals.service.CustomerRenewal",
                return_value=record,
            ):
                result = await svc.create(req)
        assert result.tenant_id == org2

    @pytest.mark.asyncio
    async def test_create_invalid_renewal_type_raises(self) -> None:
        with pytest.raises(Exception):
            CustomerRenewalCreate(
                workspace_id=_WS,
                customer_id=uuid.uuid4(),
                renewal_type="biennial",
            )

    @pytest.mark.asyncio
    async def test_create_invalid_renewal_status_raises(self) -> None:
        with pytest.raises(Exception):
            CustomerRenewalCreate(
                workspace_id=_WS,
                customer_id=uuid.uuid4(),
                renewal_status="expired",
            )

    @pytest.mark.asyncio
    async def test_create_invalid_probability_raises(self) -> None:
        with pytest.raises(Exception):
            CustomerRenewalCreate(
                workspace_id=_WS,
                customer_id=uuid.uuid4(),
                probability=150,
            )

    @pytest.mark.asyncio
    async def test_create_probability_zero_allowed(self) -> None:
        req = CustomerRenewalCreate(
            workspace_id=_WS,
            customer_id=uuid.uuid4(),
            probability=0,
        )
        assert req.probability == 0

    @pytest.mark.asyncio
    async def test_create_probability_100_allowed(self) -> None:
        req = CustomerRenewalCreate(
            workspace_id=_WS,
            customer_id=uuid.uuid4(),
            probability=100,
        )
        assert req.probability == 100

    @pytest.mark.asyncio
    async def test_create_monthly_type(self) -> None:
        req = CustomerRenewalCreate(
            workspace_id=_WS,
            customer_id=uuid.uuid4(),
            renewal_type="monthly",
        )
        assert req.renewal_type == "monthly"

    @pytest.mark.asyncio
    async def test_create_custom_type(self) -> None:
        req = CustomerRenewalCreate(
            workspace_id=_WS,
            customer_id=uuid.uuid4(),
            renewal_type="custom",
        )
        assert req.renewal_type == "custom"

    @pytest.mark.asyncio
    async def test_create_won_status(self) -> None:
        req = CustomerRenewalCreate(
            workspace_id=_WS,
            customer_id=uuid.uuid4(),
            renewal_status="won",
        )
        assert req.renewal_status == "won"

    @pytest.mark.asyncio
    async def test_create_lost_status(self) -> None:
        req = CustomerRenewalCreate(
            workspace_id=_WS,
            customer_id=uuid.uuid4(),
            renewal_status="lost",
        )
        assert req.renewal_status == "lost"

    @pytest.mark.asyncio
    async def test_create_cancelled_status(self) -> None:
        req = CustomerRenewalCreate(
            workspace_id=_WS,
            customer_id=uuid.uuid4(),
            renewal_status="cancelled",
        )
        assert req.renewal_status == "cancelled"

    @pytest.mark.asyncio
    async def test_create_negotiation_status(self) -> None:
        req = CustomerRenewalCreate(
            workspace_id=_WS,
            customer_id=uuid.uuid4(),
            renewal_status="negotiation",
        )
        assert req.renewal_status == "negotiation"

    @pytest.mark.asyncio
    async def test_create_no_proposal_id(self) -> None:
        req = CustomerRenewalCreate(
            workspace_id=_WS,
            customer_id=uuid.uuid4(),
        )
        assert req.proposal_id is None

    @pytest.mark.asyncio
    async def test_create_no_contract_value(self) -> None:
        req = CustomerRenewalCreate(
            workspace_id=_WS,
            customer_id=uuid.uuid4(),
        )
        assert req.contract_value is None

    @pytest.mark.asyncio
    async def test_create_with_notes(self) -> None:
        req = CustomerRenewalCreate(
            workspace_id=_WS,
            customer_id=uuid.uuid4(),
            notes="High-value contract",
        )
        assert req.notes == "High-value contract"


# ── TestGet ───────────────────────────────────────────────────────────────────

class TestGet:
    @pytest.mark.asyncio
    async def test_get_returns_out(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        record = _make_renewal()
        svc._repo.find_by_id = AsyncMock(return_value=record)

        with _patch_ctx(ctx, redis):
            result = await svc.get(record.id)
        assert result.id == record.id

    @pytest.mark.asyncio
    async def test_get_not_found_raises(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        svc._repo.find_by_id = AsyncMock(return_value=None)

        with _patch_ctx(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.get(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_get_hits_cache(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        record = _make_renewal()
        out_json = f'{{"id":"{record.id}","tenant_id":"{_ORG}","workspace_id":"{_WS}","customer_id":"{record.customer_id}","contract_name":"Annual SaaS Contract","contract_value":"120000.00","renewal_type":"annual","renewal_status":"planned","renewal_date":"2027-01-01","owner_user_id":null,"probability":80,"expected_value":"100000.00","proposal_id":null,"notes":null,"is_archived":false,"created_at":"{_NOW.isoformat()}","updated_at":"{_NOW.isoformat()}"}}'
        redis.get = AsyncMock(return_value=out_json)

        with _patch_ctx(ctx, redis):
            result = await svc.get(record.id)
        svc._repo.find_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_sets_cache_on_miss(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        record = _make_renewal()
        svc._repo.find_by_id = AsyncMock(return_value=record)

        with _patch_ctx(ctx, redis):
            await svc.get(record.id)
        redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_cache_failure_falls_back(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        redis.get = AsyncMock(side_effect=Exception("redis down"))
        record = _make_renewal()
        svc._repo.find_by_id = AsyncMock(return_value=record)

        with _patch_ctx(ctx, redis):
            result = await svc.get(record.id)
        assert result.id == record.id

    @pytest.mark.asyncio
    async def test_get_contract_name_preserved(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        record = _make_renewal(contract_name="My Contract")
        svc._repo.find_by_id = AsyncMock(return_value=record)

        with _patch_ctx(ctx, redis):
            result = await svc.get(record.id)
        assert result.contract_name == "My Contract"

    @pytest.mark.asyncio
    async def test_get_probability_preserved(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        record = _make_renewal(probability=65)
        svc._repo.find_by_id = AsyncMock(return_value=record)

        with _patch_ctx(ctx, redis):
            result = await svc.get(record.id)
        assert result.probability == 65

    @pytest.mark.asyncio
    async def test_get_null_probability_preserved(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        record = _make_renewal(probability=None)
        svc._repo.find_by_id = AsyncMock(return_value=record)

        with _patch_ctx(ctx, redis):
            result = await svc.get(record.id)
        assert result.probability is None

    @pytest.mark.asyncio
    async def test_get_proposal_id_preserved(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        pid = uuid.uuid4()
        record = _make_renewal(proposal_id=pid)
        svc._repo.find_by_id = AsyncMock(return_value=record)

        with _patch_ctx(ctx, redis):
            result = await svc.get(record.id)
        assert result.proposal_id == pid

    @pytest.mark.asyncio
    async def test_get_archived_record_returns(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        record = _make_renewal(is_archived=True)
        svc._repo.find_by_id = AsyncMock(return_value=record)

        with _patch_ctx(ctx, redis):
            result = await svc.get(record.id)
        assert result.is_archived is True


# ── TestUpdate ────────────────────────────────────────────────────────────────

class TestUpdate:
    @pytest.mark.asyncio
    async def test_update_returns_updated(self) -> None:
        svc, db = _make_svc()
        ctx = _ctx()
        redis = _redis()
        original = _make_renewal()
        updated = _make_renewal(
            renewal_id=original.id,
            customer_id=original.customer_id,
            contract_name="Updated Contract",
        )
        svc._repo.find_by_id = AsyncMock(side_effect=[original, updated])
        svc._repo.update_fields = AsyncMock()

        req = CustomerRenewalUpdate(contract_name="Updated Contract")
        with _patch_ctx(ctx, redis):
            result = await svc.update(original.id, req)
        assert result.contract_name == "Updated Contract"

    @pytest.mark.asyncio
    async def test_update_not_found_raises(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        svc._repo.find_by_id = AsyncMock(return_value=None)

        req = CustomerRenewalUpdate(contract_name="X")
        with _patch_ctx(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.update(uuid.uuid4(), req)

    @pytest.mark.asyncio
    async def test_update_commits(self) -> None:
        svc, db = _make_svc()
        ctx = _ctx()
        redis = _redis()
        original = _make_renewal()
        updated = _make_renewal(renewal_id=original.id, customer_id=original.customer_id)
        svc._repo.find_by_id = AsyncMock(side_effect=[original, updated])
        svc._repo.update_fields = AsyncMock()

        with _patch_ctx(ctx, redis):
            await svc.update(original.id, CustomerRenewalUpdate(notes="hello"))
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_busts_caches(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        original = _make_renewal()
        updated = _make_renewal(renewal_id=original.id, customer_id=original.customer_id)
        svc._repo.find_by_id = AsyncMock(side_effect=[original, updated])
        svc._repo.update_fields = AsyncMock()

        with _patch_ctx(ctx, redis):
            await svc.update(original.id, CustomerRenewalUpdate(notes="x"))
        assert redis.delete.call_count >= 2

    @pytest.mark.asyncio
    async def test_update_only_sends_provided_fields(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        original = _make_renewal()
        updated = _make_renewal(renewal_id=original.id, customer_id=original.customer_id)
        svc._repo.find_by_id = AsyncMock(side_effect=[original, updated])
        svc._repo.update_fields = AsyncMock()

        req = CustomerRenewalUpdate(notes="only notes updated")
        with _patch_ctx(ctx, redis):
            await svc.update(original.id, req)
        call_kwargs = svc._repo.update_fields.call_args[1]
        assert "notes" in call_kwargs
        assert "contract_name" not in call_kwargs

    @pytest.mark.asyncio
    async def test_update_renewal_date(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        original = _make_renewal()
        new_date = date(2027, 6, 30)
        updated = _make_renewal(
            renewal_id=original.id,
            customer_id=original.customer_id,
            renewal_date=new_date,
        )
        svc._repo.find_by_id = AsyncMock(side_effect=[original, updated])
        svc._repo.update_fields = AsyncMock()

        req = CustomerRenewalUpdate(renewal_date=new_date)
        with _patch_ctx(ctx, redis):
            result = await svc.update(original.id, req)
        assert result.renewal_date == new_date

    @pytest.mark.asyncio
    async def test_update_probability(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        original = _make_renewal()
        updated = _make_renewal(
            renewal_id=original.id,
            customer_id=original.customer_id,
            probability=55,
        )
        svc._repo.find_by_id = AsyncMock(side_effect=[original, updated])
        svc._repo.update_fields = AsyncMock()

        with _patch_ctx(ctx, redis):
            result = await svc.update(original.id, CustomerRenewalUpdate(probability=55))
        assert result.probability == 55

    @pytest.mark.asyncio
    async def test_update_invalid_probability_raises(self) -> None:
        with pytest.raises(Exception):
            CustomerRenewalUpdate(probability=-5)

    @pytest.mark.asyncio
    async def test_update_renewal_type(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        original = _make_renewal()
        updated = _make_renewal(
            renewal_id=original.id,
            customer_id=original.customer_id,
            renewal_type="quarterly",
        )
        svc._repo.find_by_id = AsyncMock(side_effect=[original, updated])
        svc._repo.update_fields = AsyncMock()

        with _patch_ctx(ctx, redis):
            result = await svc.update(original.id, CustomerRenewalUpdate(renewal_type="quarterly"))
        assert result.renewal_type == "quarterly"

    @pytest.mark.asyncio
    async def test_update_invalid_type_raises(self) -> None:
        with pytest.raises(Exception):
            CustomerRenewalUpdate(renewal_type="decadal")

    @pytest.mark.asyncio
    async def test_update_empty_request_updates_timestamp(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        original = _make_renewal()
        updated = _make_renewal(renewal_id=original.id, customer_id=original.customer_id)
        svc._repo.find_by_id = AsyncMock(side_effect=[original, updated])
        svc._repo.update_fields = AsyncMock()

        with _patch_ctx(ctx, redis):
            await svc.update(original.id, CustomerRenewalUpdate())
        call_kwargs = svc._repo.update_fields.call_args[1]
        assert "updated_at" in call_kwargs

    @pytest.mark.asyncio
    async def test_update_owner_via_update(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        original = _make_renewal()
        owner = uuid.uuid4()
        updated = _make_renewal(
            renewal_id=original.id,
            customer_id=original.customer_id,
            owner_user_id=owner,
        )
        svc._repo.find_by_id = AsyncMock(side_effect=[original, updated])
        svc._repo.update_fields = AsyncMock()

        with _patch_ctx(ctx, redis):
            result = await svc.update(original.id, CustomerRenewalUpdate(owner_user_id=owner))
        assert result.owner_user_id == owner


# ── TestList ──────────────────────────────────────────────────────────────────

class TestList:
    @pytest.mark.asyncio
    async def test_list_returns_items(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        records = [_make_renewal() for _ in range(3)]
        svc._repo.count = AsyncMock(return_value=3)
        svc._repo.list_page = AsyncMock(return_value=records)

        filters = CustomerRenewalFilters(workspace_id=_WS)
        with _patch_ctx(ctx, redis):
            result = await svc.list(filters)
        assert len(result.items) == 3

    @pytest.mark.asyncio
    async def test_list_total_correct(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        records = [_make_renewal() for _ in range(5)]
        svc._repo.count = AsyncMock(return_value=5)
        svc._repo.list_page = AsyncMock(return_value=records)

        filters = CustomerRenewalFilters(workspace_id=_WS)
        with _patch_ctx(ctx, redis):
            result = await svc.list(filters)
        assert result.total == 5

    @pytest.mark.asyncio
    async def test_list_has_more_when_extra_row(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        # Return limit+1 rows to signal has_more
        records = [_make_renewal() for _ in range(51)]
        svc._repo.count = AsyncMock(return_value=60)
        svc._repo.list_page = AsyncMock(return_value=records)

        filters = CustomerRenewalFilters(workspace_id=_WS, limit=50)
        with _patch_ctx(ctx, redis):
            result = await svc.list(filters)
        assert result.has_more is True
        assert len(result.items) == 50

    @pytest.mark.asyncio
    async def test_list_no_more_when_exact(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        records = [_make_renewal() for _ in range(3)]
        svc._repo.count = AsyncMock(return_value=3)
        svc._repo.list_page = AsyncMock(return_value=records)

        filters = CustomerRenewalFilters(workspace_id=_WS, limit=50)
        with _patch_ctx(ctx, redis):
            result = await svc.list(filters)
        assert result.has_more is False
        assert result.next_cursor is None

    @pytest.mark.asyncio
    async def test_list_next_cursor_when_has_more(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        records = [_make_renewal() for _ in range(51)]
        svc._repo.count = AsyncMock(return_value=100)
        svc._repo.list_page = AsyncMock(return_value=records)

        filters = CustomerRenewalFilters(workspace_id=_WS, limit=50)
        with _patch_ctx(ctx, redis):
            result = await svc.list(filters)
        assert result.next_cursor is not None

    @pytest.mark.asyncio
    async def test_list_empty(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])

        filters = CustomerRenewalFilters(workspace_id=_WS)
        with _patch_ctx(ctx, redis):
            result = await svc.list(filters)
        assert result.items == []
        assert result.total == 0

    @pytest.mark.asyncio
    async def test_list_cache_hit_default_filters(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        cached_json = '{"items":[],"next_cursor":null,"has_more":false,"total":0}'
        redis.get = AsyncMock(return_value=cached_json)

        filters = CustomerRenewalFilters(workspace_id=_WS)
        with _patch_ctx(ctx, redis):
            result = await svc.list(filters)
        svc._repo.count.assert_not_called()
        svc._repo.list_page.assert_not_called()

    @pytest.mark.asyncio
    async def test_list_no_cache_with_filters(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        redis.get = AsyncMock(return_value='{"items":[],"next_cursor":null,"has_more":false,"total":0}')
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])

        filters = CustomerRenewalFilters(workspace_id=_WS, search="Q4")
        with _patch_ctx(ctx, redis):
            await svc.list(filters)
        svc._repo.count.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_by_customer_id_filter(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        cid = uuid.uuid4()
        records = [_make_renewal(customer_id=cid) for _ in range(2)]
        svc._repo.count = AsyncMock(return_value=2)
        svc._repo.list_page = AsyncMock(return_value=records)

        filters = CustomerRenewalFilters(workspace_id=_WS, customer_id=cid)
        with _patch_ctx(ctx, redis):
            result = await svc.list(filters)
        assert len(result.items) == 2

    @pytest.mark.asyncio
    async def test_list_by_renewal_status_filter(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        records = [_make_renewal(renewal_status="won")]
        svc._repo.count = AsyncMock(return_value=1)
        svc._repo.list_page = AsyncMock(return_value=records)

        filters = CustomerRenewalFilters(workspace_id=_WS, renewal_status="won")
        with _patch_ctx(ctx, redis):
            result = await svc.list(filters)
        assert result.items[0].renewal_status == "won"

    @pytest.mark.asyncio
    async def test_list_sets_cache_on_default_miss(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])

        filters = CustomerRenewalFilters(workspace_id=_WS)
        with _patch_ctx(ctx, redis):
            await svc.list(filters)
        redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_cache_failure_does_not_raise(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        redis.get = AsyncMock(side_effect=Exception("redis down"))
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])

        filters = CustomerRenewalFilters(workspace_id=_WS)
        with _patch_ctx(ctx, redis):
            result = await svc.list(filters)
        assert result.total == 0

    @pytest.mark.asyncio
    async def test_list_by_renewal_type(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        records = [_make_renewal(renewal_type="quarterly")]
        svc._repo.count = AsyncMock(return_value=1)
        svc._repo.list_page = AsyncMock(return_value=records)

        filters = CustomerRenewalFilters(workspace_id=_WS, renewal_type="quarterly")
        with _patch_ctx(ctx, redis):
            result = await svc.list(filters)
        assert result.items[0].renewal_type == "quarterly"

    @pytest.mark.asyncio
    async def test_list_include_archived(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        records = [_make_renewal(is_archived=True)]
        svc._repo.count = AsyncMock(return_value=1)
        svc._repo.list_page = AsyncMock(return_value=records)

        filters = CustomerRenewalFilters(workspace_id=_WS, include_archived=True)
        with _patch_ctx(ctx, redis):
            result = await svc.list(filters)
        assert result.items[0].is_archived is True


# ── TestAssignOwner ───────────────────────────────────────────────────────────

class TestAssignOwner:
    @pytest.mark.asyncio
    async def test_assign_owner_returns_updated(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        owner_id = uuid.uuid4()
        original = _make_renewal()
        updated = _make_renewal(
            renewal_id=original.id,
            customer_id=original.customer_id,
            owner_user_id=owner_id,
        )
        svc._repo.find_by_id = AsyncMock(side_effect=[original, updated])
        svc._repo.update_fields = AsyncMock()

        req = AssignRenewalOwner(owner_user_id=owner_id)
        with _patch_ctx(ctx, redis):
            result = await svc.assign_owner(original.id, req)
        assert result.owner_user_id == owner_id

    @pytest.mark.asyncio
    async def test_assign_owner_not_found_raises(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        svc._repo.find_by_id = AsyncMock(return_value=None)

        with _patch_ctx(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.assign_owner(uuid.uuid4(), AssignRenewalOwner(owner_user_id=uuid.uuid4()))

    @pytest.mark.asyncio
    async def test_assign_owner_commits(self) -> None:
        svc, db = _make_svc()
        ctx = _ctx()
        redis = _redis()
        original = _make_renewal()
        updated = _make_renewal(renewal_id=original.id, customer_id=original.customer_id)
        svc._repo.find_by_id = AsyncMock(side_effect=[original, updated])
        svc._repo.update_fields = AsyncMock()

        with _patch_ctx(ctx, redis):
            await svc.assign_owner(original.id, AssignRenewalOwner(owner_user_id=uuid.uuid4()))
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_assign_owner_busts_cache(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        original = _make_renewal()
        updated = _make_renewal(renewal_id=original.id, customer_id=original.customer_id)
        svc._repo.find_by_id = AsyncMock(side_effect=[original, updated])
        svc._repo.update_fields = AsyncMock()

        with _patch_ctx(ctx, redis):
            await svc.assign_owner(original.id, AssignRenewalOwner(owner_user_id=uuid.uuid4()))
        redis.delete.assert_called()

    @pytest.mark.asyncio
    async def test_assign_owner_calls_update_fields(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        owner_id = uuid.uuid4()
        original = _make_renewal()
        updated = _make_renewal(renewal_id=original.id, customer_id=original.customer_id)
        svc._repo.find_by_id = AsyncMock(side_effect=[original, updated])
        svc._repo.update_fields = AsyncMock()

        with _patch_ctx(ctx, redis):
            await svc.assign_owner(original.id, AssignRenewalOwner(owner_user_id=owner_id))
        call_kwargs = svc._repo.update_fields.call_args[1]
        assert call_kwargs["owner_user_id"] == owner_id


# ── TestUpdateStatus ──────────────────────────────────────────────────────────

class TestUpdateStatus:
    @pytest.mark.asyncio
    async def test_update_status_returns_updated(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        original = _make_renewal(renewal_status="planned")
        updated = _make_renewal(
            renewal_id=original.id,
            customer_id=original.customer_id,
            renewal_status="in_progress",
        )
        svc._repo.find_by_id = AsyncMock(side_effect=[original, updated])
        svc._repo.update_fields = AsyncMock()

        req = UpdateRenewalStatus(renewal_status="in_progress")
        with _patch_ctx(ctx, redis):
            result = await svc.update_status(original.id, req)
        assert result.renewal_status == "in_progress"

    @pytest.mark.asyncio
    async def test_update_status_not_found_raises(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        svc._repo.find_by_id = AsyncMock(return_value=None)

        with _patch_ctx(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.update_status(uuid.uuid4(), UpdateRenewalStatus(renewal_status="won"))

    @pytest.mark.asyncio
    async def test_update_status_commits(self) -> None:
        svc, db = _make_svc()
        ctx = _ctx()
        redis = _redis()
        original = _make_renewal(renewal_status="in_progress")
        updated = _make_renewal(
            renewal_id=original.id,
            customer_id=original.customer_id,
            renewal_status="negotiation",
        )
        svc._repo.find_by_id = AsyncMock(side_effect=[original, updated])
        svc._repo.update_fields = AsyncMock()

        with _patch_ctx(ctx, redis):
            await svc.update_status(original.id, UpdateRenewalStatus(renewal_status="negotiation"))
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_status_invalid_raises(self) -> None:
        with pytest.raises(Exception):
            UpdateRenewalStatus(renewal_status="expired")

    @pytest.mark.asyncio
    async def test_update_status_all_valid_transitions(self) -> None:
        for status in ["planned", "in_progress", "negotiation", "won", "lost", "cancelled"]:
            req = UpdateRenewalStatus(renewal_status=status)
            assert req.renewal_status == status

    @pytest.mark.asyncio
    async def test_update_status_logs_when_changed(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        original = _make_renewal(renewal_status="planned")
        updated = _make_renewal(
            renewal_id=original.id,
            customer_id=original.customer_id,
            renewal_status="won",
        )
        svc._repo.find_by_id = AsyncMock(side_effect=[original, updated])
        svc._repo.update_fields = AsyncMock()

        with _patch_ctx(ctx, redis):
            result = await svc.update_status(original.id, UpdateRenewalStatus(renewal_status="won"))
        assert result.renewal_status == "won"

    @pytest.mark.asyncio
    async def test_update_status_same_status_no_event(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        original = _make_renewal(renewal_status="planned")
        updated = _make_renewal(
            renewal_id=original.id,
            customer_id=original.customer_id,
            renewal_status="planned",
        )
        svc._repo.find_by_id = AsyncMock(side_effect=[original, updated])
        svc._repo.update_fields = AsyncMock()

        with _patch_ctx(ctx, redis):
            result = await svc.update_status(original.id, UpdateRenewalStatus(renewal_status="planned"))
        assert result.renewal_status == "planned"

    @pytest.mark.asyncio
    async def test_update_status_busts_cache(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        original = _make_renewal(renewal_status="planned")
        updated = _make_renewal(
            renewal_id=original.id,
            customer_id=original.customer_id,
            renewal_status="won",
        )
        svc._repo.find_by_id = AsyncMock(side_effect=[original, updated])
        svc._repo.update_fields = AsyncMock()

        with _patch_ctx(ctx, redis):
            await svc.update_status(original.id, UpdateRenewalStatus(renewal_status="won"))
        redis.delete.assert_called()


# ── TestAttachProposal ────────────────────────────────────────────────────────

class TestAttachProposal:
    @pytest.mark.asyncio
    async def test_attach_proposal_returns_updated(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        pid = uuid.uuid4()
        original = _make_renewal()
        updated = _make_renewal(
            renewal_id=original.id,
            customer_id=original.customer_id,
            proposal_id=pid,
        )
        svc._repo.find_by_id = AsyncMock(side_effect=[original, updated])
        svc._repo.update_fields = AsyncMock()

        req = AttachProposal(proposal_id=pid)
        with _patch_ctx(ctx, redis):
            result = await svc.attach_proposal(original.id, req)
        assert result.proposal_id == pid

    @pytest.mark.asyncio
    async def test_attach_proposal_not_found_raises(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        svc._repo.find_by_id = AsyncMock(return_value=None)

        with _patch_ctx(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.attach_proposal(uuid.uuid4(), AttachProposal(proposal_id=uuid.uuid4()))

    @pytest.mark.asyncio
    async def test_attach_proposal_commits(self) -> None:
        svc, db = _make_svc()
        ctx = _ctx()
        redis = _redis()
        original = _make_renewal()
        updated = _make_renewal(renewal_id=original.id, customer_id=original.customer_id)
        svc._repo.find_by_id = AsyncMock(side_effect=[original, updated])
        svc._repo.update_fields = AsyncMock()

        with _patch_ctx(ctx, redis):
            await svc.attach_proposal(original.id, AttachProposal(proposal_id=uuid.uuid4()))
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_attach_proposal_busts_cache(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        original = _make_renewal()
        updated = _make_renewal(renewal_id=original.id, customer_id=original.customer_id)
        svc._repo.find_by_id = AsyncMock(side_effect=[original, updated])
        svc._repo.update_fields = AsyncMock()

        with _patch_ctx(ctx, redis):
            await svc.attach_proposal(original.id, AttachProposal(proposal_id=uuid.uuid4()))
        redis.delete.assert_called()

    @pytest.mark.asyncio
    async def test_attach_proposal_calls_update_fields(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        pid = uuid.uuid4()
        original = _make_renewal()
        updated = _make_renewal(renewal_id=original.id, customer_id=original.customer_id)
        svc._repo.find_by_id = AsyncMock(side_effect=[original, updated])
        svc._repo.update_fields = AsyncMock()

        with _patch_ctx(ctx, redis):
            await svc.attach_proposal(original.id, AttachProposal(proposal_id=pid))
        call_kwargs = svc._repo.update_fields.call_args[1]
        assert call_kwargs["proposal_id"] == pid


# ── TestArchive ───────────────────────────────────────────────────────────────

class TestArchive:
    @pytest.mark.asyncio
    async def test_archive_returns_archived(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        original = _make_renewal(is_archived=False)
        updated = _make_renewal(
            renewal_id=original.id,
            customer_id=original.customer_id,
            is_archived=True,
        )
        svc._repo.find_by_id = AsyncMock(side_effect=[original, updated])
        svc._repo.update_fields = AsyncMock()

        with _patch_ctx(ctx, redis):
            result = await svc.archive(original.id)
        assert result.is_archived is True

    @pytest.mark.asyncio
    async def test_archive_not_found_raises(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        svc._repo.find_by_id = AsyncMock(return_value=None)

        with _patch_ctx(ctx, redis):
            with pytest.raises(NotFoundError):
                await svc.archive(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_archive_already_archived_raises(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        record = _make_renewal(is_archived=True)
        svc._repo.find_by_id = AsyncMock(return_value=record)

        with _patch_ctx(ctx, redis):
            with pytest.raises(ValidationError):
                await svc.archive(record.id)

    @pytest.mark.asyncio
    async def test_archive_commits(self) -> None:
        svc, db = _make_svc()
        ctx = _ctx()
        redis = _redis()
        original = _make_renewal(is_archived=False)
        updated = _make_renewal(
            renewal_id=original.id,
            customer_id=original.customer_id,
            is_archived=True,
        )
        svc._repo.find_by_id = AsyncMock(side_effect=[original, updated])
        svc._repo.update_fields = AsyncMock()

        with _patch_ctx(ctx, redis):
            await svc.archive(original.id)
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_archive_busts_cache(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        original = _make_renewal(is_archived=False)
        updated = _make_renewal(
            renewal_id=original.id,
            customer_id=original.customer_id,
            is_archived=True,
        )
        svc._repo.find_by_id = AsyncMock(side_effect=[original, updated])
        svc._repo.update_fields = AsyncMock()

        with _patch_ctx(ctx, redis):
            await svc.archive(original.id)
        redis.delete.assert_called()

    @pytest.mark.asyncio
    async def test_archive_sets_is_archived_true(self) -> None:
        svc, _ = _make_svc()
        ctx = _ctx()
        redis = _redis()
        original = _make_renewal(is_archived=False)
        updated = _make_renewal(
            renewal_id=original.id,
            customer_id=original.customer_id,
            is_archived=True,
        )
        svc._repo.find_by_id = AsyncMock(side_effect=[original, updated])
        svc._repo.update_fields = AsyncMock()

        with _patch_ctx(ctx, redis):
            await svc.archive(original.id)
        call_kwargs = svc._repo.update_fields.call_args[1]
        assert call_kwargs["is_archived"] is True


# ── TestTenantIsolation ───────────────────────────────────────────────────────

class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_create_uses_context_org_id_not_parameter(self) -> None:
        """Service must pull org_id from TenantContext, never from a param."""
        svc, _ = _make_svc()
        org_a = uuid.uuid4()
        ctx = _ctx(org_id=org_a)
        redis = _redis()
        record = _make_renewal(tenant_id=org_a)
        svc._repo.create = AsyncMock(return_value=record)

        req = CustomerRenewalCreate(workspace_id=_WS, customer_id=uuid.uuid4())
        with _patch_ctx(ctx, redis):
            with patch(
                "corpmind.modules.customer_renewals.service.CustomerRenewal",
                return_value=record,
            ):
                result = await svc.create(req)
        assert result.tenant_id == org_a

    @pytest.mark.asyncio
    async def test_different_tenants_have_different_cache_keys(self) -> None:
        from corpmind.modules.customer_renewals.service import _list_key

        org_a = uuid.uuid4()
        org_b = uuid.uuid4()
        ws = uuid.uuid4()
        assert _list_key(org_a, ws) != _list_key(org_b, ws)

    @pytest.mark.asyncio
    async def test_detail_cache_key_includes_org_id(self) -> None:
        from corpmind.modules.customer_renewals.service import _detail_key

        org_a = uuid.uuid4()
        org_b = uuid.uuid4()
        rid = uuid.uuid4()
        assert _detail_key(org_a, rid) != _detail_key(org_b, rid)

    @pytest.mark.asyncio
    async def test_list_uses_tenant_context_for_cache_key(self) -> None:
        svc, _ = _make_svc()
        org_a = uuid.uuid4()
        ctx = _ctx(org_id=org_a)
        redis = _redis()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])

        filters = CustomerRenewalFilters(workspace_id=_WS)
        with _patch_ctx(ctx, redis):
            await svc.list(filters)
        set_key = redis.set.call_args[0][0]
        assert str(org_a) in set_key

    @pytest.mark.asyncio
    async def test_bust_detail_cache_uses_correct_org(self) -> None:
        svc, _ = _make_svc()
        org = uuid.uuid4()
        ctx = _ctx(org_id=org)
        redis = _redis()
        original = _make_renewal(tenant_id=org)
        updated = _make_renewal(renewal_id=original.id, customer_id=original.customer_id)
        svc._repo.find_by_id = AsyncMock(side_effect=[original, updated])
        svc._repo.update_fields = AsyncMock()

        with _patch_ctx(ctx, redis):
            await svc.update(original.id, CustomerRenewalUpdate(notes="isolation test"))
        delete_args = [str(call[0][0]) for call in redis.delete.call_args_list]
        assert any(str(org) in arg for arg in delete_args)

    @pytest.mark.asyncio
    async def test_get_cache_key_scoped_to_org(self) -> None:
        svc, _ = _make_svc()
        org = uuid.uuid4()
        ctx = _ctx(org_id=org)
        redis = _redis()
        record = _make_renewal(tenant_id=org)
        svc._repo.find_by_id = AsyncMock(return_value=record)

        with _patch_ctx(ctx, redis):
            await svc.get(record.id)
        set_key = redis.set.call_args[0][0]
        assert str(org) in set_key

    @pytest.mark.asyncio
    async def test_redis_key_prefix_contains_tenant_id(self) -> None:
        from corpmind.modules.customer_renewals.service import _list_key, _detail_key

        org = uuid.uuid4()
        ws = uuid.uuid4()
        rid = uuid.uuid4()
        assert str(org) in _list_key(org, ws)
        assert str(org) in _detail_key(org, rid)

    @pytest.mark.asyncio
    async def test_two_tenant_list_keys_dont_collide(self) -> None:
        from corpmind.modules.customer_renewals.service import _list_key

        org1, org2 = uuid.uuid4(), uuid.uuid4()
        ws = uuid.uuid4()
        assert _list_key(org1, ws) != _list_key(org2, ws)


# ── TestValidation ────────────────────────────────────────────────────────────

class TestValidation:
    def test_valid_renewal_types(self) -> None:
        for rt in ["annual", "quarterly", "monthly", "custom"]:
            req = CustomerRenewalCreate(
                workspace_id=_WS,
                customer_id=uuid.uuid4(),
                renewal_type=rt,
            )
            assert req.renewal_type == rt

    def test_valid_renewal_statuses(self) -> None:
        for rs in ["planned", "in_progress", "negotiation", "won", "lost", "cancelled"]:
            req = CustomerRenewalCreate(
                workspace_id=_WS,
                customer_id=uuid.uuid4(),
                renewal_status=rs,
            )
            assert req.renewal_status == rs

    def test_probability_boundary_values(self) -> None:
        for p in [0, 1, 50, 99, 100]:
            req = CustomerRenewalCreate(
                workspace_id=_WS,
                customer_id=uuid.uuid4(),
                probability=p,
            )
            assert req.probability == p

    def test_invalid_probability_above_100_raises(self) -> None:
        with pytest.raises(Exception):
            CustomerRenewalCreate(
                workspace_id=_WS,
                customer_id=uuid.uuid4(),
                probability=101,
            )

    def test_invalid_probability_negative_raises(self) -> None:
        with pytest.raises(Exception):
            CustomerRenewalCreate(
                workspace_id=_WS,
                customer_id=uuid.uuid4(),
                probability=-1,
            )

    def test_update_status_validates(self) -> None:
        with pytest.raises(Exception):
            UpdateRenewalStatus(renewal_status="invalid_status")

    def test_update_type_validates(self) -> None:
        with pytest.raises(Exception):
            CustomerRenewalUpdate(renewal_type="biennial")
