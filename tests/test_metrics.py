import pytest

from app.core.metrics import DEPENDENCY_READY, instrument_tool
from app.services import auth


def test_tool_instrumentation_preserves_function_contract() -> None:
    @instrument_tool("example")
    def add(left: int, right: int = 1) -> int:
        return left + right

    assert add(2, right=3) == 5
    assert add.__name__ == "add"


@pytest.mark.asyncio
async def test_metrics_token_accepts_prometheus_authorized_party(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        auth,
        "_decode_metrics_token",
        lambda _token: {"azp": "ouros-prometheus"},
    )

    claims = await auth.verify_metrics_token("signed-token")

    assert claims == {"azp": "ouros-prometheus"}


def test_dependency_gauge_is_available() -> None:
    DEPENDENCY_READY.labels("qdrant").set(1)
