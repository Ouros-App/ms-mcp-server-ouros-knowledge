import time
from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from prometheus_client import Counter, Gauge, Histogram, generate_latest

P = ParamSpec("P")
R = TypeVar("R")

HTTP_REQUESTS = Counter(
    "mcp_server_http_requests_total",
    "Total de requisicoes HTTP recebidas pelo MCP.",
    ("method", "route", "status"),
)
HTTP_DURATION = Histogram(
    "mcp_server_http_request_duration_seconds",
    "Duracao das requisicoes HTTP do MCP em segundos.",
    ("method", "route"),
)
TOOL_CALLS = Counter(
    "mcp_server_tool_calls_total",
    "Chamadas de tools MCP por resultado.",
    ("tool", "outcome"),
)
TOOL_DURATION = Histogram(
    "mcp_server_tool_duration_seconds",
    "Duracao das tools MCP em segundos.",
    ("tool",),
)
DEPENDENCY_READY = Gauge(
    "mcp_server_dependency_ready",
    "Estado conhecido da dependencia (1=ready, 0=down).",
    ("dependency",),
)


def metric_path(path: str) -> str:
    """Return bounded route labels for REST and Streamable HTTP traffic."""
    normalized = path.rstrip("/") or "/"
    if normalized == "/mcp" or normalized.startswith("/mcp/"):
        return "/mcp"
    if normalized in {"/", "/health", "/metrics", "/docs", "/openapi.json"}:
        return normalized
    return "{unknown}"


def instrument_tool(name: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Observe one synchronous FastMCP tool without changing its signature."""
    def decorator(function: Callable[P, R]) -> Callable[P, R]:
        @wraps(function)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            started = time.perf_counter()
            outcome = "error"
            try:
                result = function(*args, **kwargs)
                outcome = "success"
                return result
            finally:
                TOOL_CALLS.labels(name, outcome).inc()
                TOOL_DURATION.labels(name).observe(
                    time.perf_counter() - started
                )
        return wrapped
    return decorator


def metrics_payload() -> bytes:
    return generate_latest()
