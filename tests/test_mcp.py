import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.routing import Mount

from app.api.routes import health_check, read_root
from app.main import app
from app.mcp_server import (
    get_user_context,
    get_user_farm_data,
    mcp,
    postgres_status,
    qdrant_status,
    search_knowledge,
)
from app.services.auth import StaticTokenVerifier


class McpTests(unittest.TestCase):
    def test_mcp_binds_to_public_container_interface(self) -> None:
        """Keep the MCP transport bound to the container's external interface."""
        self.assertEqual(mcp.settings.host, "0.0.0.0")

    def test_public_mcp_endpoint_accepts_authenticated_host(self) -> None:
        """Ensure a public-host request is not rejected by transport security."""
        token = "test-static-token-with-at-least-32-characters"
        previous_verifier = mcp._token_verifier
        mcp._token_verifier = StaticTokenVerifier(token)
        route_index = next(
            index for index, route in enumerate(app.routes) if route.path == "/mcp"
        )
        previous_route = app.routes[route_index]
        app.routes[route_index] = Mount("/mcp", app=mcp.streamable_http_app())
        try:
            with TestClient(app) as client:
                response = client.post(
                    "/mcp/",
                    headers={
                        "Host": "ms-midas-mcp.discloud.app",
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/json, text/event-stream",
                        "Content-Type": "application/json",
                        "MCP-Protocol-Version": "2025-03-26",
                    },
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-03-26",
                            "capabilities": {},
                            "clientInfo": {"name": "test-client", "version": "1"},
                        },
                    },
                )
        finally:
            app.routes[route_index] = previous_route
            mcp._token_verifier = previous_verifier

        self.assertNotEqual(response.status_code, 421)
        self.assertNotEqual(response.status_code, 401)

    def test_fastapi_routes_and_app(self) -> None:
        self.assertEqual(read_root().message, "Ouros Knowledge MCP is running")
        self.assertEqual(health_check().status, "ok")
        self.assertIsNotNone(app)
        schema = app.openapi()
        self.assertEqual(schema["info"]["title"], "Ouros Knowledge MCP")
        self.assertIn("/health", schema["paths"])
        self.assertEqual(schema["paths"]["/health"]["get"]["tags"], ["Operação"])

    def test_search_validates_query_and_limit(self) -> None:
        with self.assertRaises(ValueError):
            search_knowledge("   ")
        with self.assertRaises(ValueError):
            search_knowledge("question", 21)

        with patch(
            "app.mcp_server.search_qdrant", return_value=[{"content": "answer"}]
        ) as search:
            self.assertEqual(search_knowledge(" question ", 2), [{"content": "answer"}])
        search.assert_called_once_with("question", 2)

    @patch("app.mcp_server.get_qdrant_status", return_value={"connected": True})
    @patch("app.mcp_server.get_postgres_status", return_value={"connected": True})
    def test_status_tools(self, postgres, qdrant) -> None:
        self.assertEqual(qdrant_status(), {"connected": True})
        self.assertEqual(postgres_status(), {"connected": True})
        qdrant.assert_called_once_with()
        postgres.assert_called_once_with()

    @patch("app.mcp_server.get_database_user_context", return_value={"profile": {}})
    @patch("app.mcp_server.get_authenticated_identity", return_value=("farm_owner", 42))
    def test_user_context_uses_token_identity(self, identity, context) -> None:
        self.assertEqual(get_user_context("farm_owner", 42), {"profile": {}})
        identity.assert_called_once_with("farm_owner", 42)
        context.assert_called_once_with("farm_owner", 42)

    @patch("app.mcp_server.get_database_user_farm_data", return_value={"data": {}})
    @patch("app.mcp_server.get_authenticated_identity", return_value=("farm_owner", 42))
    def test_user_farm_data_uses_token_identity(self, identity, farm_data) -> None:
        self.assertEqual(get_user_farm_data("farm_owner", 42, 5), {"data": {}})
        identity.assert_called_once_with("farm_owner", 42)
        farm_data.assert_called_once_with("farm_owner", 42, 5)


if __name__ == "__main__":
    unittest.main()
