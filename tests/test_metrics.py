import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient
from jwt import InvalidTokenError

from app.api.routes import metrics, require_metrics_bearer
from app.core.metrics import DEPENDENCY_READY, instrument_tool, metric_path
from app.main import app
from app.services import auth


def test_tool_instrumentation_preserves_function_contract() -> None:
    @instrument_tool("example")
    def add(left: int, right: int = 1) -> int:
        return left + right

    assert add(2, right=3) == 5
    assert add.__name__ == "add"


def test_tool_instrumentation_awaits_async_tools() -> None:
    @instrument_tool("async-example")
    async def async_add(left: int, right: int = 1) -> int:
        return left + right

    assert asyncio.run(async_add(2, right=3)) == 5
    assert async_add.__name__ == "async_add"


def test_metrics_token_accepts_prometheus_authorized_party(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        auth,
        "_decode_metrics_token",
        lambda _token: {"azp": "ouros-prometheus"},
    )

    claims = asyncio.run(auth.verify_metrics_token("signed-token"))

    assert claims == {"azp": "ouros-prometheus"}


def test_dependency_gauge_is_available() -> None:
    DEPENDENCY_READY.labels("qdrant").set(1)


def test_tool_instrumentation_records_error_without_swallowing_it() -> None:
    @instrument_tool("broken")
    def broken() -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        broken()


def test_metric_path_bounds_unknown_routes() -> None:
    assert metric_path("/mcp/sessions/anything") == "/mcp"
    assert metric_path("/health/") == "/health"
    assert metric_path("/random/untrusted/value") == "{unknown}"
    assert metric_path("/mcp-admin") == "{unknown}"


def test_decode_metrics_token_enforces_service_account() -> None:
    signing_key = SimpleNamespace(key="public-key")
    with (
        patch("app.services.auth._get_signing_key", return_value=signing_key),
        patch(
            "app.services.auth.decode",
            return_value={"azp": "ouros-prometheus"},
        ),
    ):
        assert auth._decode_metrics_token("signed-token") == {
            "azp": "ouros-prometheus"
        }

    with (
        patch("app.services.auth._get_signing_key", return_value=signing_key),
        patch(
            "app.services.auth.decode",
            return_value={"azp": "other-client"},
        ),
    ):
        assert auth._decode_metrics_token("signed-token") is None

    with (
        patch("app.services.auth._get_signing_key", return_value=signing_key),
        patch(
            "app.services.auth.decode",
            side_effect=InvalidTokenError("invalid"),
        ),
    ):
        assert auth._decode_metrics_token("signed-token") is None


def test_metrics_auth_dependency_covers_rejection_and_success() -> None:
    with pytest.raises(HTTPException) as missing:
        asyncio.run(require_metrics_bearer(None))
    assert missing.value.status_code == 401

    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials="signed-token",
    )
    with (
        patch(
            "app.api.routes.verify_metrics_token",
            AsyncMock(return_value=None),
        ),
        pytest.raises(HTTPException) as rejected,
    ):
        asyncio.run(require_metrics_bearer(credentials))
    assert rejected.value.status_code == 401

    with patch(
        "app.api.routes.verify_metrics_token",
        AsyncMock(return_value={"azp": "ouros-prometheus"}),
    ):
        claims = asyncio.run(require_metrics_bearer(credentials))
    assert claims["azp"] == "ouros-prometheus"


def test_metrics_auth_dependency_maps_jwks_failure_to_503() -> None:
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials="signed-token",
    )
    with (
        patch(
            "app.api.routes.verify_metrics_token",
            AsyncMock(
                side_effect=auth.AuthenticationKeyServiceError("jwks unavailable")
            ),
        ),
        pytest.raises(HTTPException) as unavailable,
    ):
        asyncio.run(require_metrics_bearer(credentials))

    assert unavailable.value.status_code == 503


def test_metrics_endpoint_returns_prometheus_payload() -> None:
    response = asyncio.run(metrics({"azp": "ouros-prometheus"}))

    assert response.status_code == 200
    assert b"mcp_server_http_requests_total" in response.body



def test_metrics_endpoint_rejects_anonymous_and_ordinary_mcp_token() -> None:
    signing_key = SimpleNamespace(key="public-key")

    client = TestClient(app)
    try:
        anonymous = client.get("/metrics")
        assert anonymous.status_code == 401

        with (
            patch(
                "app.services.auth._get_signing_key",
                return_value=signing_key,
            ),
            patch(
                "app.services.auth.decode",
                return_value={"azp": "ms-ai-server-mcp-exchange"},
            ),
        ):
            ordinary = client.get(
                "/metrics",
                headers={"Authorization": "Bearer signed-token"},
            )
    finally:
        client.close()

    assert ordinary.status_code == 401
