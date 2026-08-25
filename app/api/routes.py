from fastapi import APIRouter

from app.schemas.common import HealthResponse, MessageResponse

router = APIRouter()


@router.get("/", response_model=MessageResponse)
def read_root() -> MessageResponse:
    """Return the service liveness message."""
    return MessageResponse(message="Ouros Knowledge MCP is running")


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Return the service health status."""
    return HealthResponse(status="ok")
