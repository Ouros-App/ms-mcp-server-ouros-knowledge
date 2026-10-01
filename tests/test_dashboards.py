from unittest.mock import patch

import httpx
import pytest

from app.core.config import settings
from app.services.dashboards import (
    DashboardServiceError,
    _decode_response,
    _validate_chart_selections,
    create_custom_dashboard,
    list_custom_dashboard_catalog,
)

VALID_CHART = {"chart_id": "goal-status", "render_as": "pie"}
VALID_PAYLOAD = {
    "title": "Metas",
    "charts": [
        {
            "id": "goal-status",
            "title": "Status das metas",
            "render_as": "pie",
            "html": "<html></html>",
        }
    ],
}


@pytest.mark.parametrize(
    "charts",
    [
        [],
        [{"chart_id": "INVALID_chart!", "render_as": "auto"}],
        [VALID_CHART, VALID_CHART],
        [{"chart_id": "goal-status", "render_as": ""}],
    ],
)
def test_chart_selection_rejects_invalid_values(charts):
    with pytest.raises(ValueError):
        _validate_chart_selections(charts)


def test_chart_selection_accepts_plotly_types_delegated_to_telemetry():
    _validate_chart_selections(
        [
            {"chart_id": "goal-status", "render_as": "pie"},
            {"chart_id": "monthly-consumption", "render_as": "histogram"},
            {"chart_id": "lot-throughput", "render_as": "scatter3d"},
            {"chart_id": "resource-efficiency", "render_as": "treemap"},
        ]
    )
    _validate_chart_selections(
        [{"chart_id": "monthly-consumption", "render_as": "surface"}]
    )
    _validate_chart_selections(
        [{"chart_id": "monthly-consumption", "render_as": "future-plotly-trace"}]
    )


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (401, None),
        (403, None),
        (404, None),
        (400, None),
        (503, None),
        (418, None),
        (200, "not-json"),
        (200, {"title": "Metas"}),
        (200, {"charts": []}),
        (200, {"charts": [{"id": "a"}]}),
    ],
)
def test_decode_response_rejects_api_errors_and_malformed_payloads(status, body):
    response = (
        httpx.Response(status, json=body)
        if isinstance(body, dict)
        else httpx.Response(
            status,
            text=body if isinstance(body, str) else "",
        )
    )
    with pytest.raises(DashboardServiceError):
        _decode_response(response)


def test_decode_response_rejects_oversized_html():
    payload = {"charts": [{**VALID_PAYLOAD["charts"][0], "html": "x" * 1_500_001}]}
    with pytest.raises(DashboardServiceError, match="gráfico inválido"):
        _decode_response(httpx.Response(200, json=payload))


def test_decode_response_rejects_oversized_combined_dashboard():
    chart = {**VALID_PAYLOAD["charts"][0], "html": "x" * 600_000}
    payload = {"charts": [chart, chart, chart, chart]}
    with pytest.raises(DashboardServiceError, match="limite de tamanho"):
        _decode_response(httpx.Response(200, json=payload))


def test_decode_response_accepts_valid_dashboard():
    assert _decode_response(httpx.Response(200, json=VALID_PAYLOAD)) == VALID_PAYLOAD


