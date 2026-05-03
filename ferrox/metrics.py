"""Prometheus metrics for Ferrox"""

import os
import threading

from prometheus_client import Counter, Gauge, Histogram, start_http_server

# Metrics definitions
agent_requests_total = Counter(
    "ferrox_agent_requests_total", "Total number of agent requests", ["provider", "model", "status"]
)

agent_request_duration = Histogram(
    "ferrox_agent_request_duration_seconds",
    "Agent request duration in seconds",
    ["provider", "model"],
)

active_sessions = Gauge("ferrox_active_sessions", "Number of active chat sessions")

tool_calls_total = Counter(
    "ferrox_tool_calls_total", "Total number of tool calls", ["tool_name", "status"]
)

tool_call_duration = Histogram(
    "ferrox_tool_call_duration_seconds", "Tool call duration in seconds", ["tool_name"]
)

tokens_used_total = Counter("ferrox_tokens_used_total", "Total tokens used", ["provider", "model"])

errors_total = Counter("ferrox_errors_total", "Total number of errors", ["error_type", "component"])

fallback_attempts_total = Counter(
    "ferrox_fallback_attempts_total",
    "Total number of provider fallback attempts",
    ["from_provider", "to_provider"],
)


class MetricsServer:
    """Prometheus metrics server manager"""

    def __init__(self, port: int = 9090):
        self.port = port
        self.server_started = False
        self._lock = threading.Lock()

    def start(self) -> bool:
        """
        Start the Prometheus metrics HTTP server

        Returns:
            True if server was started, False if already running
        """
        with self._lock:
            if self.server_started:
                return False

            try:
                start_http_server(self.port)
                self.server_started = True
                return True
            except Exception as e:
                print(f"Failed to start metrics server: {e}")
                return False

    def is_running(self) -> bool:
        """Check if the metrics server is running"""
        with self._lock:
            return self.server_started


# Global metrics server instance
_metrics_server = None


def start_metrics_server(port: int = 9090) -> bool:
    """
    Start Prometheus metrics server

    Args:
        port: Port to run the metrics server on

    Returns:
        True if server was started, False if already running or failed
    """
    global _metrics_server

    # Get port from environment variable if not specified
    metrics_port = int(os.getenv("PROMETHEUS_PORT", str(port)))

    if _metrics_server is None:
        _metrics_server = MetricsServer(metrics_port)

    return _metrics_server.start()


def increment_agent_requests(provider: str, model: str, status: str = "success") -> None:
    """Increment agent requests counter"""
    agent_requests_total.labels(provider=provider, model=model, status=status).inc()


def record_agent_request_duration(provider: str, model: str, duration: float) -> None:
    """Record agent request duration"""
    agent_request_duration.labels(provider=provider, model=model).observe(duration)


def increment_active_sessions() -> None:
    """Increment active sessions gauge"""
    active_sessions.inc()


def decrement_active_sessions() -> None:
    """Decrement active sessions gauge"""
    active_sessions.dec()


def increment_tool_calls(tool_name: str, status: str = "success") -> None:
    """Increment tool calls counter"""
    tool_calls_total.labels(tool_name=tool_name, status=status).inc()


def record_tool_call_duration(tool_name: str, duration: float) -> None:
    """Record tool call duration"""
    tool_call_duration.labels(tool_name=tool_name).observe(duration)


def increment_tokens_used(provider: str, model: str, count: int = 1) -> None:
    """Increment tokens used counter"""
    tokens_used_total.labels(provider=provider, model=model).inc(count)


def increment_errors(error_type: str, component: str) -> None:
    """Increment errors counter"""
    errors_total.labels(error_type=error_type, component=component).inc()


def increment_fallback_attempts(from_provider: str, to_provider: str) -> None:
    """Increment fallback attempts counter"""
    fallback_attempts_total.labels(from_provider=from_provider, to_provider=to_provider).inc()
