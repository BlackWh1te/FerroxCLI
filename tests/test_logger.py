"""Tests for ferrox logger module"""

import logging
from unittest.mock import MagicMock, patch

from ferrox.logger import (
    get_logger,
    log_fallback,
    log_mode_change,
    log_permission,
    log_provider_validation,
    log_request,
    log_tool_execution,
    setup_logger,
)


class TestSetupLogger:
    def test_creates_logger_with_correct_name(self, tmp_path):
        with patch("ferrox.logger.DEBUG_LOG_FILE", tmp_path / "debug.log"):
            logger = setup_logger(verbose=False)
            assert isinstance(logger, logging.Logger)
            assert logger.name == "ferrox"
            # Should have at least one handler (file)
            assert len(logger.handlers) >= 1

    def test_verbose_adds_console_handler(self, tmp_path):
        with patch("ferrox.logger.DEBUG_LOG_FILE", tmp_path / "debug.log"):
            logger = setup_logger(verbose=True)
            handler_types = [type(h) for h in logger.handlers]
            assert logging.StreamHandler in handler_types
            assert logging.FileHandler in handler_types

    def test_clears_existing_handlers(self, tmp_path):
        with patch("ferrox.logger.DEBUG_LOG_FILE", tmp_path / "debug.log"):
            logger = setup_logger(verbose=False)
            handler_count = len(logger.handlers)
            # Second call should clear and re-add
            logger2 = setup_logger(verbose=False)
            assert len(logger2.handlers) == handler_count


class TestLogRequest:
    def test_logs_success(self):
        mock_logger = MagicMock()
        log_request(
            mock_logger,
            request_id=1,
            provider_name="openai",
            model="gpt-4o",
            base_url="https://api.openai.com",
            tokens_in=100,
            tokens_out=50,
            success=True,
        )
        mock_logger.info.assert_called_once()
        msg = mock_logger.info.call_args[0][0]
        assert "openai" in msg
        assert "gpt-4o" in msg
        assert "OK" in msg

    def test_logs_failure_with_error(self):
        mock_logger = MagicMock()
        log_request(
            mock_logger,
            request_id=2,
            provider_name="ollama",
            model="llama3.2",
            base_url="http://localhost:11434",
            success=False,
            error="Connection refused",
        )
        mock_logger.error.assert_called_once()
        msg = mock_logger.error.call_args[0][0]
        assert "FAILED" in msg
        assert "Connection refused" in msg


class TestLogToolExecution:
    def test_logs_success(self):
        mock_logger = MagicMock()
        log_tool_execution(
            mock_logger,
            tool_name="read_file",
            args={"file_path": "test.py"},
            success=True,
            result="content here",
        )
        mock_logger.debug.assert_called_once()
        msg = mock_logger.debug.call_args[0][0]
        assert "read_file" in msg
        assert "OK" in msg

    def test_logs_failure(self):
        mock_logger = MagicMock()
        log_tool_execution(
            mock_logger,
            tool_name="run_command",
            args={"command": "ls"},
            success=False,
            error="Permission denied",
        )
        mock_logger.warning.assert_called_once()
        msg = mock_logger.warning.call_args[0][0]
        assert "FAILED" in msg


class TestLogFallback:
    def test_logs_fallback(self):
        mock_logger = MagicMock()
        log_fallback(mock_logger, "gpt-4o", "llama3.2", "Rate limit")
        mock_logger.info.assert_called_once()
        msg = mock_logger.info.call_args[0][0]
        assert "FALLBACK" in msg
        assert "gpt-4o -> llama3.2" in msg


class TestLogProviderValidation:
    def test_valid_provider(self):
        mock_logger = MagicMock()
        log_provider_validation(
            mock_logger, "openai", "https://api.openai.com", success=True, models_count=5
        )
        mock_logger.info.assert_called_once()
        msg = mock_logger.info.call_args[0][0]
        assert "VALID" in msg
        assert "5" in msg

    def test_invalid_provider(self):
        mock_logger = MagicMock()
        log_provider_validation(
            mock_logger, "ollama", "http://localhost:11434", success=False, error="Timeout"
        )
        mock_logger.warning.assert_called_once()
        msg = mock_logger.warning.call_args[0][0]
        assert "INVALID" in msg
        assert "Timeout" in msg


class TestLogPermission:
    def test_granted(self):
        mock_logger = MagicMock()
        log_permission(mock_logger, "read", "/tmp/test", True, "NORMAL")
        mock_logger.info.assert_called_once()
        msg = mock_logger.info.call_args[0][0]
        assert "GRANTED" in msg
        assert "NORMAL" in msg

    def test_denied(self):
        mock_logger = MagicMock()
        log_permission(mock_logger, "write", "/etc/passwd", False, "PLAN")
        mock_logger.info.assert_called_once()
        msg = mock_logger.info.call_args[0][0]
        assert "DENIED" in msg


class TestLogModeChange:
    def test_logs_mode_change(self):
        mock_logger = MagicMock()
        log_mode_change(mock_logger, "NORMAL", "PLAN")
        mock_logger.info.assert_called_once()
        msg = mock_logger.info.call_args[0][0]
        assert "NORMAL -> PLAN" in msg


class TestGetLogger:
    def test_creates_on_first_call(self):
        with patch("ferrox.logger._logger", None), patch(
            "ferrox.logger.setup_logger"
        ) as mock_setup:
            mock_setup.return_value = MagicMock()
            logger = get_logger()
            mock_setup.assert_called_once_with(False)
            assert logger is not None

    def test_returns_existing(self):
        mock_logger = MagicMock()
        with patch("ferrox.logger._logger", mock_logger), patch(
            "ferrox.logger.setup_logger"
        ) as mock_setup:
            logger1 = get_logger()
            logger2 = get_logger()
            # setup_logger should NOT be called when logger already exists
            mock_setup.assert_not_called()
            assert logger1 == logger2