@pytest.mark.anyio
async def test_create_custom_dashboard_posts_delegated_request():
    captured = {}
    real_client = httpx.AsyncClient

    def handler(request):
        captured["authorization"] = request.headers["authorization"]
        captured["payload"] = request.read()
        return httpx.Response(200, json=VALID_PAYLOAD)

    transport = httpx.MockTransport(handler)
    with (
        patch.object(
            settings, "TELEMETRY_DASHBOARD_API_URL", "https://telemetry.test/"
        ),
        patch(
            "app.services.dashboards.httpx.AsyncClient",
            side_effect=lambda **kwargs: real_client(transport=transport, **kwargs),
        ),
    ):
        result = await create_custom_dashboard(" Metas ", [VALID_CHART], 30, "jwt")

    assert result == VALID_PAYLOAD
    assert captured["authorization"] == "Bearer jwt"
    assert b'"title":"Metas"' in captured["payload"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("title", "charts", "period_days", "token", "base_url", "message"),
    [
        (" ", [VALID_CHART], 30, "jwt", "https://telemetry.test", "title"),
        ("Metas", [], 30, "jwt", "https://telemetry.test", "charts"),
        ("Metas", [VALID_CHART], 30, "", "https://telemetry.test", "Token"),
        ("Metas", [VALID_CHART], 30, "jwt", " ", "configurada"),
    ],
)
async def test_create_custom_dashboard_rejects_invalid_request_before_http(
    title,
    charts,
    period_days,
    token,
    base_url,
    message,
):
    with (
        patch.object(settings, "TELEMETRY_DASHBOARD_API_URL", base_url),
        pytest.raises((ValueError, DashboardServiceError), match=message),
    ):
        await create_custom_dashboard(title, charts, period_days, token)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "failure", [httpx.ReadTimeout("slow"), httpx.ConnectError("offline")]
)
async def test_create_custom_dashboard_maps_http_failures(failure):
    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda _request: (_ for _ in ()).throw(failure))
    with (
        patch.object(settings, "TELEMETRY_DASHBOARD_API_URL", "https://telemetry.test"),
        patch(
            "app.services.dashboards.httpx.AsyncClient",
            side_effect=lambda **kwargs: real_client(transport=transport, **kwargs),
        ),
        pytest.raises(DashboardServiceError),
    ):
        await create_custom_dashboard("Metas", [VALID_CHART], 30, "jwt")


@pytest.mark.anyio
async def test_create_custom_dashboard_rejects_mismatched_response():
    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(200, json={**VALID_PAYLOAD, "title": "Outro"})
    )
    with (
        patch.object(settings, "TELEMETRY_DASHBOARD_API_URL", "https://telemetry.test"),
        patch(
            "app.services.dashboards.httpx.AsyncClient",
            side_effect=lambda **kwargs: real_client(transport=transport, **kwargs),
        ),
        pytest.raises(DashboardServiceError, match="outro painel"),
    ):
        await create_custom_dashboard("Metas", [VALID_CHART], 30, "jwt")


def _catalog_client(handler):
    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    return lambda **kwargs: real_client(transport=transport, **kwargs)


@pytest.mark.anyio
async def test_catalog_returns_flattened_user_scoped_charts():
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.path == "/v1/user/dashboards":
            return httpx.Response(200, json={"items": [{"id": "water", "title": "Água"}]})
        return httpx.Response(
            200,
            json={"items": [{
                "id": "daily-water",
                "title": "Consumo diário",
                "default_render_as": "scatter",
                "render_options": ["scatter", "bar", "histogram"],
            }]},
        )

    with (
        patch.object(settings, "TELEMETRY_DASHBOARD_API_URL", "https://telemetry.test/"),
        patch("app.services.dashboards.httpx.AsyncClient", side_effect=_catalog_client(handler)),
    ):
        result = await list_custom_dashboard_catalog("jwt")

    assert result == {"charts": [{
        "chart_id": "daily-water",
        "title": "Consumo diário",
        "dashboard": "Água",
        "default_render_as": "scatter",
        "render_options": ["scatter", "bar", "histogram"],
    }]}
    assert len(calls) == 2
    assert all(call.headers["authorization"] == "Bearer jwt" for call in calls)


@pytest.mark.anyio
async def test_catalog_accepts_empty_dashboard_list():
    with (
        patch.object(settings, "TELEMETRY_DASHBOARD_API_URL", "https://telemetry.test"),
        patch(
            "app.services.dashboards.httpx.AsyncClient",
            side_effect=_catalog_client(lambda _request: httpx.Response(200, json={"items": []})),
        ),
    ):
        assert await list_custom_dashboard_catalog("jwt") == {"charts": []}


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status", "message"),
    [(401, "identidade"), (403, "identidade"), (503, "temporariamente indisponível"), (422, "rejeitou")],
)
async def test_catalog_maps_dashboard_list_http_errors(status, message):
    with (
        patch.object(settings, "TELEMETRY_DASHBOARD_API_URL", "https://telemetry.test"),
        patch(
            "app.services.dashboards.httpx.AsyncClient",
            side_effect=_catalog_client(lambda _request: httpx.Response(status)),
        ),
        pytest.raises(DashboardServiceError, match=message),
    ):
        await list_custom_dashboard_catalog("jwt")


