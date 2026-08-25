from functools import lru_cache
from typing import Any

from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

from app.core.config import settings


def _require_nvidia_key() -> str:
    if not settings.NVIDIA_API_KEY:
        raise RuntimeError("NVIDIA_API_KEY não está configurada no .env")
    return settings.NVIDIA_API_KEY


@lru_cache(maxsize=1)
def get_qdrant_client() -> QdrantClient:
    return QdrantClient(
        url=settings.QDRANT_URL,
        api_key=settings.QDRANT_API_KEY or None,
    )


@lru_cache(maxsize=1)
def get_vector_store() -> QdrantVectorStore:
    embeddings = NVIDIAEmbeddings(
        model=settings.NVIDIA_EMBEDDING_MODEL,
        nvidia_api_key=_require_nvidia_key(),
        base_url=settings.NVIDIA_BASE_URL,
    )
    return QdrantVectorStore(
        client=get_qdrant_client(),
        collection_name=settings.QDRANT_COLLECTION_NAME,
        embedding=embeddings,
    )


def search_knowledge(query: str, limit: int) -> list[dict[str, Any]]:
    documents = get_vector_store().similarity_search_with_score(query, k=limit)
    return [
        {
            "content": document.page_content,
            "metadata": document.metadata,
            "score": score,
        }
        for document, score in documents
    ]


def qdrant_status() -> dict[str, Any]:
    try:
        get_qdrant_client().get_collection(settings.QDRANT_COLLECTION_NAME)
        return {
            "connected": True,
            "collection": settings.QDRANT_COLLECTION_NAME,
            "exists": True,
        }
    except Exception as error:  # noqa: BLE001 - status must report client/network failures
        return {
            "connected": False,
            "collection": settings.QDRANT_COLLECTION_NAME,
            "exists": False,
            "error": type(error).__name__,
        }
