import logging
from time import perf_counter
from typing import Annotated, Any, Literal

from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import Context, FastMCP
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.identity import FARM_OWNER_USER_TYPE
from app.core.metrics import DEPENDENCY_READY, instrument_tool
from app.services.auth import (
    KeycloakTokenVerifier,
    get_authenticated_identity,
    verify_telemetry_access_token,
)
from app.services.dashboards import DashboardServiceError
from app.services.dashboards import create_custom_dashboard as render_custom_dashboard
from app.services.database import (
    DEFAULT_CONSUMPTION_PERIOD_DAYS,
    MAX_CONSUMPTION_PERIOD_DAYS,
)
from app.services.database import (
    get_consumption_summary as get_database_consumption_summary,
)
from app.services.database import (
    get_user_context as get_database_user_context,
)
from app.services.database import (
    import_resource_records as get_database_import_resource_records,
)
from app.services.database import (
    postgres_status as get_postgres_status,
)
from app.services.imports import extract_resource_records, file_to_markdown
from app.services.knowledge import qdrant_status as get_qdrant_status
from app.services.knowledge import search_knowledge as search_qdrant

logger = logging.getLogger(__name__)


class CustomDashboardChartSelection(BaseModel):
    """One approved chart and its requested visual form."""

    chart_id: str = Field(min_length=1, max_length=64)
    render_as: Literal[
        "auto",
        "indicator",
        "bar",
        "line",
        "pie",
        "donut",
        "histogram",
    ] = "auto"

mcp = FastMCP(
    name=settings.PROJECT_NAME,
    host="0.0.0.0",
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
    auth=AuthSettings(
        issuer_url=settings.MCP_JWT_ISSUER,
        resource_server_url=settings.MCP_RESOURCE_URL,
    ),
    token_verifier=KeycloakTokenVerifier(),
)


@mcp.tool()
@instrument_tool("search_knowledge")
def search_knowledge(
    query: str,
    limit: Annotated[
        int,
        Field(
            ge=1,
            le=settings.SEARCH_MAX_K,
            description="Quantidade maxima de trechos retornados.",
        ),
    ] = settings.SEARCH_TOP_K,
) -> list[dict[str, Any]]:
    """Search Qdrant using NVIDIA embeddings.

    Args:
        query: Natural-language question or search phrase.
        limit: Number of matches to return within the configured search ceiling.
    """
    logger.info(
        "mcp_tool_started tool=search_knowledge query_chars=%d limit=%d",
        len(query),
        limit,
    )
    if not query.strip():
        logger.warning("mcp_tool_failed tool=search_knowledge reason=empty_query")
        raise ValueError("query não pode ser vazio")
    if not 1 <= limit <= settings.SEARCH_MAX_K:
        raise ValueError(
            f"limit deve estar entre 1 e {settings.SEARCH_MAX_K}"
        )
    started_at = perf_counter()
    result = search_qdrant(query.strip(), limit)
    logger.info(
        "mcp_tool_completed tool=search_knowledge result_count=%d duration_ms=%.1f",
        len(result),
        (perf_counter() - started_at) * 1000,
    )
    return result


@mcp.tool()
@instrument_tool("qdrant_status")
def qdrant_status() -> dict[str, Any]:
    """Check whether the configured Qdrant collection is reachable."""
    result = get_qdrant_status()
    DEPENDENCY_READY.labels("qdrant").set(
        1 if result.get("connected") else 0
    )
    return result


@mcp.tool()
@instrument_tool("postgres_status")
def postgres_status() -> dict[str, Any]:
    """Check whether the MIDAS read-only PostgreSQL connection is reachable."""
    result = get_postgres_status()
    DEPENDENCY_READY.labels("postgresql").set(
        1 if result.get("connected") else 0
    )
    return result


@mcp.tool()
@instrument_tool("get_user_context")
def get_user_context() -> dict[str, Any]:
    """Load profile and linked farms for the authenticated Keycloak identity."""
    started_at = perf_counter()
    user_type, user_id = get_authenticated_identity()
    logger.info("mcp_tool_started tool=get_user_context user_type=%s", user_type)
    result = get_database_user_context(user_type, user_id)
    logger.info(
        "mcp_tool_completed tool=get_user_context user_type=%s "
        "farms=%d enterprises=%d duration_ms=%.1f",
        user_type,
        len(result.get("farms", [])),
        len(result.get("enterprises", [])),
        (perf_counter() - started_at) * 1000,
    )
    return result


