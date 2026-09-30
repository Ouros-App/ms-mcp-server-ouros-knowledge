from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.mcp_server import create_custom_dashboard
from app.services.dashboards import DashboardServiceError


def context_with_token(token: str | None):
    authorization = f"Bearer {token}" if token else None
    headers = {"x-ouros-telemetry-token": authorization} if authorization else {}
    return SimpleNamespace(
        request_context=SimpleNamespace(
            request=SimpleNamespace(headers=headers),
        )
    )


@pytest.mark.anyio
async def test_custom_dashboard_tool_verifies_and_forwards_scoped_request():
    result = {"title": "Metas", "charts": [{"id": "goal-status"}]}
    charts = [SimpleNamespace(model_dump=lambda: {"chart_id": "goal-status", "render_as": "pie"})]
    with (
        patch("app.mcp_server.get_authenticated_identity", return_value=("farm_owner", 42)),
        patch("app.mcp_server.verify_telemetry_access_token", new=AsyncMock()) as verify,
        patch("app.mcp_server.render_custom_dashboard", new=AsyncMock(return_value=result)) as render,
    ):
        response = await create_custom_dashboard(
            "Metas",
            charts,
            context_with_token("delegated-jwt"),
            period_days=14,
        )

    assert response == result
    verify.assert_awaited_once_with("delegated-jwt")
    render.assert_awaited_once_with(
        "Metas",
        [{"chart_id": "goal-status", "render_as": "pie"}],
        14,
        "delegated-jwt",
    )


@pytest.mark.anyio
async def test_custom_dashboard_tool_requires_a_delegated_bearer_token():
    with (
        patch("app.mcp_server.get_authenticated_identity", return_value=("farm_owner", 42)),
        patch("app.mcp_server.verify_telemetry_access_token", new=AsyncMock()) as verify,
        pytest.raises(PermissionError, match="token delegado"),
    ):
        await create_custom_dashboard(
            "Metas",
            [],
            context_with_token(None),
        )

    verify.assert_not_awaited()


@pytest.mark.anyio
async def test_custom_dashboard_tool_propagates_auth_and_api_errors():
    with (
        patch("app.mcp_server.get_authenticated_identity", return_value=("farm_owner", 42)),
        patch(
            "app.mcp_server.verify_telemetry_access_token",
            new=AsyncMock(side_effect=PermissionError("invalid delegated token")),
        ),
        pytest.raises(PermissionError, match="invalid delegated token"),
    ):
        await create_custom_dashboard("Metas", [], context_with_token("bad-jwt"))

    with (
        patch("app.mcp_server.get_authenticated_identity", return_value=("farm_owner", 42)),
        patch("app.mcp_server.verify_telemetry_access_token", new=AsyncMock()),
        patch(
            "app.mcp_server.render_custom_dashboard",
            new=AsyncMock(side_effect=DashboardServiceError("upstream unavailable")),
        ),
        pytest.raises(DashboardServiceError, match="upstream unavailable"),
    ):
        await create_custom_dashboard("Metas", [], context_with_token("good-jwt"))
