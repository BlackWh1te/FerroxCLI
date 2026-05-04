"""Tests for ferrox metrics module"""

from unittest.mock import MagicMock, patch

from ferrox.metrics import (
    MetricsServer,
    decrement_active_sessions,
    increment_active_sessions,
    increment_agent_requests,
    increment_errors,
    increment_fallback_attempts,
    increment_tokens_used,
    increment_tool_calls,
    record_agent_request_duration,
    record_tool_call_duration,
    start_metrics_server,
)


class TestMetricsServer:
    def test_init_sets_defaults(self):
        server = MetricsServer(port=9090)
        assert server.port == 9090
        assert server.server_started is False

    @patch("ferrox.metrics.start_http_server")
    def test_start_returns_true_on_success(self, mock_start):
        server = MetricsServer(port=9090)
        result = server.start()
        assert result is True
        assert server.server_started is True
        mock_start.assert_called_once_with(9090)

    @patch("ferrox.metrics.start_http_server")
    def test_start_returns_false_on_exception(self, mock_start):
        mock_start.side_effect = Exception("Port in use")
        server = MetricsServer(port=9090)
        result = server.start()
        assert result is False

    @patch("ferrox.metrics.start_http_server")
    def test_start_returns_false_if_already_running(self, mock_start):
        server = MetricsServer(port=9090)
        server.start()
        result = server.start()
        assert result is False
        mock_start.assert_called_once()

    @patch("ferrox.metrics.start_http_server")
    def test_is_running_reflects_state(self, mock_start):
        server = MetricsServer(port=9090)
        assert server.is_running() is False
        server.start()
        assert server.is_running() is True


class TestStartMetricsServer:
    @patch("ferrox.metrics.MetricsServer")
    def test_creates_and_starts_server(self, mock_cls):
        mock_instance = MagicMock()
        mock_instance.start.return_value = True
        mock_cls.return_value = mock_instance

        result = start_metrics_server(port=9090)
        assert result is True
        mock_cls.assert_called_once_with(9090)

    @patch.dict("os.environ", {"PROMETHEUS_PORT": "9091"})
    @patch("ferrox.metrics._metrics_server", None)
    @patch("ferrox.metrics.MetricsServer")
    def test_uses_env_port(self, mock_cls):
        mock_instance = MagicMock()
        mock_instance.start.return_value = True
        mock_cls.return_value = mock_instance

        start_metrics_server()
        mock_cls.assert_called_once_with(9091)


class TestIncrementFunctions:
    @patch("ferrox.metrics.agent_requests_total")
    def test_increment_agent_requests(self, mock_counter):
        increment_agent_requests("openai", "gpt-4o", "success")
        mock_counter.labels.assert_called_once_with(
            provider="openai", model="gpt-4o", status="success"
        )
        mock_counter.labels.return_value.inc.assert_called_once()

    @patch("ferrox.metrics.tool_calls_total")
    def test_increment_tool_calls(self, mock_counter):
        increment_tool_calls("read_file", "success")
        mock_counter.labels.assert_called_once_with(tool_name="read_file", status="success")
        mock_counter.labels.return_value.inc.assert_called_once()

    @patch("ferrox.metrics.errors_total")
    def test_increment_errors(self, mock_counter):
        increment_errors("timeout", "api")
        mock_counter.labels.assert_called_once_with(error_type="timeout", component="api")
        mock_counter.labels.return_value.inc.assert_called_once()

    @patch("ferrox.metrics.fallback_attempts_total")
    def test_increment_fallback_attempts(self, mock_counter):
        increment_fallback_attempts("openai", "ollama")
        mock_counter.labels.assert_called_once_with(from_provider="openai", to_provider="ollama")
        mock_counter.labels.return_value.inc.assert_called_once()

    @patch("ferrox.metrics.tokens_used_total")
    def test_increment_tokens_used(self, mock_counter):
        increment_tokens_used("openai", "gpt-4o", 100)
        mock_counter.labels.assert_called_once_with(provider="openai", model="gpt-4o")
        mock_counter.labels.return_value.inc.assert_called_once_with(100)

    @patch("ferrox.metrics.active_sessions")
    def test_increment_active_sessions(self, mock_gauge):
        increment_active_sessions()
        mock_gauge.inc.assert_called_once()

    @patch("ferrox.metrics.active_sessions")
    def test_decrement_active_sessions(self, mock_gauge):
        decrement_active_sessions()
        mock_gauge.dec.assert_called_once()


class TestRecordFunctions:
    @patch("ferrox.metrics.agent_request_duration")
    def test_record_agent_request_duration(self, mock_histogram):
        record_agent_request_duration("openai", "gpt-4o", 1.5)
        mock_histogram.labels.assert_called_once_with(provider="openai", model="gpt-4o")
        mock_histogram.labels.return_value.observe.assert_called_once_with(1.5)

    @patch("ferrox.metrics.tool_call_duration")
    def test_record_tool_call_duration(self, mock_histogram):
        record_tool_call_duration("read_file", 0.5)
        mock_histogram.labels.assert_called_once_with(tool_name="read_file")
        mock_histogram.labels.return_value.observe.assert_called_once_with(0.5)
