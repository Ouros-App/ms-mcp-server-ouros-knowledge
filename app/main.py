from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI, Request

from app.api.routes import router
from app.core.config import settings
from app.core.metrics import metric_route, observe_http_request
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
        "As chamadas MCP exigem um access token JWT do Keycloak em `Authorization: Bearer`; "
        "a identidade das tools vem exclusivamente dos claims assinados."
    ),
    version=settings.VERSION,
    openapi_tags=OPENAPI_TAGS,
    lifespan=lifespan,
)

@app.middleware("http")
async def observe_requests(request: Request, call_next):
    started_at = perf_counter()
    route = metric_route(request.url.path)
    try:
        response = await call_next(request)
    except Exception:
        observe_http_request(
            request.method,
            route,
            500,
            perf_counter() - started_at,
        )
        raise
    observe_http_request(
        request.method,
        route,
        response.status_code,
        perf_counter() - started_at,
    )
    return response


app.include_router(router)
app.mount("/mcp", mcp.streamable_http_app())
