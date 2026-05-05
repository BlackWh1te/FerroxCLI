"""Tests for ferrox.monitoring module"""

import pytest
from unittest.mock import MagicMock, patch

from ferrox import __version__
from ferrox.monitoring import (
    add_breadcrumb,
    capture_exception,
    capture_message,
    init_sentry,
    set_tag,
    set_user_context,
)


class TestInitSentry:
    """Test Sentry initialization"""

    def test_no_dsn_returns_false(self, monkeypatch):
        """When no DSN is provided and env var is not set, return False"""
        monkeypatch.delenv("SENTRY_DSN", raising=False)
        assert init_sentry() is False

    def test_with_env_dsn(self, monkeypatch):
        """Uses SENTRY_DSN env var when available"""
        monkeypatch.setenv("SENTRY_DSN", "https://test@sentry.io/1")
        monkeypatch.setenv("SENTRY_ENVIRONMENT", "production")

        with patch("ferrox.monitoring.sentry_sdk.init") as mock_init:
            result = init_sentry()

        assert result is True
        mock_init.assert_called_once()
        call_kwargs = mock_init.call_args.kwargs
        assert call_kwargs["dsn"] == "https://test@sentry.io/1"
        assert call_kwargs["environment"] == "production"
        assert call_kwargs["release"] == __version__

    def test_with_provided_dsn(self):
        """Uses provided DSN parameter over env var"""
        with patch("ferrox.monitoring.sentry_sdk.init") as mock_init:
            result = init_sentry(dsn="https://provided@sentry.io/2")

        assert result is True
        mock_init.assert_called_once()
        assert mock_init.call_args.kwargs["dsn"] == "https://provided@sentry.io/2"

    def test_default_environment(self, monkeypatch):
        """Defaults to 'development' when SENTRY_ENVIRONMENT not set"""
        monkeypatch.setenv("SENTRY_DSN", "https://test@sentry.io/1")
        monkeypatch.delenv("SENTRY_ENVIRONMENT", raising=False)

        with patch("ferrox.monitoring.sentry_sdk.init") as mock_init:
            init_sentry()

        assert mock_init.call_args.kwargs["environment"] == "development"

    def test_init_failure_returns_false(self, monkeypatch):
        """When sentry_sdk.init raises, return False and print warning"""
        monkeypatch.setenv("SENTRY_DSN", "https://test@sentry.io/1")

        with patch("ferrox.monitoring.sentry_sdk.init", side_effect=RuntimeError("boom")):
            with patch("builtins.print") as mock_print:
                result = init_sentry()

        assert result is False
        mock_print.assert_called_once()
        assert "Failed to initialize Sentry" in mock_print.call_args[0][0]

    def test_traces_sample_rate(self, monkeypatch):
        """traces_sample_rate is passed through to sentry init"""
        monkeypatch.setenv("SENTRY_DSN", "https://test@sentry.io/1")

        with patch("ferrox.monitoring.sentry_sdk.init") as mock_init:
            init_sentry(traces_sample_rate=0.5)

        assert mock_init.call_args.kwargs["traces_sample_rate"] == 0.5

    def test_ignores_keyboard_interrupt(self, monkeypatch):
        """KeyboardInterrupt is in the ignore_errors list"""
        monkeypatch.setenv("SENTRY_DSN", "https://test@sentry.io/1")

        with patch("ferrox.monitoring.sentry_sdk.init") as mock_init:
            init_sentry()

        ignore_errors = mock_init.call_args.kwargs.get("ignore_errors", [])
        assert KeyboardInterrupt in ignore_errors

    def test_ferrox_version_env_override(self, monkeypatch):
        """FERROX_VERSION env var overrides __version__"""
        monkeypatch.setenv("SENTRY_DSN", "https://test@sentry.io/1")
        monkeypatch.setenv("FERROX_VERSION", "9.9.9")

        with patch("ferrox.monitoring.sentry_sdk.init") as mock_init:
            init_sentry()

        assert mock_init.call_args.kwargs["release"] == "9.9.9"


class TestCaptureException:
    """Test capture_exception"""

    def test_calls_sentry_capture(self):
        """capture_exception delegates to sentry_sdk"""
        exc = ValueError("test error")

        with patch("ferrox.monitoring.sentry_sdk.capture_exception") as mock_capture:
            capture_exception(exc)

        mock_capture.assert_called_once_with(exc)


class TestCaptureMessage:
    """Test capture_message"""

    def test_default_level(self):
        """Default level is 'info'"""
        with patch("ferrox.monitoring.sentry_sdk.capture_message") as mock_capture:
            capture_message("hello world")

        mock_capture.assert_called_once_with("hello world", level="info")

    def test_custom_level(self):
        """Custom level is passed through"""
        with patch("ferrox.monitoring.sentry_sdk.capture_message") as mock_capture:
            capture_message("alert", level="error")

        mock_capture.assert_called_once_with("alert", level="error")


class TestAddBreadcrumb:
    """Test add_breadcrumb"""

    def test_basic_call(self):
        """add_breadcrumb passes args to sentry_sdk"""
        with patch("ferrox.monitoring.sentry_sdk.add_breadcrumb") as mock_bc:
            add_breadcrumb("user clicked button", category="ui", level="info")

        mock_bc.assert_called_once_with(
            message="user clicked button", category="ui", level="info"
        )

    def test_extra_kwargs(self):
        """Extra kwargs are forwarded"""
        with patch("ferrox.monitoring.sentry_sdk.add_breadcrumb") as mock_bc:
            add_breadcrumb("event", data={"key": "value"})

        mock_bc.assert_called_once_with(
            message="event", category="default", level="info", data={"key": "value"}
        )


class TestSetUserContext:
    """Test set_user_context"""

    def test_basic_call(self):
        """set_user_context wraps user_id in dict and forwards kwargs"""
        with patch("ferrox.monitoring.sentry_sdk.set_user") as mock_set:
            set_user_context("user-123", email="test@example.com")

        mock_set.assert_called_once_with(
            {"id": "user-123", "email": "test@example.com"}
        )


class TestSetTag:
    """Test set_tag"""

    def test_basic_call(self):
        """set_tag delegates to sentry_sdk.set_tag"""
        with patch("ferrox.monitoring.sentry_sdk.set_tag") as mock_tag:
            set_tag("version", "1.2.3")

        mock_tag.assert_called_once_with("version", "1.2.3")
