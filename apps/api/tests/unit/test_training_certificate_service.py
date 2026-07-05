"""Unit tests for TrainingCertificateService — Sprint 45."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corpmind.core.exceptions import NotFoundError, ValidationError
from corpmind.modules.training.service import (
    TrainingCertificateService,
    _cert_detail_key,
    _cert_list_key,
)
from corpmind.modules.training.schemas import (
    IssueCertificate,
    RevokeCertificate,
    TrainingCertificateCreate,
    TrainingCertificateFilters,
    TrainingCertificateListOut,
    TrainingCertificateOut,
    TrainingCertificateUpdate,
    VALID_CERTIFICATE_STATUSES,
)
from corpmind.modules.training.events import (
    CertificateCreated,
    CertificateIssued,
    CertificateRevoked,
)

_NOW = datetime(2026, 7, 5, 10, 0, 0, tzinfo=UTC)
_ORG = uuid.uuid4()
_WS = uuid.uuid4()
_SID = uuid.uuid4()   # session id
_AID = uuid.uuid4()   # attendance id
_CID = uuid.uuid4()   # certificate id


# ── Helpers ───────────────────────────────────────────────────────────────────

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


def _make_svc() -> tuple[TrainingCertificateService, MagicMock]:
    db_session = MagicMock()
    db_session.commit = AsyncMock()
    svc = TrainingCertificateService(db_session)
    svc._repo = MagicMock()
    svc._attendance_repo = MagicMock()
    return svc, db_session


def _make_attendance_obj(**kwargs) -> MagicMock:
    obj = MagicMock()
    obj.id = kwargs.get("id", _AID)
    obj.tenant_id = _ORG
    obj.workspace_id = _WS
    obj.session_id = kwargs.get("session_id", _SID)
    obj.participant_name = kwargs.get("participant_name", "Alice Smith")
    obj.participant_email = kwargs.get("participant_email", "alice@acme.com")
    obj.certificate_eligible = kwargs.get("certificate_eligible", True)
    return obj


def _make_cert_obj(**kwargs) -> MagicMock:
    obj = MagicMock()
    obj.id = kwargs.get("id", _CID)
    obj.tenant_id = _ORG
    obj.workspace_id = _WS
    obj.attendance_id = kwargs.get("attendance_id", _AID)
    obj.session_id = kwargs.get("session_id", _SID)
    obj.certificate_number = kwargs.get("certificate_number", None)
    obj.participant_name = kwargs.get("participant_name", "Alice Smith")
    obj.participant_email = kwargs.get("participant_email", "alice@acme.com")
    obj.certificate_title = kwargs.get("certificate_title", None)
    obj.issue_date = kwargs.get("issue_date", None)
    obj.issued_by = kwargs.get("issued_by", None)
    obj.status = kwargs.get("status", "draft")
    obj.download_count = kwargs.get("download_count", 0)
    obj.verification_code = kwargs.get("verification_code", "abc123")
    obj.notes = kwargs.get("notes", None)
    obj.created_at = kwargs.get("created_at", _NOW)
    obj.updated_at = kwargs.get("updated_at", _NOW)
    return obj


def _cert_out_json(**kwargs) -> str:
    obj = _make_cert_obj(**kwargs)
    return TrainingCertificateOut(
        id=obj.id,
        tenant_id=_ORG,
        workspace_id=_WS,
        attendance_id=obj.attendance_id,
        session_id=obj.session_id,
        certificate_number=obj.certificate_number,
        participant_name=obj.participant_name,
        participant_email=obj.participant_email,
        certificate_title=obj.certificate_title,
        issue_date=obj.issue_date,
        issued_by=obj.issued_by,
        status=obj.status,
        download_count=obj.download_count,
        verification_code=obj.verification_code,
        notes=obj.notes,
        created_at=obj.created_at,
        updated_at=obj.updated_at,
    ).model_dump_json()


# ── Cache key tests ───────────────────────────────────────────────────────────

class TestCacheKeys:
    def test_cert_list_key_format(self):
        key = _cert_list_key(_ORG, _SID)
        assert key == f"t:{_ORG}:training:certificates:list:{_SID}"

    def test_cert_detail_key_format(self):
        key = _cert_detail_key(_ORG, _CID)
        assert key == f"t:{_ORG}:training:certificates:detail:{_CID}"

    def test_list_key_different_orgs_differ(self):
        other = uuid.uuid4()
        assert _cert_list_key(_ORG, _SID) != _cert_list_key(other, _SID)

    def test_detail_key_different_certs_differ(self):
        other = uuid.uuid4()
        assert _cert_detail_key(_ORG, _CID) != _cert_detail_key(_ORG, other)

    def test_list_and_detail_keys_differ(self):
        assert _cert_list_key(_ORG, _SID) != _cert_detail_key(_ORG, _SID)


# ── Schema tests ──────────────────────────────────────────────────────────────

class TestCertificateSchemas:
    def test_valid_certificate_statuses_set(self):
        assert "draft" in VALID_CERTIFICATE_STATUSES
        assert "issued" in VALID_CERTIFICATE_STATUSES
        assert "revoked" in VALID_CERTIFICATE_STATUSES

    def test_valid_statuses_count(self):
        assert len(VALID_CERTIFICATE_STATUSES) == 3

    def test_certificate_create_requires_workspace(self):
        with pytest.raises(Exception):
            TrainingCertificateCreate(attendance_id=_AID, session_id=_SID)  # type: ignore[call-arg]

    def test_certificate_create_requires_attendance(self):
        with pytest.raises(Exception):
            TrainingCertificateCreate(workspace_id=_WS, session_id=_SID)  # type: ignore[call-arg]

    def test_certificate_create_requires_session(self):
        with pytest.raises(Exception):
            TrainingCertificateCreate(workspace_id=_WS, attendance_id=_AID)  # type: ignore[call-arg]

    def test_certificate_create_optional_fields_default_none(self):
        req = TrainingCertificateCreate(
            workspace_id=_WS, attendance_id=_AID, session_id=_SID
        )
        assert req.certificate_title is None
        assert req.notes is None

    def test_certificate_update_all_optional(self):
        req = TrainingCertificateUpdate()
        assert req.participant_name is None
        assert req.certificate_title is None
        assert req.certificate_number is None
        assert req.issued_by is None
        assert req.notes is None

    def test_issue_certificate_all_optional(self):
        req = IssueCertificate()
        assert req.issue_date is None
        assert req.issued_by is None
        assert req.certificate_number is None

    def test_revoke_certificate_all_optional(self):
        req = RevokeCertificate()
        assert req.notes is None

    def test_certificate_filters_requires_workspace(self):
        with pytest.raises(Exception):
            TrainingCertificateFilters()  # type: ignore[call-arg]

    def test_certificate_filters_defaults(self):
        f = TrainingCertificateFilters(workspace_id=_WS)
        assert f.session_id is None
        assert f.status is None
        assert f.limit == 50

    def test_certificate_out_model_config(self):
        obj = _make_cert_obj()
        out = TrainingCertificateOut.model_validate(obj)
        assert out.participant_name == "Alice Smith"

    def test_certificate_update_participant_name_validator_rejects_empty(self):
        with pytest.raises(Exception):
            TrainingCertificateUpdate(participant_name="")

    def test_certificate_out_dump_round_trip(self):
        obj = _make_cert_obj()
        out = TrainingCertificateOut.model_validate(obj)
        restored = TrainingCertificateOut.model_validate_json(out.model_dump_json())
        assert restored.id == out.id
        assert restored.status == out.status

    def test_certificate_create_with_optional_fields(self):
        req = TrainingCertificateCreate(
            workspace_id=_WS,
            attendance_id=_AID,
            session_id=_SID,
            certificate_title="Certificate of Completion",
            notes="Well done",
        )
        assert req.certificate_title == "Certificate of Completion"
        assert req.notes == "Well done"

    def test_issue_certificate_with_all_fields(self):
        req = IssueCertificate(
            issue_date=date(2026, 7, 5),
            issued_by="Trainer A",
            certificate_number="CERT-2026-001",
        )
        assert req.issued_by == "Trainer A"
        assert req.certificate_number == "CERT-2026-001"


# ── Event tests ───────────────────────────────────────────────────────────────

class TestCertificateEvents:
    def test_certificate_created_is_frozen(self):
        evt = CertificateCreated(
            certificate_id=_CID,
            attendance_id=_AID,
            session_id=_SID,
            tenant_id=_ORG,
            participant_name="Alice",
        )
        with pytest.raises((AttributeError, TypeError)):
            evt.certificate_id = uuid.uuid4()  # type: ignore[misc]

    def test_certificate_created_has_occurred_at(self):
        evt = CertificateCreated(
            certificate_id=_CID,
            attendance_id=_AID,
            session_id=_SID,
            tenant_id=_ORG,
            participant_name="Alice",
        )
        assert evt.occurred_at is not None

    def test_certificate_issued_fields(self):
        evt = CertificateIssued(
            certificate_id=_CID,
            attendance_id=_AID,
            session_id=_SID,
            tenant_id=_ORG,
            issued_by="Trainer A",
        )
        assert evt.issued_by == "Trainer A"

    def test_certificate_revoked_fields(self):
        evt = CertificateRevoked(
            certificate_id=_CID,
            attendance_id=_AID,
            session_id=_SID,
            tenant_id=_ORG,
        )
        assert str(evt.certificate_id) == str(_CID)

    def test_certificate_issued_none_issued_by(self):
        evt = CertificateIssued(
            certificate_id=_CID,
            attendance_id=_AID,
            session_id=_SID,
            tenant_id=_ORG,
            issued_by=None,
        )
        assert evt.issued_by is None


# ── create_certificate tests ──────────────────────────────────────────────────

class TestCreateCertificate:
    @pytest.mark.asyncio
    async def test_create_eligible_attendance(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        attendance = _make_attendance_obj(certificate_eligible=True)
        svc._attendance_repo.find_by_id = AsyncMock(return_value=attendance)
        svc._repo.create = AsyncMock()
        req = TrainingCertificateCreate(
            workspace_id=_WS, attendance_id=_AID, session_id=_SID
        )
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ):
            out = await svc.create_certificate(req)
        assert out.participant_name == attendance.participant_name

    @pytest.mark.asyncio
    async def test_create_non_eligible_raises_validation_error(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        attendance = _make_attendance_obj(certificate_eligible=False)
        svc._attendance_repo.find_by_id = AsyncMock(return_value=attendance)
        req = TrainingCertificateCreate(
            workspace_id=_WS, attendance_id=_AID, session_id=_SID
        )
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ), pytest.raises(ValidationError):
            await svc.create_certificate(req)

    @pytest.mark.asyncio
    async def test_create_unknown_attendance_raises_not_found(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._attendance_repo.find_by_id = AsyncMock(return_value=None)
        req = TrainingCertificateCreate(
            workspace_id=_WS, attendance_id=_AID, session_id=_SID
        )
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ), pytest.raises(NotFoundError):
            await svc.create_certificate(req)

    @pytest.mark.asyncio
    async def test_create_generates_verification_code(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        attendance = _make_attendance_obj(certificate_eligible=True)
        svc._attendance_repo.find_by_id = AsyncMock(return_value=attendance)
        svc._repo.create = AsyncMock()
        req = TrainingCertificateCreate(
            workspace_id=_WS, attendance_id=_AID, session_id=_SID
        )
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ):
            out = await svc.create_certificate(req)
        assert out.verification_code is not None
        assert len(out.verification_code) > 0

    @pytest.mark.asyncio
    async def test_create_status_is_draft(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        attendance = _make_attendance_obj(certificate_eligible=True)
        svc._attendance_repo.find_by_id = AsyncMock(return_value=attendance)
        svc._repo.create = AsyncMock()
        req = TrainingCertificateCreate(
            workspace_id=_WS, attendance_id=_AID, session_id=_SID
        )
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ):
            out = await svc.create_certificate(req)
        assert out.status == "draft"

    @pytest.mark.asyncio
    async def test_create_populates_participant_name_from_attendance(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        attendance = _make_attendance_obj(
            certificate_eligible=True, participant_name="Bob Jones"
        )
        svc._attendance_repo.find_by_id = AsyncMock(return_value=attendance)
        svc._repo.create = AsyncMock()
        req = TrainingCertificateCreate(
            workspace_id=_WS, attendance_id=_AID, session_id=_SID
        )
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ):
            out = await svc.create_certificate(req)
        assert out.participant_name == "Bob Jones"

    @pytest.mark.asyncio
    async def test_create_populates_participant_email_from_attendance(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        attendance = _make_attendance_obj(
            certificate_eligible=True, participant_email="bob@example.com"
        )
        svc._attendance_repo.find_by_id = AsyncMock(return_value=attendance)
        svc._repo.create = AsyncMock()
        req = TrainingCertificateCreate(
            workspace_id=_WS, attendance_id=_AID, session_id=_SID
        )
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ):
            out = await svc.create_certificate(req)
        assert out.participant_email == "bob@example.com"

    @pytest.mark.asyncio
    async def test_create_calls_commit(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        attendance = _make_attendance_obj(certificate_eligible=True)
        svc._attendance_repo.find_by_id = AsyncMock(return_value=attendance)
        svc._repo.create = AsyncMock()
        req = TrainingCertificateCreate(
            workspace_id=_WS, attendance_id=_AID, session_id=_SID
        )
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ):
            await svc.create_certificate(req)
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_busts_list_cache(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        attendance = _make_attendance_obj(certificate_eligible=True)
        svc._attendance_repo.find_by_id = AsyncMock(return_value=attendance)
        svc._repo.create = AsyncMock()
        req = TrainingCertificateCreate(
            workspace_id=_WS, attendance_id=_AID, session_id=_SID
        )
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ):
            await svc.create_certificate(req)
        redis.delete.assert_awaited()

    @pytest.mark.asyncio
    async def test_create_with_certificate_title(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        attendance = _make_attendance_obj(certificate_eligible=True)
        svc._attendance_repo.find_by_id = AsyncMock(return_value=attendance)
        svc._repo.create = AsyncMock()
        req = TrainingCertificateCreate(
            workspace_id=_WS,
            attendance_id=_AID,
            session_id=_SID,
            certificate_title="Certificate of Completion",
        )
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ):
            out = await svc.create_certificate(req)
        assert out.certificate_title == "Certificate of Completion"


# ── issue_certificate tests ───────────────────────────────────────────────────

class TestIssueCertificate:
    @pytest.mark.asyncio
    async def test_issue_draft_transitions_to_issued(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        cert = _make_cert_obj(status="draft")
        issued = _make_cert_obj(status="issued")
        svc._repo.find_by_id = AsyncMock(side_effect=[cert, issued])
        svc._repo.update_fields = AsyncMock()
        req = IssueCertificate()
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ):
            out = await svc.issue_certificate(_CID, req)
        assert out.status == "issued"

    @pytest.mark.asyncio
    async def test_issue_non_draft_raises_validation_error(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        cert = _make_cert_obj(status="issued")
        svc._repo.find_by_id = AsyncMock(return_value=cert)
        req = IssueCertificate()
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ), pytest.raises(ValidationError):
            await svc.issue_certificate(_CID, req)

    @pytest.mark.asyncio
    async def test_issue_revoked_raises_validation_error(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        cert = _make_cert_obj(status="revoked")
        svc._repo.find_by_id = AsyncMock(return_value=cert)
        req = IssueCertificate()
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ), pytest.raises(ValidationError):
            await svc.issue_certificate(_CID, req)

    @pytest.mark.asyncio
    async def test_issue_unknown_cert_raises_not_found(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_id = AsyncMock(return_value=None)
        req = IssueCertificate()
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ), pytest.raises(NotFoundError):
            await svc.issue_certificate(_CID, req)

    @pytest.mark.asyncio
    async def test_issue_sets_issue_date(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        cert = _make_cert_obj(status="draft")
        issued = _make_cert_obj(status="issued", issue_date=date(2026, 7, 5))
        svc._repo.find_by_id = AsyncMock(side_effect=[cert, issued])
        svc._repo.update_fields = AsyncMock()
        req = IssueCertificate(issue_date=date(2026, 7, 5))
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ):
            out = await svc.issue_certificate(_CID, req)
        assert out.issue_date == date(2026, 7, 5)

    @pytest.mark.asyncio
    async def test_issue_sets_issued_by(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        cert = _make_cert_obj(status="draft")
        issued = _make_cert_obj(status="issued", issued_by="Trainer A")
        svc._repo.find_by_id = AsyncMock(side_effect=[cert, issued])
        svc._repo.update_fields = AsyncMock()
        req = IssueCertificate(issued_by="Trainer A")
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ):
            out = await svc.issue_certificate(_CID, req)
        assert out.issued_by == "Trainer A"

    @pytest.mark.asyncio
    async def test_issue_sets_certificate_number(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        cert = _make_cert_obj(status="draft")
        issued = _make_cert_obj(status="issued", certificate_number="CERT-001")
        svc._repo.find_by_id = AsyncMock(side_effect=[cert, issued])
        svc._repo.update_fields = AsyncMock()
        req = IssueCertificate(certificate_number="CERT-001")
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ):
            out = await svc.issue_certificate(_CID, req)
        assert out.certificate_number == "CERT-001"

    @pytest.mark.asyncio
    async def test_issue_busts_caches(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        cert = _make_cert_obj(status="draft")
        issued = _make_cert_obj(status="issued")
        svc._repo.find_by_id = AsyncMock(side_effect=[cert, issued])
        svc._repo.update_fields = AsyncMock()
        req = IssueCertificate()
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ):
            await svc.issue_certificate(_CID, req)
        assert redis.delete.await_count >= 2

    @pytest.mark.asyncio
    async def test_issue_calls_commit(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        cert = _make_cert_obj(status="draft")
        issued = _make_cert_obj(status="issued")
        svc._repo.find_by_id = AsyncMock(side_effect=[cert, issued])
        svc._repo.update_fields = AsyncMock()
        req = IssueCertificate()
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ):
            await svc.issue_certificate(_CID, req)
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_issue_update_fields_called_with_status(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        cert = _make_cert_obj(status="draft")
        issued = _make_cert_obj(status="issued")
        svc._repo.find_by_id = AsyncMock(side_effect=[cert, issued])
        svc._repo.update_fields = AsyncMock()
        req = IssueCertificate()
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ):
            await svc.issue_certificate(_CID, req)
        call_kwargs = svc._repo.update_fields.call_args
        assert call_kwargs[1].get("status") == "issued" or "issued" in str(call_kwargs)


# ── revoke_certificate tests ──────────────────────────────────────────────────

class TestRevokeCertificate:
    @pytest.mark.asyncio
    async def test_revoke_draft_transitions_to_revoked(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        cert = _make_cert_obj(status="draft")
        revoked = _make_cert_obj(status="revoked")
        svc._repo.find_by_id = AsyncMock(side_effect=[cert, revoked])
        svc._repo.update_fields = AsyncMock()
        req = RevokeCertificate()
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ):
            out = await svc.revoke_certificate(_CID, req)
        assert out.status == "revoked"

    @pytest.mark.asyncio
    async def test_revoke_issued_transitions_to_revoked(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        cert = _make_cert_obj(status="issued")
        revoked = _make_cert_obj(status="revoked")
        svc._repo.find_by_id = AsyncMock(side_effect=[cert, revoked])
        svc._repo.update_fields = AsyncMock()
        req = RevokeCertificate()
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ):
            out = await svc.revoke_certificate(_CID, req)
        assert out.status == "revoked"

    @pytest.mark.asyncio
    async def test_revoke_already_revoked_raises_validation_error(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        cert = _make_cert_obj(status="revoked")
        svc._repo.find_by_id = AsyncMock(return_value=cert)
        req = RevokeCertificate()
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ), pytest.raises(ValidationError):
            await svc.revoke_certificate(_CID, req)

    @pytest.mark.asyncio
    async def test_revoke_unknown_cert_raises_not_found(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_id = AsyncMock(return_value=None)
        req = RevokeCertificate()
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ), pytest.raises(NotFoundError):
            await svc.revoke_certificate(_CID, req)

    @pytest.mark.asyncio
    async def test_revoke_sets_notes(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        cert = _make_cert_obj(status="issued")
        revoked = _make_cert_obj(status="revoked", notes="Fraudulent")
        svc._repo.find_by_id = AsyncMock(side_effect=[cert, revoked])
        svc._repo.update_fields = AsyncMock()
        req = RevokeCertificate(notes="Fraudulent")
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ):
            out = await svc.revoke_certificate(_CID, req)
        assert out.notes == "Fraudulent"

    @pytest.mark.asyncio
    async def test_revoke_busts_caches(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        cert = _make_cert_obj(status="draft")
        revoked = _make_cert_obj(status="revoked")
        svc._repo.find_by_id = AsyncMock(side_effect=[cert, revoked])
        svc._repo.update_fields = AsyncMock()
        req = RevokeCertificate()
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ):
            await svc.revoke_certificate(_CID, req)
        assert redis.delete.await_count >= 2

    @pytest.mark.asyncio
    async def test_revoke_calls_commit(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        cert = _make_cert_obj(status="draft")
        revoked = _make_cert_obj(status="revoked")
        svc._repo.find_by_id = AsyncMock(side_effect=[cert, revoked])
        svc._repo.update_fields = AsyncMock()
        req = RevokeCertificate()
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ):
            await svc.revoke_certificate(_CID, req)
        db.commit.assert_awaited_once()


# ── update_certificate tests ──────────────────────────────────────────────────

class TestUpdateCertificate:
    @pytest.mark.asyncio
    async def test_update_draft_succeeds(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        cert = _make_cert_obj(status="draft")
        updated = _make_cert_obj(status="draft", certificate_title="New Title")
        svc._repo.find_by_id = AsyncMock(side_effect=[cert, updated])
        svc._repo.update_fields = AsyncMock()
        req = TrainingCertificateUpdate(certificate_title="New Title")
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ):
            out = await svc.update_certificate(_CID, req)
        assert out.certificate_title == "New Title"

    @pytest.mark.asyncio
    async def test_update_non_draft_raises_validation_error(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        cert = _make_cert_obj(status="issued")
        svc._repo.find_by_id = AsyncMock(return_value=cert)
        req = TrainingCertificateUpdate(certificate_title="New Title")
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ), pytest.raises(ValidationError):
            await svc.update_certificate(_CID, req)

    @pytest.mark.asyncio
    async def test_update_unknown_cert_raises_not_found(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.find_by_id = AsyncMock(return_value=None)
        req = TrainingCertificateUpdate(certificate_title="New Title")
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ), pytest.raises(NotFoundError):
            await svc.update_certificate(_CID, req)

    @pytest.mark.asyncio
    async def test_update_calls_commit(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        cert = _make_cert_obj(status="draft")
        updated = _make_cert_obj(status="draft")
        svc._repo.find_by_id = AsyncMock(side_effect=[cert, updated])
        svc._repo.update_fields = AsyncMock()
        req = TrainingCertificateUpdate(notes="updated")
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ):
            await svc.update_certificate(_CID, req)
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_revoked_cert_raises_validation_error(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        cert = _make_cert_obj(status="revoked")
        svc._repo.find_by_id = AsyncMock(return_value=cert)
        req = TrainingCertificateUpdate(notes="try update")
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ), pytest.raises(ValidationError):
            await svc.update_certificate(_CID, req)

    @pytest.mark.asyncio
    async def test_update_busts_detail_cache(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        cert = _make_cert_obj(status="draft")
        updated = _make_cert_obj(status="draft")
        svc._repo.find_by_id = AsyncMock(side_effect=[cert, updated])
        svc._repo.update_fields = AsyncMock()
        req = TrainingCertificateUpdate(notes="note")
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ):
            await svc.update_certificate(_CID, req)
        redis.delete.assert_awaited()


# ── get_certificate tests ─────────────────────────────────────────────────────

class TestGetCertificate:
    @pytest.mark.asyncio
    async def test_get_cache_hit(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        cached_json = _cert_out_json()
        redis = _make_redis(cached=cached_json)
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ):
            out = await svc.get_certificate(_CID)
        svc._repo.find_by_id.assert_not_called()
        assert out.id == _CID

    @pytest.mark.asyncio
    async def test_get_cache_miss_hits_repo(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis(cached=None)
        cert = _make_cert_obj()
        svc._repo.find_by_id = AsyncMock(return_value=cert)
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ):
            out = await svc.get_certificate(_CID)
        svc._repo.find_by_id.assert_awaited_once()
        assert out.participant_name == "Alice Smith"

    @pytest.mark.asyncio
    async def test_get_not_found_raises_not_found_error(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis(cached=None)
        svc._repo.find_by_id = AsyncMock(return_value=None)
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ), pytest.raises(NotFoundError):
            await svc.get_certificate(_CID)

    @pytest.mark.asyncio
    async def test_get_cache_miss_sets_cache(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis(cached=None)
        cert = _make_cert_obj()
        svc._repo.find_by_id = AsyncMock(return_value=cert)
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ):
            await svc.get_certificate(_CID)
        redis.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_cache_error_falls_back_to_repo(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        redis.get = AsyncMock(side_effect=Exception("redis down"))
        cert = _make_cert_obj()
        svc._repo.find_by_id = AsyncMock(return_value=cert)
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ):
            out = await svc.get_certificate(_CID)
        assert out.participant_name == "Alice Smith"


# ── list_certificates tests ───────────────────────────────────────────────────

class TestListCertificates:
    @pytest.mark.asyncio
    async def test_session_only_cache_hit(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        list_json = TrainingCertificateListOut(
            items=[], next_cursor=None, has_more=False, total=0
        ).model_dump_json()
        redis = _make_redis(cached=list_json)
        filters = TrainingCertificateFilters(
            workspace_id=_WS, session_id=_SID
        )
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ):
            out = await svc.list_certificates(filters)
        svc._repo.count.assert_not_called()
        assert out.total == 0

    @pytest.mark.asyncio
    async def test_session_only_cache_miss_hits_repo(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis(cached=None)
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        filters = TrainingCertificateFilters(workspace_id=_WS, session_id=_SID)
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ):
            out = await svc.list_certificates(filters)
        svc._repo.count.assert_awaited_once()
        assert out.total == 0

    @pytest.mark.asyncio
    async def test_filters_skip_cache(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        filters = TrainingCertificateFilters(
            workspace_id=_WS, session_id=_SID, status="issued"
        )
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ):
            await svc.list_certificates(filters)
        redis.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_has_more_true_when_full_page(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis(cached=None)
        certs = [_make_cert_obj(id=uuid.uuid4()) for _ in range(50)]
        svc._repo.count = AsyncMock(return_value=60)
        svc._repo.list_page = AsyncMock(return_value=certs)
        filters = TrainingCertificateFilters(workspace_id=_WS, session_id=_SID)
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ):
            out = await svc.list_certificates(filters)
        assert out.has_more is True
        assert out.next_cursor is not None

    @pytest.mark.asyncio
    async def test_has_more_false_when_partial_page(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis(cached=None)
        certs = [_make_cert_obj(id=uuid.uuid4()) for _ in range(3)]
        svc._repo.count = AsyncMock(return_value=3)
        svc._repo.list_page = AsyncMock(return_value=certs)
        filters = TrainingCertificateFilters(workspace_id=_WS, session_id=_SID)
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ):
            out = await svc.list_certificates(filters)
        assert out.has_more is False
        assert out.next_cursor is None

    @pytest.mark.asyncio
    async def test_returns_correct_item_count(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis(cached=None)
        certs = [_make_cert_obj(id=uuid.uuid4()) for _ in range(5)]
        svc._repo.count = AsyncMock(return_value=5)
        svc._repo.list_page = AsyncMock(return_value=certs)
        filters = TrainingCertificateFilters(workspace_id=_WS, session_id=_SID)
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ):
            out = await svc.list_certificates(filters)
        assert len(out.items) == 5

    @pytest.mark.asyncio
    async def test_session_only_writes_to_cache(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis(cached=None)
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        filters = TrainingCertificateFilters(workspace_id=_WS, session_id=_SID)
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ):
            await svc.list_certificates(filters)
        redis.set.assert_awaited()

    @pytest.mark.asyncio
    async def test_list_with_no_session_skips_cache(self):
        svc, db = _make_svc()
        ctx = _make_ctx()
        redis = _make_redis()
        svc._repo.count = AsyncMock(return_value=0)
        svc._repo.list_page = AsyncMock(return_value=[])
        filters = TrainingCertificateFilters(workspace_id=_WS)
        with patch(
            "corpmind.modules.training.service.get_tenant_context", return_value=ctx
        ), patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ):
            await svc.list_certificates(filters)
        redis.get.assert_not_called()


# ── verify_certificate tests ──────────────────────────────────────────────────

class TestVerifyCertificate:
    @pytest.mark.asyncio
    async def test_verify_found(self):
        svc, db = _make_svc()
        cert = _make_cert_obj(verification_code="abc123def456")
        svc._repo.find_by_verification_code = AsyncMock(return_value=cert)
        out = await svc.verify_certificate("abc123def456")
        assert out.verification_code == "abc123def456"

    @pytest.mark.asyncio
    async def test_verify_not_found_raises_not_found(self):
        svc, db = _make_svc()
        svc._repo.find_by_verification_code = AsyncMock(return_value=None)
        with pytest.raises(NotFoundError):
            await svc.verify_certificate("bogus-code")

    @pytest.mark.asyncio
    async def test_verify_returns_correct_participant(self):
        svc, db = _make_svc()
        cert = _make_cert_obj(participant_name="Carol White", verification_code="xyz789")
        svc._repo.find_by_verification_code = AsyncMock(return_value=cert)
        out = await svc.verify_certificate("xyz789")
        assert out.participant_name == "Carol White"

    @pytest.mark.asyncio
    async def test_verify_passes_code_to_repo(self):
        svc, db = _make_svc()
        cert = _make_cert_obj()
        svc._repo.find_by_verification_code = AsyncMock(return_value=cert)
        await svc.verify_certificate("mycode")
        svc._repo.find_by_verification_code.assert_awaited_once_with("mycode")

    @pytest.mark.asyncio
    async def test_verify_empty_code_raises_not_found(self):
        svc, db = _make_svc()
        svc._repo.find_by_verification_code = AsyncMock(return_value=None)
        with pytest.raises(NotFoundError):
            await svc.verify_certificate("")


# ── Cache bust helper tests ───────────────────────────────────────────────────

class TestCacheBustHelpers:
    @pytest.mark.asyncio
    async def test_bust_cert_list_cache_calls_delete(self):
        svc, db = _make_svc()
        redis = _make_redis()
        with patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ):
            await svc._bust_cert_list_cache(_ORG, _SID)
        redis.delete.assert_awaited_once_with(_cert_list_key(_ORG, _SID))

    @pytest.mark.asyncio
    async def test_bust_cert_detail_cache_calls_delete(self):
        svc, db = _make_svc()
        redis = _make_redis()
        with patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ):
            await svc._bust_cert_detail_cache(_ORG, _CID)
        redis.delete.assert_awaited_once_with(_cert_detail_key(_ORG, _CID))

    @pytest.mark.asyncio
    async def test_bust_list_cache_redis_error_silenced(self):
        svc, db = _make_svc()
        redis = _make_redis()
        redis.delete = AsyncMock(side_effect=Exception("redis down"))
        with patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ):
            await svc._bust_cert_list_cache(_ORG, _SID)  # must not raise

    @pytest.mark.asyncio
    async def test_bust_detail_cache_redis_error_silenced(self):
        svc, db = _make_svc()
        redis = _make_redis()
        redis.delete = AsyncMock(side_effect=Exception("redis down"))
        with patch(
            "corpmind.modules.training.service.get_redis", return_value=redis
        ):
            await svc._bust_cert_detail_cache(_ORG, _CID)  # must not raise
