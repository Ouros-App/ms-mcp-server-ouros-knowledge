import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services.knowledge import qdrant_status, search_knowledge


class KnowledgeTests(unittest.TestCase):
    def test_search_knowledge_maps_results(self) -> None:
        store = SimpleNamespace(
            similarity_search_with_score=lambda query, k: [
                (
                    SimpleNamespace(page_content="answer", metadata={"source": "doc"}),
                    0.9,
                )
            ]
        )
        with patch("app.services.knowledge.get_vector_store", return_value=store):
            self.assertEqual(
                search_knowledge("question", 1),
                [{"content": "answer", "metadata": {"source": "doc"}, "score": 0.9}],
            )

    @patch("app.services.knowledge.settings.QDRANT_COLLECTION_NAME", "test_collection")
    def test_qdrant_status_success_and_failure(self) -> None:
        client = SimpleNamespace(get_collection=lambda collection: None)
        with patch("app.services.knowledge.get_qdrant_client", return_value=client):
            self.assertEqual(
                qdrant_status(),
                {"connected": True, "collection": "test_collection", "exists": True},
            )

        failing_client = SimpleNamespace(
            get_collection=lambda collection: (_ for _ in ()).throw(ConnectionError())
        )
        with patch(
            "app.services.knowledge.get_qdrant_client", return_value=failing_client
        ):
            result = qdrant_status()
        self.assertFalse(result["connected"])
        self.assertEqual(result["error"], "ConnectionError")


if __name__ == "__main__":
    unittest.main()
