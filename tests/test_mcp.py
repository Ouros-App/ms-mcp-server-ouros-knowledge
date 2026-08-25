import unittest
from unittest.mock import patch

from app.api.routes import health_check, read_root
from app.main import app
from app.mcp_server import (
    get_user_context,
    get_user_farm_data,
    postgres_status,
    qdrant_status,
    search_knowledge,
)


class McpTests(unittest.TestCase):
    def test_fastapi_routes_and_app(self) -> None:
        self.assertEqual(read_root().message, "Ouros Knowledge MCP is running")
        self.assertEqual(health_check().status, "ok")
        self.assertIsNotNone(app)

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
