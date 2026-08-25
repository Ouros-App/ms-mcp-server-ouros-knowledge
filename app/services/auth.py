import jwt
from jwt import InvalidTokenError
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken

from app.core.config import settings

VALID_USER_TYPES = {"farm_owner", "company_employee", "admin"}


class MidasTokenVerifier:
    """Validate signed user identity tokens for the MCP resource server."""

    def __init__(
        self,
        secret: str | None = None,
        issuer: str | None = None,
        audience: str | None = None,
    ) -> None:
        """Initialize verification settings from explicit values or the environment."""
        self.secret = secret if secret is not None else settings.MCP_JWT_SECRET
        self.issuer = issuer or settings.MCP_JWT_ISSUER_URL
        self.audience = audience or settings.MCP_RESOURCE_URL

    async def verify_token(self, token: str) -> AccessToken | None:
        """Return authenticated claims when a JWT is valid and scoped."""
        if not self.secret or len(self.secret) < 32:
            return None
        try:
            claims = jwt.decode(
                token,
                self.secret,
                algorithms=["HS256"],
                audience=self.audience,
                issuer=self.issuer,
                options={"require": ["exp", "sub", "user_type"]},
            )
            user_type = claims.get("user_type")
            user_id = int(claims["sub"])
            if user_type not in VALID_USER_TYPES or user_id <= 0:
                return None
        except (InvalidTokenError, TypeError, ValueError):
            return None

        scope = claims.get("scope", "")
        scopes = scope if isinstance(scope, list) else str(scope).split()
        return AccessToken(
            token=token,
            client_id=str(claims.get("client_id", "midas")),
            scopes=scopes,
            expires_at=int(claims["exp"]),
            resource=self.audience,
            subject=str(user_id),
            claims=claims,
        )


def get_authenticated_identity() -> tuple[str, int]:
    """Derive the database identity from the verified MCP access token."""
    access_token = get_access_token()
    if access_token is None or not access_token.claims:
        raise PermissionError("autenticação MCP obrigatória")

    user_type = access_token.claims.get("user_type")
    try:
        user_id = int(access_token.claims.get("sub", ""))
    except (TypeError, ValueError) as error:
        raise PermissionError("identidade MCP inválida") from error

    if user_type not in VALID_USER_TYPES or user_id <= 0:
        raise PermissionError("identidade MCP inválida")
    return user_type, user_id
