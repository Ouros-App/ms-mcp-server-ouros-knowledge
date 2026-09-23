from secrets import compare_digest

from fastapi import APIRouter, HTTPException, Request, Response, status
from prometheus_client import CONTENT_TYPE_LATEST

from app.core.config import settings
from app.core.metrics import metrics_payload
from app.schemas.common import HealthResponse, MessageResponse

router = APIRouter(tags=["Operação"])


@router.get(
    "/",
    response_model=MessageResponse,
    summary="Verificar disponibilidade",
    description="Retorna a mensagem básica de disponibilidade do serviço.",
    response_description="Mensagem de disponibilidade.",
)
def read_root() -> MessageResponse:
    """Return the service liveness message."""
    return MessageResponse(message="Ouros Knowledge MCP is running")


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Verificar saúde da aplicação",
    description="Endpoint de liveness para monitoramento da aplicação FastAPI.",
    response_description="Status atual da aplicação.",
)
def health_check() -> HealthResponse:
    """Return the service health status."""
    return HealthResponse(status="ok")


@router.get("/metrics", include_in_schema=False)
def metrics(request: Request) -> Response:
    """Expose low-cardinality Prometheus metrics to the telemetry collector."""
    configured = settings.METRICS_TOKEN
    if configured is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Métricas não configuradas.",
        )
    supplied = request.headers.get("Authorization", "").encode()
    expected = f"Bearer {configured.get_secret_value()}".encode()
    if not compare_digest(supplied, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Métricas não autorizadas.",
        )
    return Response(content=metrics_payload(), media_type=CONTENT_TYPE_LATEST)
