import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

MAX_CUSTOM_DASHBOARD_CHARTS = 4
MAX_CHART_HTML_CHARS = 1_500_000
_ALLOWED_CHART_IDS = frozenset(
    {
        "current-flock",
        "capacity-utilization",
        "mortality-rate",
        "farm-capacity",
        "lot-throughput",
        "lot-mortality",
        "lot-cost",
        "monthly-consumption",
        "resource-efficiency",
        "goal-status",
        "goal-type",
    }
)
_ALLOWED_RENDER_TYPES = frozenset(
    {"auto", "indicator", "bar", "line", "pie", "donut", "histogram"}
)


class DashboardServiceError(RuntimeError):
    """The dashboard API could not return a usable custom dashboard."""


def _validate_chart_selections(charts: list[dict[str, str]]) -> None:
    if not 1 <= len(charts) <= MAX_CUSTOM_DASHBOARD_CHARTS:
        raise ValueError(
            f"charts deve conter de 1 a {MAX_CUSTOM_DASHBOARD_CHARTS} itens"
        )
    chart_ids = [chart.get("chart_id") for chart in charts]
    if len(chart_ids) != len(set(chart_ids)):
        raise ValueError("charts não pode conter chart_ids duplicados")
    unsupported = [
        chart_id for chart_id in chart_ids if chart_id not in _ALLOWED_CHART_IDS
    ]
    if unsupported:
        raise ValueError("charts contém gráficos não suportados")
    if any(chart.get("render_as") not in _ALLOWED_RENDER_TYPES for chart in charts):
        raise ValueError("charts contém um tipo de visualização não suportado")


def _decode_response(response: httpx.Response) -> dict[str, Any]:
    if response.status_code in (401, 403):
        raise DashboardServiceError("A identidade não tem acesso aos dashboards")
    if response.status_code == 404:
        raise DashboardServiceError("Um dos gráficos solicitados não existe")
    if response.status_code == 400:
        raise DashboardServiceError("A visualização solicitada não é compatível")
    if response.status_code >= 500:
        raise DashboardServiceError("Os dashboards estão temporariamente indisponíveis")
    if response.status_code != 200:
        raise DashboardServiceError("A API de dashboards rejeitou a solicitação")

    try:
        payload = response.json()
    except ValueError as exc:
        raise DashboardServiceError(
            "A API de dashboards retornou dados inválidos"
        ) from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("charts"), list):
        raise DashboardServiceError("A API de dashboards retornou dados inválidos")
    charts = payload["charts"]
    if not 1 <= len(charts) <= MAX_CUSTOM_DASHBOARD_CHARTS:
        raise DashboardServiceError("A API de dashboards retornou uma lista inválida")
    html_chars = 0
    for chart in charts:
        if (
            not isinstance(chart, dict)
            or not isinstance(chart.get("id"), str)
            or not isinstance(chart.get("title"), str)
            or not isinstance(chart.get("render_as"), str)
            or not isinstance(chart.get("html"), str)
            or len(chart["html"]) > MAX_CHART_HTML_CHARS
        ):
            raise DashboardServiceError(
                "A API de dashboards retornou um gráfico inválido"
            )
        html_chars += len(chart["html"])
    if html_chars > 2_000_000:
        raise DashboardServiceError("O painel retornado excede o limite de tamanho")
    return payload


async def create_custom_dashboard(
    title: str,
    charts: list[dict[str, str]],
    period_days: int,
    telemetry_token: str,
) -> dict[str, Any]:
    """Render an ephemeral dashboard through the user-scoped Telemetry API."""
    _validate_chart_selections(charts)
    if not title.strip() or len(title) > 120:
        raise ValueError("title deve conter de 1 a 120 caracteres")
    if not telemetry_token or len(telemetry_token) > 16_384:
        raise DashboardServiceError("Token delegado do Telemetry indisponível")
    base_url = settings.TELEMETRY_DASHBOARD_API_URL
    if not base_url or not base_url.strip():
        raise DashboardServiceError("API de dashboards não está configurada")

    payload = {
        "title": title.strip(),
        "period_days": period_days,
        "charts": charts,
    }
    timeout = httpx.Timeout(settings.TELEMETRY_DASHBOARD_API_TIMEOUT_SECONDS)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{base_url.rstrip('/')}/v1/user/dashboards/custom",
                json=payload,
                headers={"Authorization": f"Bearer {telemetry_token}"},
            )
    except httpx.TimeoutException as exc:
        logger.warning("custom_dashboard_failed reason=timeout")
        raise DashboardServiceError(
            "A API de dashboards demorou para responder"
        ) from exc
    except httpx.HTTPError as exc:
        logger.warning(
            "custom_dashboard_failed reason=http_error error=%s",
            type(exc).__name__,
        )
        raise DashboardServiceError(
            "A API de dashboards está temporariamente indisponível"
        ) from exc

    logger.info(
        "custom_dashboard_response status=%d requested_charts=%d",
        response.status_code,
        len(charts),
    )
    result = _decode_response(response)
    if (
        result.get("title") != title.strip()
        or [chart.get("id") for chart in result["charts"]]
        != [chart.get("chart_id") for chart in charts]
    ):
        raise DashboardServiceError("A API de dashboards retornou outro painel")
    return result
