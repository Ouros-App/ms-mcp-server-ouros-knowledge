import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from app.api.routes import router
from app.core.config import settings
from app.core.metrics import HTTP_DURATION, HTTP_REQUESTS, metric_path
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

@app.middleware("http")
async def prometheus_request_metrics(request: Request, call_next):
    """Record bounded HTTP request telemetry for REST and MCP transport."""
    started = time.perf_counter()
    route = metric_path(request.url.path)
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        duration = time.perf_counter() - started
        HTTP_REQUESTS.labels(
            request.method,
            route,
            str(status_code),
        ).inc()
        HTTP_DURATION.labels(request.method, route).observe(duration)


app.include_router(router)
app.mount("/mcp", mcp.streamable_http_app())
