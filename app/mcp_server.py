from typing import Annotated, Any

from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from pydantic import Field

from app.core.config import settings
from app.core.identity import FARM_OWNER_USER_TYPE
from app.core.metrics import observe_tool
from app.services.auth import (
    KeycloakTokenVerifier,
    get_authenticated_identity,
)
from app.services.database import (
    DEFAULT_CONSUMPTION_PERIOD_DAYS,
    DEFAULT_FARM_DATA_LIMIT,
    MAX_CONSUMPTION_PERIOD_DAYS,
    MAX_FARM_DATA_LIMIT,
)
from app.services.database import (
    get_consumption_summary as get_database_consumption_summary,
)
from app.services.database import (
    get_user_context as get_database_user_context,
)
from app.services.database import (
    get_user_farm_data as get_database_user_farm_data,
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
    with observe_tool("search_knowledge"):
        if not query.strip():
            raise ValueError("query não pode ser vazio")
        if not 1 <= limit <= settings.SEARCH_MAX_K:
            raise ValueError(
                f"limit deve estar entre 1 e {settings.SEARCH_MAX_K}"
            )
        return search_qdrant(query.strip(), limit)


@mcp.tool()
def qdrant_status() -> dict[str, Any]:
    """Check whether the configured Qdrant collection is reachable."""
    with observe_tool("qdrant_status"):
        return get_qdrant_status()


@mcp.tool()
def postgres_status() -> dict[str, Any]:
    """Check whether the MIDAS read-only PostgreSQL connection is reachable."""
    with observe_tool("postgres_status"):
        return get_postgres_status()


@mcp.tool()
def get_user_context() -> dict[str, Any]:
    """Load profile and linked farms for the authenticated Keycloak identity."""
    with observe_tool("get_user_context"):
        user_type, user_id = get_authenticated_identity()
        return get_database_user_context(user_type, user_id)


@mcp.tool()
def get_user_farm_data(
    limit: Annotated[
        int,
        Field(
            ge=1,
            le=MAX_FARM_DATA_LIMIT,
            description="Quantidade maxima por conjunto de dados.",
        ),
    ] = DEFAULT_FARM_DATA_LIMIT,
) -> dict[str, Any]:
    """Load bounded farm data for the authenticated Keycloak identity."""
    with observe_tool("get_user_farm_data"):
        user_type, user_id = get_authenticated_identity()
        return get_database_user_farm_data(user_type, user_id, limit)


@mcp.tool()
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
    with observe_tool("get_consumption_summary"):
        user_type, user_id = get_authenticated_identity()
        return get_database_consumption_summary(user_type, user_id, period_days)


@mcp.tool()
def import_user_resource_records(
    request_id: str,
    source_type: str,
    source_name: str,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Import historical records for the authenticated farm owner."""
    with observe_tool("import_user_resource_records"):
        user_type, user_id = get_authenticated_identity()
        if user_type != "farm_owner":
            raise PermissionError("somente farm_owner pode importar registros")
        return get_database_import_resource_records(
            user_type,
            user_id,
            request_id,
            source_type,
            source_name,
            records,
        )


@mcp.tool()
def prepare_resource_import(
    filename: str,
    content_type: str,
    encoded_file: str,
) -> dict[str, Any]:
    """Convert a PDF/XLSX and use NVIDIA NIM to prepare an import preview.

    This tool never writes to PostgreSQL. The returned records must be reviewed
    and explicitly sent to import_user_resource_records afterward.
    """
    with observe_tool("prepare_resource_import"):
        if not filename.strip():
            raise ValueError("filename não pode ser vazio")
        markdown = file_to_markdown(content_type, encoded_file)
        return extract_resource_records(markdown, filename.strip())
