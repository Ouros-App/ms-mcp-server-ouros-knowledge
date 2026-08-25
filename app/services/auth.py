import secrets
from typing import Any

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken

from app.core.config import settings

VALID_USER_TYPES = {"farm_owner", "company_employee", "admin"}
STATIC_TOKEN_EXPIRY = 2_147_483_647


class StaticTokenVerifier:
    """Validate one shared bearer token configured for the MCP server."""

    def __init__(
        self,
        token: str | None = None,
        resource_url: str | None = None,
        user_type: str | None = None,
        user_id: int | None = None,
    ) -> None:
        """Load the shared token and optional fixed database identity."""
        self.token = token if token is not None else settings.MCP_AUTH_TOKEN
        self.resource_url = resource_url or settings.MCP_RESOURCE_URL
        self.user_type = user_type if user_type is not None else settings.MCP_USER_TYPE
        self.user_id = user_id if user_id is not None else settings.MCP_USER_ID

    async def verify_token(self, token: str) -> AccessToken | None:
        """Return access information when the bearer token matches exactly."""
        if not self.token or len(self.token) < 32:
            return None
        if not secrets.compare_digest(token, self.token):
            return None

        claims: dict[str, Any] = {}
        if self.user_type is not None and self.user_id is not None:
            if self.user_type not in VALID_USER_TYPES or self.user_id <= 0:
                return None
            claims = {"sub": str(self.user_id), "user_type": self.user_type}

        return AccessToken(
            token=token,
            client_id="midas",
            scopes=["mcp"],
            expires_at=STATIC_TOKEN_EXPIRY,
            resource=self.resource_url,
            subject=str(self.user_id) if self.user_id is not None else "midas",
            claims=claims,
        )


def get_authenticated_identity() -> tuple[str, int]:
    """Derive the database identity from the verified MCP access token."""
    access_token = get_access_token()
    if access_token is None:
        raise PermissionError("autenticação MCP obrigatória")

    claims = access_token.claims or {}
    user_type = claims.get("user_type") or settings.MCP_USER_TYPE
    configured_user_id = settings.MCP_USER_ID
    user_id_claim = claims.get("sub")
    user_id_value = user_id_claim if user_id_claim is not None else configured_user_id
    try:
        user_id = int(user_id_value or "")
    except (TypeError, ValueError) as error:
        raise PermissionError("identidade MCP inválida") from error

    if user_type not in VALID_USER_TYPES or user_id <= 0:
        raise PermissionError("identidade MCP inválida")
    return user_type, user_id
