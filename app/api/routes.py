from fastapi import APIRouter

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
