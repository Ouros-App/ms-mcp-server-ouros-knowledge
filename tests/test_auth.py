import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import jwt

from app.services.auth import MidasTokenVerifier, get_authenticated_identity


class AuthTests(unittest.IsolatedAsyncioTestCase):
    secret = "test-secret-with-at-least-32-characters"
    issuer = "https://issuer.test"
    audience = "http://localhost:8000/mcp"

    def make_token(self, **changes: object) -> str:
        payload = {
            "sub": "42",
            "user_type": "farm_owner",
            "iss": self.issuer,
            "aud": self.audience,
            "exp": int(time.time()) + 300,
        }
        payload.update(changes)
        return jwt.encode(payload, self.secret, algorithm="HS256")

    async def test_valid_token_returns_access_token(self) -> None:
        verifier = MidasTokenVerifier(self.secret, self.issuer, self.audience)

        access_token = await verifier.verify_token(
            self.make_token(scope="read:profile")
        )

        self.assertIsNotNone(access_token)
        assert access_token is not None
        self.assertEqual(access_token.subject, "42")
        self.assertEqual(access_token.scopes, ["read:profile"])
        self.assertEqual(access_token.claims["user_type"], "farm_owner")

    async def test_invalid_token_is_rejected(self) -> None:
        verifier = MidasTokenVerifier(self.secret, self.issuer, self.audience)

        for token in (
            self.make_token(user_type="unknown"),
            self.make_token(sub="0"),
            self.make_token(aud="http://other.test/mcp"),
            self.make_token(exp=int(time.time()) - 1),
        ):
            self.assertIsNone(await verifier.verify_token(token))

        self.assertIsNone(
            await MidasTokenVerifier("short").verify_token(self.make_token())
        )

    @patch("app.services.auth.get_access_token")
    def test_identity_is_derived_from_verified_claims(self, get_access_token) -> None:
        get_access_token.return_value = SimpleNamespace(
            claims={"sub": "7", "user_type": "company_employee"}
        )

        self.assertEqual(get_authenticated_identity(), ("company_employee", 7))

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
