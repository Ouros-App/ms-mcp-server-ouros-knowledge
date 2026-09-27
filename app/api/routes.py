from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from prometheus_client import CONTENT_TYPE_LATEST

from app.core.metrics import metrics_payload
from app.schemas.common import HealthResponse, MessageResponse
from app.services.auth import (
    AuthenticationKeyServiceError,
    verify_metrics_token,
)

router = APIRouter(tags=["Operação"])
metrics_bearer = HTTPBearer(auto_error=False)


async def require_metrics_bearer(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(metrics_bearer),
    ],
) -> dict:
    """Allow only the managed ouros-prometheus service account."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid metrics credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        claims = await verify_metrics_token(credentials.credentials)
    except AuthenticationKeyServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Metrics authentication temporarily unavailable.",
        ) from exc
    if claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid metrics credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return claims


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
async def metrics(
    _claims: Annotated[dict, Depends(require_metrics_bearer)],
) -> Response:
    """Expose Prometheus metrics to the dedicated scraper identity."""
    return Response(
        content=metrics_payload(),
        media_type=CONTENT_TYPE_LATEST,
    )
