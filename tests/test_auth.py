import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.core.config import settings
from app.services.auth import (
    KeycloakTokenVerifier,
    _decode_keycloak_token,
    _identity_from_claims,
    _jwks_url,
    get_authenticated_identity,
)


class AuthTests(unittest.IsolatedAsyncioTestCase):
    def test_jwks_url_supports_explicit_and_derived_modes(self) -> None:
        with (
            patch.object(settings, "MCP_JWKS_URL", "https://keys.example/jwks"),
            patch.object(settings, "MCP_JWT_ISSUER", "https://issuer.example"),
        ):
            self.assertEqual(_jwks_url(), "https://keys.example/jwks")

        with (
            patch.object(settings, "MCP_JWKS_URL", None),
            patch.object(settings, "MCP_JWT_ISSUER", "https://issuer.example/"),
        ):
            self.assertEqual(
                _jwks_url(),
                "https://issuer.example/protocol/openid-connect/certs",
            )

    def test_decode_keycloak_token_uses_rs256_issuer_and_audience(self) -> None:
        signing_key = SimpleNamespace(key="public-key")
        jwks_client = Mock()
        jwks_client.get_jwk_set.return_value = object()
        jwks_client.get_signing_key_from_jwt.return_value = signing_key
        expected_claims = {
            "sub": "subject",
            "azp": "ms-ai-server-mcp-exchange",
        }

        with (
            patch.object(settings, "MCP_JWKS_URL", "https://keys.example/jwks"),
            patch.object(settings, "MCP_JWT_ISSUER", "https://issuer.example"),
            patch.object(settings, "MCP_JWT_AUDIENCE", "mcp-audience"),
            patch.object(
                settings,
                "MCP_JWT_AUTHORIZED_PARTY",
                "ms-ai-server-mcp-exchange",
            ),
            patch("app.services.auth._get_jwks_client", return_value=jwks_client),
            patch("app.services.auth.decode", return_value=expected_claims) as decoder,
        ):
            claims = _decode_keycloak_token("signed-token")

        self.assertEqual(claims, expected_claims)
        jwks_client.get_jwk_set.assert_called_once_with()
        jwks_client.get_signing_key_from_jwt.assert_called_once_with("signed-token")
        self.assertEqual(decoder.call_args.kwargs["algorithms"], ["RS256"])
        self.assertEqual(decoder.call_args.kwargs["issuer"], "https://issuer.example")
        self.assertEqual(decoder.call_args.kwargs["audience"], "mcp-audience")

    def test_direct_mobile_authorized_party_is_rejected(self) -> None:
        signing_key = SimpleNamespace(key="public-key")
        jwks_client = Mock()
        jwks_client.get_jwk_set.return_value = object()
        jwks_client.get_signing_key_from_jwt.return_value = signing_key

        with (
            patch.object(settings, "MCP_JWKS_URL", "https://keys.example/jwks"),
            patch.object(settings, "MCP_JWT_ISSUER", "https://issuer.example"),
            patch.object(settings, "MCP_JWT_AUDIENCE", "mcp-audience"),
            patch.object(
                settings,
                "MCP_JWT_AUTHORIZED_PARTY",
                "ms-ai-server-mcp-exchange",
            ),
            patch("app.services.auth._get_jwks_client", return_value=jwks_client),
            patch(
                "app.services.auth.decode",
                return_value={
                    "sub": "subject",
                    "azp": "ouros-mobile",
                    "aud": ["mcp-audience"],
                },
            ),
        ):
            self.assertIsNone(_decode_keycloak_token("direct-mobile-token"))

    def test_identity_claim_validation(self) -> None:
        self.assertEqual(
            _identity_from_claims(
                {
                    "database_id": 7,
                    "account_type": "company_employee",
                    "realm_access": {"roles": ["company_employee"]},
                }
            ),
            ("company_employee", 7),
        )
        for claims in (
            {
                "database_id": 42,
                "account_type": "admin",
                "realm_access": {"roles": ["farm_owner"]},
            },
            {
                "database_id": 0,
                "account_type": "farm_owner",
                "realm_access": {"roles": ["farm_owner"]},
            },
            {
                "database_id": True,
                "account_type": "farm_owner",
                "realm_access": {"roles": ["farm_owner"]},
            },
        ):
            with self.subTest(claims=claims):
                self.assertIsNone(_identity_from_claims(claims))

    async def test_keycloak_token_returns_signed_business_claims(self) -> None:
        claims = {
            "sub": "keycloak-subject",
            "database_id": 42,
            "account_type": "farm_owner",
            "realm_access": {"roles": ["farm_owner"]},
            "scope": "openid ouros-identity",
            "exp": 2_147_483_647,
        }
        with patch("app.services.auth._decode_keycloak_token", return_value=claims):
            access_token = await KeycloakTokenVerifier().verify_token("signed-token")

        self.assertIsNotNone(access_token)
        assert access_token is not None
        self.assertEqual(access_token.subject, "keycloak-subject")
        self.assertEqual(access_token.claims["database_id"], 42)
        self.assertEqual(access_token.scopes, ["openid", "ouros-identity"])

    async def test_invalid_keycloak_token_is_rejected_without_fallback(self) -> None:
        with patch("app.services.auth._decode_keycloak_token", return_value=None):
            self.assertIsNone(
                await KeycloakTokenVerifier().verify_token("not-a-keycloak-token")
            )

    @patch("app.services.auth.get_access_token")
    def test_identity_is_derived_only_from_keycloak_claims(self, get_access_token) -> None:
        get_access_token.return_value = SimpleNamespace(
            claims={
                "database_id": 42,
                "account_type": "farm_owner",
                "realm_access": {"roles": ["farm_owner"]},
            }
        )
        self.assertEqual(get_authenticated_identity(), ("farm_owner", 42))

    @patch("app.services.auth.get_access_token", return_value=None)
    def test_missing_token_requires_authentication(self, _get_access_token) -> None:
        with self.assertRaises(PermissionError):
            get_authenticated_identity()

    @patch("app.services.auth.get_access_token")
    def test_invalid_claim_identity_is_rejected(self, get_access_token) -> None:
        get_access_token.return_value = SimpleNamespace(claims={})
        with self.assertRaises(PermissionError):
            get_authenticated_identity()


if __name__ == "__main__":
    unittest.main()
