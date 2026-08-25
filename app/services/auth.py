import secrets

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
    ) -> None:
        """Load the shared token used to authenticate the MCP client."""
        self.token = token if token is not None else settings.MCP_AUTH_TOKEN
        self.resource_url = resource_url or settings.MCP_RESOURCE_URL

    async def verify_token(self, token: str) -> AccessToken | None:
        """Return access information when the bearer token matches exactly."""
        if not self.token or len(self.token) < 32:
            return None
        if not secrets.compare_digest(token, self.token):
            return None

        return AccessToken(
            token=token,
            client_id="midas",
            scopes=["mcp"],
            expires_at=STATIC_TOKEN_EXPIRY,
            resource=self.resource_url,
            subject="midas",
            claims={},
        )


def get_authenticated_identity(user_type: str, user_id: int) -> tuple[str, int]:
    """Validate the requested database identity after MCP authentication."""
    access_token = get_access_token()
    if access_token is None:
        raise PermissionError("autenticação MCP obrigatória")

    if (
        not isinstance(user_type, str)
        or user_type not in VALID_USER_TYPES
        or not isinstance(user_id, int)
        or user_id <= 0
    ):
        raise PermissionError("identidade MCP inválida")
    return user_type, user_id
