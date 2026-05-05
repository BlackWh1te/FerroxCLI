"""Tests for ferrox.ui.tool_logger module"""

from unittest.mock import MagicMock, patch

import pytest

from ferrox.ui.tool_logger import log_tool_execution


class TestLogToolExecution:
    """Test log_tool_execution for various tools"""

    @pytest.fixture
    def mock_console(self):
        with patch("ferrox.ui.tool_logger.console") as mock:
            yield mock

    def test_read_file_full(self, mock_console):
        """Read entire file logs correct summary"""
        log_tool_execution(
            "read_file",
            {"file_path": "/test.py", "lines_read": (1, 50), "total_lines": 50},
        )
        mock_console.print.assert_called_once()
        text = mock_console.print.call_args[0][0]
        assert "ReadFile" in str(text)
        assert "/test.py" in str(text)
        assert "50 lines" in str(text)

    def test_read_file_partial(self, mock_console):
        """Read partial file logs line range"""
        log_tool_execution(
            "read_file",
            {"file_path": "/test.py", "lines_read": (10, 20), "total_lines": 50},
        )
        text = mock_console.print.call_args[0][0]
        assert "lines 10-20 of 50" in str(text)

    def test_search_text_with_matches(self, mock_console):
        """Search with matches logs count"""
        log_tool_execution(
            "search_text",
            {"query": "foo", "file_path": "/test.py", "matches": [1, 2, 3]},
        )
        text = mock_console.print.call_args[0][0]
        assert "SearchText" in str(text)
        assert "3 match" in str(text)

    def test_search_text_no_matches(self, mock_console):
        """Search with no matches logs 'No matches found'"""
        log_tool_execution(
            "search_text",
            {"query": "bar", "file_path": "/test.py", "matches": []},
        )
        text = mock_console.print.call_args[0][0]
        assert "No matches found" in str(text)

    def test_edit_file_accepted(self, mock_console):
        """Accepted edit shows green checkmark"""
        log_tool_execution(
            "edit_file",
            {
                "file_path": "/test.py",
                "additions": 5,
                "deletions": 2,
                "accepted": True,
            },
        )
        text = mock_console.print.call_args[0][0]
        assert "Accepted" in str(text)
        assert "+5, -2" in str(text)

    def test_edit_file_rejected(self, mock_console):
        """Rejected edit shows red cross"""
        log_tool_execution(
            "edit_file",
            {
                "file_path": "/test.py",
                "additions": 0,
                "deletions": 0,
                "accepted": False,
            },
        )
        text = mock_console.print.call_args[0][0]
        assert "Rejected" in str(text)

    def test_run_command_success(self, mock_console):
        """Successful command shows green checkmark"""
        log_tool_execution(
            "run_command",
            {"command": "pytest", "exit_code": 0, "working_dir": "/proj"},
        )
        text = mock_console.print.call_args[0][0]
        assert "Success" in str(text)
        assert "pytest" in str(text)
        assert "/proj" in str(text)

    def test_run_command_failure(self, mock_console):
        """Failed command shows red cross and exit code"""
        log_tool_execution(
            "run_command",
            {"command": "badcmd", "exit_code": 1, "working_dir": "/proj"},
        )
        text = mock_console.print.call_args[0][0]
        assert "Failed" in str(text)
        assert "exit code 1" in str(text)

    def test_unknown_tool(self, mock_console):
        """Unknown tool prints generic dim message"""
        log_tool_execution("custom_tool", {"summary": "Custom result"})
        text = mock_console.print.call_args[0][0]
        assert "custom_tool" in str(text)
        assert "Custom result" in str(text)

    def test_unknown_tool_no_summary(self, mock_console):
        """Unknown tool without summary prints 'Executed'"""
        log_tool_execution("custom_tool", {})
        text = mock_console.print.call_args[0][0]
        assert "Executed" in str(text)
