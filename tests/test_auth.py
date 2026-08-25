import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services.auth import StaticTokenVerifier, get_authenticated_identity


class AuthTests(unittest.IsolatedAsyncioTestCase):
    token = "test-static-token-with-at-least-32-characters"

    async def test_matching_static_token_returns_access_token(self) -> None:
        verifier = StaticTokenVerifier(self.token, "http://localhost:8000/mcp")

        access_token = await verifier.verify_token(self.token)

        self.assertIsNotNone(access_token)
        assert access_token is not None
        self.assertEqual(access_token.subject, "midas")
        self.assertEqual(access_token.claims, {})

    async def test_invalid_or_weak_static_token_is_rejected(self) -> None:
        verifier = StaticTokenVerifier(self.token)

        self.assertIsNone(await verifier.verify_token("wrong-token"))
        self.assertIsNone(await StaticTokenVerifier("short").verify_token("short"))

    @patch("app.services.auth.get_access_token")
    def test_identity_is_validated_after_authentication(self, get_access_token) -> None:
        get_access_token.return_value = SimpleNamespace(claims={})

        self.assertEqual(
            get_authenticated_identity("company_employee", 7),
            ("company_employee", 7),
        )

    @patch("app.services.auth.get_access_token", return_value=None)
    def test_missing_token_requires_authentication(self, _get_access_token) -> None:
        with self.assertRaises(PermissionError):
            get_authenticated_identity("farm_owner", 42)

    @patch("app.services.auth.get_access_token")
    def test_invalid_identity_requires_authentication(self, get_access_token) -> None:
        get_access_token.return_value = SimpleNamespace(claims={})

        with self.assertRaises(PermissionError):
            get_authenticated_identity("unknown", 42)  # type: ignore[arg-type]
        with self.assertRaises(PermissionError):
            get_authenticated_identity("farm_owner", 0)


if __name__ == "__main__":
    unittest.main()
