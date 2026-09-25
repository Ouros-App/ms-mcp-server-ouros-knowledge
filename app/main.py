import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.core.config import settings
from app.mcp_server import mcp

logger = logging.getLogger(__name__)

OPENAPI_TAGS = [
    {
        "name": "Operação",
        "description": "Endpoints de disponibilidade e saúde da aplicação.",
    }
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run the MCP session manager for the FastAPI application lifetime."""
    logger.info(
        "mcp_application_starting issuer=%s audience=%s authorized_party=%s",
        settings.MCP_JWT_ISSUER,
        settings.MCP_JWT_AUDIENCE,
        settings.MCP_JWT_AUTHORIZED_PARTY,
    )
    async with mcp.session_manager.run():
        logger.info("mcp_application_ready")
        yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    description=(
        f"{settings.DESCRIPTION}\n\n"
        "O endpoint MCP está disponível em `/mcp/` via Streamable HTTP. "
        "As chamadas MCP exigem um access token JWT do Keycloak em `Authorization: Bearer`; "
        "a identidade das tools vem exclusivamente dos claims assinados."
    ),
    version=settings.VERSION,
    openapi_tags=OPENAPI_TAGS,
    lifespan=lifespan,
)

app.include_router(router)
app.mount("/mcp", mcp.streamable_http_app())
