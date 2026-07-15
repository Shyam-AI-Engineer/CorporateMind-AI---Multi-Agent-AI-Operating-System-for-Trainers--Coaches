"""Unit tests for the /metrics endpoint bearer-token gate.

Tests _metrics_auth directly without spinning up a full ASGI app.

Covers:
  - When METRICS_TOKEN is empty, endpoint is open (no auth required)
  - When METRICS_TOKEN is set, valid Bearer token passes
  - When METRICS_TOKEN is set, missing Authorization header returns 401
  - When METRICS_TOKEN is set, wrong token returns 401
  - When METRICS_TOKEN is set, malformed header (no 'Bearer ' prefix) returns 401
  - 401 response includes WWW-Authenticate: Bearer header
  - 401 response body has 'code' and 'message' fields
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse


from corpmind.core.tenancy import _metrics_auth


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_request(auth_header: str | None = None) -> Request:
    req = MagicMock(spec=Request)
    if auth_header is not None:
        req.headers = {"Authorization": auth_header}
    else:
        req.headers = {}
    req.url = MagicMock()
    req.url.path = "/metrics"
    return req


async def _passthrough_call_next(_request: Request) -> JSONResponse:
    """Simulates the next middleware layer returning a 200."""
    return JSONResponse(content={"ok": True}, status_code=200)


# ── No token configured (dev / staging) ───────────────────────────────────────

class TestMetricsAuthNoToken:
    @pytest.mark.asyncio
    async def test_endpoint_open_when_token_not_configured(self) -> None:
        """When METRICS_TOKEN is empty, any request passes through."""
        mock_settings = MagicMock()
        mock_settings.METRICS_TOKEN = ""

        with patch("corpmind.core.config.settings", mock_settings):
            response = await _metrics_auth(_make_request(), _passthrough_call_next)

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_endpoint_open_without_auth_header_when_no_token(self) -> None:
        """No Authorization header + no METRICS_TOKEN = passes."""
        mock_settings = MagicMock()
        mock_settings.METRICS_TOKEN = ""

        with patch("corpmind.core.config.settings", mock_settings):
            response = await _metrics_auth(_make_request(auth_header=None), _passthrough_call_next)

        assert response.status_code == 200


# ── Token configured ───────────────────────────────────────────────────────────

class TestMetricsAuthWithToken:
    _TOKEN = "super-secret-prometheus-token"

    def _settings(self, token: str = _TOKEN) -> MagicMock:
        mock = MagicMock()
        mock.METRICS_TOKEN = token
        return mock

    @pytest.mark.asyncio
    async def test_valid_bearer_token_passes(self) -> None:
        with patch("corpmind.core.config.settings", self._settings()):
            response = await _metrics_auth(
                _make_request(auth_header=f"Bearer {self._TOKEN}"),
                _passthrough_call_next,
            )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_missing_auth_header_returns_401(self) -> None:
        with patch("corpmind.core.config.settings", self._settings()):
            response = await _metrics_auth(
                _make_request(auth_header=None),
                _passthrough_call_next,
            )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_token_returns_401(self) -> None:
        with patch("corpmind.core.config.settings", self._settings()):
            response = await _metrics_auth(
                _make_request(auth_header="Bearer wrong-token"),
                _passthrough_call_next,
            )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_malformed_header_no_bearer_prefix_returns_401(self) -> None:
        """Prometheus requires 'Bearer <token>' — plain token without prefix rejected."""
        with patch("corpmind.core.config.settings", self._settings()):
            response = await _metrics_auth(
                _make_request(auth_header=self._TOKEN),  # missing "Bearer " prefix
                _passthrough_call_next,
            )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_401_includes_www_authenticate_header(self) -> None:
        """WWW-Authenticate: Bearer is required for RFC 6750 compliance."""
        with patch("corpmind.core.config.settings", self._settings()):
            response = await _metrics_auth(
                _make_request(auth_header=None),
                _passthrough_call_next,
            )
        assert response.status_code == 401
        assert "WWW-Authenticate" in response.headers
        assert response.headers["WWW-Authenticate"] == "Bearer"

    @pytest.mark.asyncio
    async def test_401_body_has_code_and_message(self) -> None:
        """API consumers expect the standard {code, message} error envelope."""
        import json

        with patch("corpmind.core.config.settings", self._settings()):
            response = await _metrics_auth(
                _make_request(auth_header="Bearer bad"),
                _passthrough_call_next,
            )

        body = json.loads(bytes(response.body))
        assert "code" in body
        assert "message" in body
        assert body["code"] == "unauthenticated"

    @pytest.mark.asyncio
    async def test_case_sensitive_token_comparison(self) -> None:
        """Token comparison must be exact — no case-folding."""
        with patch("corpmind.core.config.settings", self._settings()):
            response = await _metrics_auth(
                _make_request(auth_header=f"Bearer {self._TOKEN.upper()}"),
                _passthrough_call_next,
            )
        assert response.status_code == 401
