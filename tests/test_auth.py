import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services.auth import StaticTokenVerifier, get_authenticated_identity


class AuthTests(unittest.IsolatedAsyncioTestCase):
    token = "test-static-token-with-at-least-32-characters"

    async def test_matching_static_token_returns_fixed_identity(self) -> None:
        verifier = StaticTokenVerifier(
            self.token,
            "http://localhost:8000/mcp",
            "farm_owner",
            42,
        )

        access_token = await verifier.verify_token(self.token)

        self.assertIsNotNone(access_token)
        assert access_token is not None
        self.assertEqual(access_token.subject, "42")
        self.assertEqual(access_token.claims, {"sub": "42", "user_type": "farm_owner"})

    async def test_invalid_or_weak_static_token_is_rejected(self) -> None:
        verifier = StaticTokenVerifier(self.token)

        self.assertIsNone(await verifier.verify_token("wrong-token"))
        self.assertIsNone(await StaticTokenVerifier("short").verify_token("short"))
        self.assertIsNone(
            await StaticTokenVerifier(
                self.token, user_type="unknown", user_id=1
            ).verify_token(self.token)
        )

    @patch("app.services.auth.get_access_token")
    def test_identity_is_derived_from_verified_claims(self, get_access_token) -> None:
        get_access_token.return_value = SimpleNamespace(
            claims={"sub": "7", "user_type": "company_employee"}
        )

        self.assertEqual(get_authenticated_identity(), ("company_employee", 7))

    @patch("app.services.auth.get_access_token")
    @patch("app.services.auth.settings.MCP_USER_TYPE", "farm_owner")
    @patch("app.services.auth.settings.MCP_USER_ID", 9)
    def test_identity_uses_fixed_environment_defaults(self, get_access_token) -> None:
        get_access_token.return_value = SimpleNamespace(claims={})

        self.assertEqual(get_authenticated_identity(), ("farm_owner", 9))

    @patch("app.services.auth.get_access_token", return_value=None)
    def test_missing_identity_requires_authentication(self, _get_access_token) -> None:
        with self.assertRaises(PermissionError):
            get_authenticated_identity()

    @patch("app.services.auth.get_access_token")
    def test_invalid_identity_requires_authentication(self, get_access_token) -> None:
        get_access_token.return_value = SimpleNamespace(
            claims={"sub": "not-an-id", "user_type": "farm_owner"}
        )

        with self.assertRaises(PermissionError):
            get_authenticated_identity()


if __name__ == "__main__":
    unittest.main()
