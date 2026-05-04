"""Tests for status indicators module"""

from unittest.mock import MagicMock, patch

from ferrox.indicators import SimpleStatus, StatusIndicator, get_spinner, status_bar


class TestSimpleStatus:
    @patch("ferrox.indicators.console")
    def test_show_thinking(self, mock_console):
        SimpleStatus.show_thinking()
        mock_console.print.assert_called_once()
        args = mock_console.print.call_args[0]
        assert "thinking" in args[0].lower()

    @patch("ferrox.indicators.console")
    def test_show_running(self, mock_console):
        SimpleStatus.show_running("read_file")
        mock_console.print.assert_called_once()
        args = mock_console.print.call_args[0]
        assert "Running" in args[0]
        assert "read_file" in args[0]

    @patch("ferrox.indicators.console")
    def test_show_fetching(self, mock_console):
        SimpleStatus.show_fetching("https://example.com")
        mock_console.print.assert_called_once()
        args = mock_console.print.call_args[0]
        assert "Fetching" in args[0]

    def test_clear_does_nothing(self):
        # clear() is a no-op
        result = SimpleStatus.clear()
        assert result is None


class TestStatusIndicator:
    def test_init_defaults(self):
        indicator = StatusIndicator()
        assert indicator.state == "thinking"
        assert indicator.prefix == ""
        assert indicator.running is False

    def test_init_custom(self):
        indicator = StatusIndicator(state="fetching", prefix="[test]")
        assert indicator.state == "fetching"
        assert indicator.prefix == "[test]"

    @patch("ferrox.indicators.console")
    def test_start_sets_running(self, mock_console):
        mock_status = MagicMock()
        mock_console.status.return_value = mock_status
        indicator = StatusIndicator()
        indicator.start("Processing...")
        assert indicator.running is True
        assert indicator.message == "Processing..."

    @patch("ferrox.indicators.console")
    def test_start_with_fallback(self, mock_console):
        mock_console.status.side_effect = Exception("No status")
        indicator = StatusIndicator()
        indicator.start("Working...")
        assert indicator.running is True

    @patch("ferrox.indicators.console")
    def test_stop_sets_not_running(self, mock_console):
        mock_status = MagicMock()
        mock_console.status.return_value = mock_status
        indicator = StatusIndicator()
        indicator.start("Working...")
        indicator.stop()
        assert indicator.running is False

    @patch("ferrox.indicators.console")
    def test_stop_when_no_status(self, mock_console):
        indicator = StatusIndicator()
        indicator.running = True
        # Should not raise even without a status object
        indicator.stop()
        assert indicator.running is False

    @patch("ferrox.indicators.console")
    def test_update_message(self, mock_console):
        mock_status = MagicMock()
        mock_console.status.return_value = mock_status
        indicator = StatusIndicator()
        indicator.start("Step 1")
        indicator.update_message("Step 2")
        assert indicator.message == "Step 2"

    @patch("ferrox.indicators.console")
    def test_update_message_without_status(self, mock_console):
        indicator = StatusIndicator()
        # Should not raise
        indicator.update_message("No status")
        assert indicator.message == "No status"


class TestGetSpinner:
    def test_returns_status_indicator(self):
        spinner = get_spinner("fetching", "[prefix]")
        assert isinstance(spinner, StatusIndicator)
        assert spinner.state == "fetching"
        assert spinner.prefix == "[prefix]"


class TestStatusBar:
    def test_is_simple_status(self):
        assert isinstance(status_bar, SimpleStatus)
