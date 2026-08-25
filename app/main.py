from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.core.config import settings
from app.mcp_server import mcp

OPENAPI_TAGS = [
    {
        "name": "Operação",
        "description": "Endpoints de disponibilidade e saúde da aplicação.",
    }
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run the MCP session manager for the FastAPI application lifetime."""
    async with mcp.session_manager.run():
        yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    description=(
        f"{settings.DESCRIPTION}\n\n"
        "O endpoint MCP está disponível em `/mcp/` via Streamable HTTP. "
        "As chamadas MCP exigem `Authorization: Bearer <MCP_AUTH_TOKEN>`; "
        "as tools de contexto recebem `user_type` e `user_id` em cada chamada."
    ),
    version=settings.VERSION,
    openapi_tags=OPENAPI_TAGS,
    lifespan=lifespan,
)

app.include_router(router)
app.mount("/mcp", mcp.streamable_http_app())
