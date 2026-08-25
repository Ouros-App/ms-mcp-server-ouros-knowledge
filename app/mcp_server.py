from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from app.core.config import settings
from app.services.database import (
    get_user_context as get_database_user_context,
)
from app.services.database import (
    get_user_farm_data as get_database_user_farm_data,
)
from app.services.database import (
    postgres_status as get_postgres_status,
)
from app.services.knowledge import (
    qdrant_status as get_qdrant_status,
)
from app.services.knowledge import (
    search_knowledge as search_qdrant,
)

mcp = FastMCP(
    name=settings.PROJECT_NAME,
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
)


@mcp.tool()
def search_knowledge(
    query: str, limit: int = settings.SEARCH_TOP_K
) -> list[dict[str, Any]]:
    """Search the configured Qdrant knowledge collection using NVIDIA embeddings."""
    if not query.strip():
        raise ValueError("query não pode ser vazio")
    if not 1 <= limit <= 20:
        raise ValueError("limit deve estar entre 1 e 20")
    return search_qdrant(query.strip(), limit)


@mcp.tool()
def qdrant_status() -> dict[str, Any]:
    """Check whether the configured Qdrant collection is reachable."""
    return get_qdrant_status()


@mcp.tool()
def postgres_status() -> dict[str, Any]:
    """Check whether the MIDAS read-only PostgreSQL connection is reachable."""
    return get_postgres_status()


@mcp.tool()
def get_user_context(
    user_type: Literal["farm_owner", "company_employee", "admin"],
    user_id: int,
) -> dict[str, Any]:
    """Load a user's profile and linked farms for personalized answers.

    The application should derive user_type and user_id from its authenticated
    session instead of letting the model choose another user's identity.
    """
    return get_database_user_context(user_type, user_id)


@mcp.tool()
def get_user_farm_data(
    user_type: Literal["farm_owner", "company_employee", "admin"],
    user_id: int,
    limit: int = 20,
) -> dict[str, Any]:
    """Load bounded goals, consumption, lots, and tips for the user's farms."""
    return get_database_user_farm_data(user_type, user_id, limit)
