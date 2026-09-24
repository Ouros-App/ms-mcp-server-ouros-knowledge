import unittest

from pydantic import ValidationError

from app.core.config import Settings


class ConfigAuthTests(unittest.TestCase):
    def test_keycloak_jwt_is_required(self) -> None:
        config = Settings(_env_file=None)

        self.assertEqual(
            config.MCP_JWT_ISSUER,
            "https://ouros-keycloak.discloud.app/realms/ouros",
        )
        self.assertEqual(
            config.MCP_JWT_AUDIENCE,
            "ms-mcp-server-ouros-knowledge",
        )
        self.assertEqual(
            config.MCP_JWT_AUTHORIZED_PARTY,
            "ms-ai-server-mcp-exchange",
        )

    def test_keycloak_jwt_contract_values_are_normalized(self) -> None:
        config = Settings(
            _env_file=None,
            MCP_JWT_ISSUER="  https://issuer.example/realms/ouros  ",
            MCP_JWT_AUDIENCE="  ms-mcp-server-ouros-knowledge  ",
            MCP_JWT_AUTHORIZED_PARTY="  ms-ai-server-mcp-exchange  ",
        )

        self.assertEqual(
            config.MCP_JWT_ISSUER,
            "https://issuer.example/realms/ouros",
        )
        self.assertEqual(
            config.MCP_JWT_AUDIENCE,
            "ms-mcp-server-ouros-knowledge",
        )
        self.assertEqual(
            config.MCP_JWT_AUTHORIZED_PARTY,
            "ms-ai-server-mcp-exchange",
        )

    def test_search_bounds_are_validated(self) -> None:
        with self.assertRaises(ValidationError):
            Settings(
                _env_file=None,
                SEARCH_TOP_K=0,
            )

        with self.assertRaises(ValidationError):
            Settings(
                _env_file=None,
                SEARCH_MAX_K=0,
            )

        with self.assertRaises(ValidationError):
            Settings(
                _env_file=None,
                SEARCH_TOP_K=10,
                SEARCH_MAX_K=5,
            )

    def test_blank_keycloak_jwt_config_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            Settings(
                _env_file=None,
                MCP_JWT_ISSUER="",
                MCP_JWT_AUDIENCE="ms-mcp-server-ouros-knowledge",
            )

        with self.assertRaises(ValidationError):
            Settings(
                _env_file=None,
                MCP_JWT_ISSUER="https://ouros-keycloak.discloud.app/realms/ouros",
                MCP_JWT_AUDIENCE="",
            )

        with self.assertRaises(ValidationError):
            Settings(
                _env_file=None,
                MCP_JWT_ISSUER="https://ouros-keycloak.discloud.app/realms/ouros",
                MCP_JWT_AUDIENCE="ms-mcp-server-ouros-knowledge",
                MCP_JWT_AUTHORIZED_PARTY="",
            )


if __name__ == "__main__":
    unittest.main()