@mcp.tool()
@instrument_tool("get_consumption_summary")
def get_consumption_summary(
    period_days: Annotated[
        int,
        Field(
            ge=1,
            le=MAX_CONSUMPTION_PERIOD_DAYS,
            description="Janela de consumo em dias.",
        ),
    ] = DEFAULT_CONSUMPTION_PERIOD_DAYS,
) -> dict[str, Any]:
    """Aggregate scoped water and energy records for the authenticated identity.

    The tool never accepts user_id or farm_id. Scope is derived exclusively from
    the delegated Keycloak token and the PostgreSQL relationship model.
    """
    started_at = perf_counter()
    user_type, user_id = get_authenticated_identity()
    logger.info(
        "mcp_tool_started tool=get_consumption_summary user_type=%s period_days=%d",
        user_type,
        period_days,
    )
    result = get_database_consumption_summary(user_type, user_id, period_days)
    logger.info(
        "mcp_tool_completed tool=get_consumption_summary user_type=%s "
        "period_days=%d summaries=%d duration_ms=%.1f",
        user_type,
        period_days,
        len(result.get("summaries", [])),
        (perf_counter() - started_at) * 1000,
    )
    return result


@mcp.tool()
@instrument_tool("create_custom_dashboard")
async def create_custom_dashboard(
    title: Annotated[
        str,
        Field(min_length=1, max_length=120, description="Título curto do painel."),
    ],
    charts: Annotated[
        list[CustomDashboardChartSelection],
        Field(
            min_length=1,
            max_length=4,
            description=(
                "Selecione até quatro gráficos. Formatos compatíveis: current-flock "
                "(indicator); capacity-utilization e mortality-rate (indicator ou "
                "donut); farm-capacity e lot-throughput (bar, line ou histogram); "
                "lot-mortality, lot-cost, monthly-consumption e resource-efficiency "
                "(line/bar ou histogram); goal-status (pie, donut ou bar); goal-type "
                "(bar ou line). Prefira o tipo visual pedido pelo usuário quando for "
                "compatível. Histogramas representam a distribuição de valores "
                "numéricos. Use auto quando não houver preferência."
            ),
        ),
    ],
    ctx: Context,
    period_days: Annotated[
        int,
        Field(
            ge=1,
            le=366,
            description="Janela em dias aplicada aos gráficos temporais.",
        ),
    ] = 30,
) -> dict[str, Any]:
    """Compose a temporary dashboard from approved, user-scoped Ouros charts.

    The user's farm or enterprise is taken from the authenticated request. This
    tool does not accept IDs, SQL, or arbitrary chart definitions. The optional
    period is bounded and applies only to charts backed by dated analytics.
    It returns a dashboard payload with isolated Plotly HTML charts for the chat
    client to render.
    """
    started_at = perf_counter()
    user_type, _user_id = get_authenticated_identity()
    request = getattr(ctx.request_context, "request", None)
    headers = getattr(request, "headers", None)
    telemetry_authorization = (
        headers.get("x-ouros-telemetry-token") if headers is not None else None
    )
    scheme, _, telemetry_token = (telemetry_authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not telemetry_token.strip():
        raise PermissionError("token delegado do Telemetry indisponível")
    await verify_telemetry_access_token(telemetry_token.strip())
    try:
        result = await render_custom_dashboard(
            title,
            [chart.model_dump() for chart in charts],
            period_days,
            telemetry_token.strip(),
        )
    except (ValueError, DashboardServiceError) as exc:
        logger.warning(
            "mcp_tool_failed tool=create_custom_dashboard user_type=%s reason=%s",
            user_type,
            type(exc).__name__,
        )
        raise

    logger.info(
        "mcp_tool_completed tool=create_custom_dashboard user_type=%s "
        "charts=%d duration_ms=%.1f",
        user_type,
        len(result["charts"]),
        (perf_counter() - started_at) * 1000,
    )
    return result


@mcp.tool()
@instrument_tool("import_user_resource_records")
def import_user_resource_records(
    request_id: str,
    source_type: str,
    source_name: str,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Import historical records for the authenticated farm owner."""
    user_type, user_id = get_authenticated_identity()
    if user_type != FARM_OWNER_USER_TYPE:
        raise PermissionError(
            f"somente {FARM_OWNER_USER_TYPE} pode importar registros"
        )
    return get_database_import_resource_records(
        user_type,
        user_id,
        request_id,
        source_type,
        source_name,
        records,
    )


@mcp.tool()
@instrument_tool("prepare_resource_import")
def prepare_resource_import(
    filename: str,
    content_type: str,
    encoded_file: str,
) -> dict[str, Any]:
    """Convert a PDF/XLSX and use NVIDIA NIM to prepare an import preview.

    This tool never writes to PostgreSQL. The returned records must be reviewed
    and explicitly sent to import_user_resource_records afterward.
    """
    if not filename.strip():
        raise ValueError("filename não pode ser vazio")
    markdown = file_to_markdown(content_type, encoded_file)
    return extract_resource_records(markdown, filename.strip())
