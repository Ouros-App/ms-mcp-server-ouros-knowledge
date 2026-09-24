from contextlib import contextmanager
from time import perf_counter

from prometheus_client import Counter, Gauge, Histogram, generate_latest

HTTP_REQUESTS = Counter(
    "ouros_mcp_http_requests",
    "Total de requisicoes HTTP recebidas pelo Knowledge MCP.",
    ("method", "route", "status"),
)
HTTP_DURATION = Histogram(
    "ouros_mcp_http_request_duration_seconds",
    "Duracao das requisicoes HTTP do Knowledge MCP.",
    ("method", "route"),
)
TOOL_CALLS = Counter(
    "ouros_mcp_tool_calls",
    "Chamadas de tools MCP por resultado.",
    ("tool", "outcome"),
)
TOOL_DURATION = Histogram(
    "ouros_mcp_tool_duration_seconds",
    "Duracao da execucao de tools no Knowledge MCP.",
    ("tool",),
)
TOOL_IN_FLIGHT = Gauge(
    "ouros_mcp_tool_in_flight",
    "Tools MCP em execucao neste processo.",
    ("tool",),
)

_ALLOWED_TOOLS = {
    "search_knowledge",
    "qdrant_status",
    "postgres_status",
    "get_user_context",
    "get_user_farm_data",
    "get_consumption_summary",
    "import_user_resource_records",
    "prepare_resource_import",
}


def safe_tool_name(tool: object) -> str:
    return tool if isinstance(tool, str) and tool in _ALLOWED_TOOLS else "unknown"


def metric_route(path: str) -> str:
    if path.startswith("/mcp"):
        return "/mcp"
    if path == "/metrics":
        return "/metrics"
    if path == "/health":
        return "/health"
    if path == "/":
        return "/"
    return "unmatched"


def observe_http_request(
    method: str,
    route: str,
    status: int | str,
    duration_seconds: float,
) -> None:
    HTTP_REQUESTS.labels(method, route, str(status)).inc()
    HTTP_DURATION.labels(method, route).observe(max(duration_seconds, 0.0))


@contextmanager
def observe_tool(tool: str):
    """Measure a bounded tool label without recording arguments or user data."""
    safe_tool = safe_tool_name(tool)
    started_at = perf_counter()
    TOOL_IN_FLIGHT.labels(safe_tool).inc()
    try:
        yield
    except Exception:
        TOOL_CALLS.labels(safe_tool, "error").inc()
        raise
    else:
        TOOL_CALLS.labels(safe_tool, "success").inc()
    finally:
        TOOL_DURATION.labels(safe_tool).observe(perf_counter() - started_at)
        TOOL_IN_FLIGHT.labels(safe_tool).dec()


def metrics_payload() -> bytes:
    return generate_latest()
