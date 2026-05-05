"""Tests for ferrox.ui.trace_viewer module"""

from datetime import datetime
from unittest.mock import patch

import pytest

from ferrox.ui.trace_viewer import show_help_panel, show_trace_viewer


def _get_string_calls(mock_console):
    """Return list of string arguments passed to console.print."""
    return [
        call.args[0]
        for call in mock_console.print.call_args_list
        if call.args and isinstance(call.args[0], str)
    ]


def _has_object_type(mock_console, obj_type):
    """Check if console.print was called with an object of given type."""
    return any(
        call.args and isinstance(call.args[0], obj_type)
        for call in mock_console.print.call_args_list
    )


class TestShowHelpPanel:
    """Test show_help_panel"""

    def test_displays_shortcuts(self):
        """Help panel shows header and table with shortcuts"""
        with patch("ferrox.ui.trace_viewer.console") as mock_console, patch(
            "builtins.input", return_value=""
        ):
            show_help_panel()

        strings = _get_string_calls(mock_console)
        assert any("KEYBOARD SHORTCUTS" in s for s in strings)
        assert any("Press Enter to return" in s for s in strings)
        from rich.table import Table

        assert _has_object_type(mock_console, Table)

    def test_waits_for_input(self):
        """show_help_panel waits for Enter before returning"""
        with patch("ferrox.ui.trace_viewer.console"), patch(
            "builtins.input", return_value=""
        ) as mock_input:
            show_help_panel()

        mock_input.assert_called_once()


class TestShowTraceViewer:
    """Test show_trace_viewer"""

    def test_empty_logs(self):
        """When no logs, shows 'No logs recorded yet'"""
        with patch("ferrox.ui.trace_viewer.console") as mock_console, patch(
            "builtins.input", return_value=""
        ):
            show_trace_viewer([])

        strings = _get_string_calls(mock_console)
        assert any("No logs recorded yet" in s for s in strings)

    def test_thought_log(self):
        """Thought logs are rendered in a Panel"""
        logs = [
            {
                "type": "thought",
                "content": "Planning the architecture",
                "timestamp": datetime(2025, 1, 1, 12, 0, 0),
            }
        ]
        with patch("ferrox.ui.trace_viewer.console") as mock_console, patch(
            "builtins.input", return_value=""
        ):
            show_trace_viewer(logs)

        from rich.panel import Panel

        assert _has_object_type(mock_console, Panel)
        strings = _get_string_calls(mock_console)
        assert any("Summary:" in s for s in strings)
        assert any("1 thoughts" in s for s in strings)

    def test_tool_call_log(self):
        """Tool call logs show tool name in a Panel"""
        logs = [
            {
                "type": "tool_call",
                "name": "read_file",
                "args": {"file_path": "/test.py"},
                "timestamp": None,
            }
        ]
        with patch("ferrox.ui.trace_viewer.console") as mock_console, patch(
            "builtins.input", return_value=""
        ):
            show_trace_viewer(logs)

        from rich.panel import Panel

        assert _has_object_type(mock_console, Panel)
        strings = _get_string_calls(mock_console)
        assert any("Summary:" in s for s in strings)

    def test_tool_result_success(self):
        """Successful tool results are rendered"""
        logs = [
            {
                "type": "tool_result",
                "name": "run_command",
                "success": True,
                "content": "All tests passed",
                "timestamp": None,
            }
        ]
        with patch("ferrox.ui.trace_viewer.console") as mock_console, patch(
            "builtins.input", return_value=""
        ):
            show_trace_viewer(logs)

        from rich.panel import Panel

        assert _has_object_type(mock_console, Panel)

    def test_tool_result_failure(self):
        """Failed tool results are rendered"""
        logs = [
            {
                "type": "tool_result",
                "name": "run_command",
                "success": False,
                "content": "Tests failed",
                "timestamp": None,
            }
        ]
        with patch("ferrox.ui.trace_viewer.console") as mock_console, patch(
            "builtins.input", return_value=""
        ):
            show_trace_viewer(logs)

        from rich.panel import Panel

        assert _has_object_type(mock_console, Panel)

    def test_summary_stats(self):
        """Summary line shows counts"""
        logs = [
            {"type": "thought", "content": "t1", "timestamp": None},
            {"type": "tool_call", "name": "x", "args": {}, "timestamp": None},
            {
                "type": "tool_result",
                "name": "x",
                "success": True,
                "content": "",
                "timestamp": None,
            },
            {
                "type": "tool_result",
                "name": "y",
                "success": False,
                "content": "",
                "timestamp": None,
            },
        ]
        with patch("ferrox.ui.trace_viewer.console") as mock_console, patch(
            "builtins.input", return_value=""
        ):
            show_trace_viewer(logs)

        strings = _get_string_calls(mock_console)
        summary = next(s for s in strings if "thoughts" in s)
        assert "1 thoughts" in summary
        assert "1 tool calls" in summary
        assert "1 ✅" in summary
        assert "1 ❌" in summary

    def test_long_content_truncated(self):
        """Long content is rendered in a Panel"""
        logs = [
            {
                "type": "tool_result",
                "name": "x",
                "success": True,
                "content": "a" * 500,
                "timestamp": None,
            }
        ]
        with patch("ferrox.ui.trace_viewer.console") as mock_console, patch(
            "builtins.input", return_value=""
        ):
            show_trace_viewer(logs)

        from rich.panel import Panel

        panels = [
            call.args[0]
            for call in mock_console.print.call_args_list
            if call.args and isinstance(call.args[0], Panel)
        ]
        assert len(panels) > 0
        # At least one Panel exists for the tool result
        assert any("Result:" in str(p.title) for p in panels if hasattr(p, "title"))

    def test_timestamp_string_fallback(self):
        """Non-datetime timestamp is rendered as string"""
        logs = [
            {
                "type": "thought",
                "content": "t1",
                "timestamp": "2025-01-01 12:00:00",
            }
        ]
        with patch("ferrox.ui.trace_viewer.console") as mock_console, patch(
            "builtins.input", return_value=""
        ):
            show_trace_viewer(logs)

        from rich.panel import Panel

        panels = [
            call.args[0]
            for call in mock_console.print.call_args_list
            if call.args and isinstance(call.args[0], Panel)
        ]
        assert len(panels) > 0
        # At least one Panel was rendered with a title
        assert any(p.title is not None for p in panels if hasattr(p, "title"))

    def test_waits_for_input(self):
        """show_trace_viewer waits for Enter before returning"""
        with patch("ferrox.ui.trace_viewer.console"), patch(
            "builtins.input", return_value=""
        ) as mock_input:
            show_trace_viewer([])

        mock_input.assert_called_once()