@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload",
    [
        [], {"items": "bad"}, {"items": [None]},
        {"items": [{"id": "INVALID!", "title": "Água"}]},
        {"items": [{"id": "water", "title": " "}]},
        {"items": [{"id": "water", "title": "Água"}] * 33},
    ],
)
async def test_catalog_rejects_invalid_dashboard_payloads(payload):
    with (
        patch.object(settings, "TELEMETRY_DASHBOARD_API_URL", "https://telemetry.test"),
        patch(
            "app.services.dashboards.httpx.AsyncClient",
            side_effect=_catalog_client(lambda _request: httpx.Response(200, json=payload)),
        ),
        pytest.raises(DashboardServiceError),
    ):
        await list_custom_dashboard_catalog("jwt")


@pytest.mark.anyio
@pytest.mark.parametrize(
    "charts",
    [
        "bad", [None],
        [{"id": "INVALID!", "title": "Consumo", "default_render_as": "bar", "render_options": ["bar"]}],
        [{"id": "water", "title": " ", "default_render_as": "bar", "render_options": ["bar"]}],
        [{"id": "water", "title": "Consumo", "default_render_as": "bar", "render_options": []}],
        [{"id": "water", "title": "Consumo", "default_render_as": "bar", "render_options": [None]}],
        [{"id": "water", "title": "Consumo", "default_render_as": "bar", "render_options": ["bar"]}] * 65,
    ],
)
async def test_catalog_rejects_invalid_chart_payloads(charts):
    responses = iter([
        httpx.Response(200, json={"items": [{"id": "water", "title": "Água"}]}),
        httpx.Response(200, json={"items": charts}),
    ])
    with (
        patch.object(settings, "TELEMETRY_DASHBOARD_API_URL", "https://telemetry.test"),
        patch(
            "app.services.dashboards.httpx.AsyncClient",
            side_effect=_catalog_client(lambda _request: next(responses)),
        ),
        pytest.raises(DashboardServiceError),
    ):
        await list_custom_dashboard_catalog("jwt")


@pytest.mark.anyio
async def test_catalog_maps_chart_endpoint_http_error():
    responses = iter([
        httpx.Response(200, json={"items": [{"id": "water", "title": "Água"}]}),
        httpx.Response(403),
    ])
    with (
        patch.object(settings, "TELEMETRY_DASHBOARD_API_URL", "https://telemetry.test"),
        patch(
            "app.services.dashboards.httpx.AsyncClient",
            side_effect=_catalog_client(lambda _request: next(responses)),
        ),
        pytest.raises(DashboardServiceError, match="identidade"),
    ):
        await list_custom_dashboard_catalog("jwt")


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("token", "base_url", "message"),
    [("", "https://telemetry.test", "Token"), ("jwt", " ", "configurada")],
)
async def test_catalog_requires_token_and_configuration(token, base_url, message):
    with (
        patch.object(settings, "TELEMETRY_DASHBOARD_API_URL", base_url),
        pytest.raises(DashboardServiceError, match=message),
    ):
        await list_custom_dashboard_catalog(token)


@pytest.mark.anyio
@pytest.mark.parametrize("failure", [httpx.ReadTimeout("slow"), httpx.ConnectError("offline")])
async def test_catalog_maps_http_transport_failures(failure):
    with (
        patch.object(settings, "TELEMETRY_DASHBOARD_API_URL", "https://telemetry.test"),
        patch(
            "app.services.dashboards.httpx.AsyncClient",
            side_effect=_catalog_client(lambda _request: (_ for _ in ()).throw(failure)),
        ),
        pytest.raises(DashboardServiceError),
    ):
        await list_custom_dashboard_catalog("jwt")


@pytest.mark.anyio
async def test_catalog_maps_invalid_json():
    with (
        patch.object(settings, "TELEMETRY_DASHBOARD_API_URL", "https://telemetry.test"),
        patch(
            "app.services.dashboards.httpx.AsyncClient",
            side_effect=_catalog_client(lambda _request: httpx.Response(200, text="not-json")),
        ),
        pytest.raises(DashboardServiceError, match="dados inválidos"),
    ):
        await list_custom_dashboard_catalog("jwt")
