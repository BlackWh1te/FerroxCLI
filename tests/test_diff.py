"""Tests for diff viewer module"""

from unittest.mock import MagicMock, patch

import pytest
from rich.panel import Panel

from ferrox.diff import (
    apply_file_edit,
    generate_diff,
    prompt_accept_reject,
    render_diff_inline,
    render_diff_side_by_side,
    show_diff_and_prompt,
)


class TestGenerateDiff:
    def test_empty_content(self):
        diff = generate_diff("", "", "test.py")
        assert isinstance(diff, list)

    def test_no_changes(self):
        content = "line1\nline2"
        diff = generate_diff(content, content, "test.py")
        # unified_diff with no changes still produces headers
        assert all("---" in line or "+++" in line or "@@" in line for line in diff)

    def test_addition(self):
        original = "line1"
        new = "line1\nline2"
        diff = generate_diff(original, new, "test.py")
        assert any(line.startswith("+") and "line2" in line for line in diff)

    def test_deletion(self):
        original = "line1\nline2"
        new = "line1"
        diff = generate_diff(original, new, "test.py")
        assert any(line.startswith("-") and "line2" in line for line in diff)

    def test_modification(self):
        original = "old line"
        new = "new line"
        diff = generate_diff(original, new, "test.py")
        assert len(diff) > 0
        assert "original/test.py" in str(diff)
        assert "modified/test.py" in str(diff)


class TestRenderDiffInline:
    def test_returns_panel(self):
        result = render_diff_inline("a\nb", "a\nc", "test.py")
        assert isinstance(result, Panel)
        assert "test.py" in str(result.title)

    def test_empty_diff(self):
        result = render_diff_inline("same", "same", "test.py")
        assert isinstance(result, Panel)

    def test_with_additions(self):
        result = render_diff_inline("a", "a\nb", "test.py")
        assert isinstance(result, Panel)

    def test_with_deletions(self):
        result = render_diff_inline("a\nb", "a", "test.py")
        assert isinstance(result, Panel)


class TestRenderDiffSideBySide:
    def test_returns_panel(self):
        result = render_diff_side_by_side("a", "b", "test.py")
        assert isinstance(result, Panel)

    def test_empty_content(self):
        result = render_diff_side_by_side("", "", "test.py")
        assert isinstance(result, Panel)

    def test_equal_content(self):
        result = render_diff_side_by_side("same\ncontent", "same\ncontent", "test.py")
        assert isinstance(result, Panel)

    def test_insert_only(self):
        result = render_diff_side_by_side("a", "a\nb\nc", "test.py")
        assert isinstance(result, Panel)

    def test_delete_only(self):
        result = render_diff_side_by_side("a\nb", "a", "test.py")
        assert isinstance(result, Panel)

    def test_replace(self):
        result = render_diff_side_by_side("old", "new", "test.py")
        assert isinstance(result, Panel)


class TestPromptAcceptReject:
    @pytest.mark.skipif(
        not hasattr(__import__("sys").stdin, "isatty") or __import__("os").name == "nt",
        reason="termios/tty not available on Windows",
    )
    @patch("sys.stdin")
    @patch("sys.stdin.isatty")
    def test_tty_accept_enter(self, mock_isatty, mock_stdin):
        mock_isatty.return_value = True

        with (
            patch("termios.tcgetattr", return_value=None),
            patch("tty.setcbreak"),
            patch("termios.tcsetattr"),
            patch.object(mock_stdin, "read", return_value="\r"),
        ):
            result = prompt_accept_reject("test.py")
            assert result is True

    @pytest.mark.skipif(
        not hasattr(__import__("sys").stdin, "isatty") or __import__("os").name == "nt",
        reason="termios/tty not available on Windows",
    )
    @patch("sys.stdin.isatty")
    def test_tty_reject_esc(self, mock_isatty):
        mock_isatty.return_value = True

        with (
            patch("termios.tcgetattr", return_value=None),
            patch("tty.setcbreak"),
            patch("termios.tcsetattr"),
            patch("sys.stdin.read", return_value="\x1b"),
        ):
            result = prompt_accept_reject("test.py")
            assert result is False

    @pytest.mark.skipif(
        not hasattr(__import__("sys").stdin, "isatty") or __import__("os").name == "nt",
        reason="termios/tty not available on Windows",
    )
    @patch("sys.stdin.isatty")
    def test_tty_edit(self, mock_isatty):
        mock_isatty.return_value = True

        with (
            patch("termios.tcgetattr", return_value=None),
            patch("tty.setcbreak"),
            patch("termios.tcsetattr"),
            patch("sys.stdin.read", return_value="e"),
        ):
            result = prompt_accept_reject("test.py")
            assert result == "edit"

    @patch("sys.stdin.isatty")
    def test_not_tty_defaults_accept(self, mock_isatty):
        mock_isatty.return_value = False
        with patch("builtins.input", return_value=""):
            result = prompt_accept_reject("test.py")
            assert result is True

    @patch("sys.stdin.isatty")
    def test_input_no(self, mock_isatty):
        mock_isatty.return_value = False
        with patch("builtins.input", return_value="n"):
            result = prompt_accept_reject("test.py")
            assert result is False

    @patch("sys.stdin.isatty")
    def test_input_edit(self, mock_isatty):
        mock_isatty.return_value = False
        with patch("builtins.input", return_value="e"):
            result = prompt_accept_reject("test.py")
            assert result == "edit"


class TestShowDiffAndPrompt:
    @patch("ferrox.diff.render_diff_inline")
    @patch("ferrox.diff.prompt_accept_reject")
    def test_accepted(self, mock_prompt, mock_render):
        mock_panel = MagicMock()
        mock_render.return_value = mock_panel
        mock_prompt.return_value = True

        with patch("ferrox.diff.console"):
            accepted, edited = show_diff_and_prompt("a", "b", "test.py")
            assert accepted is True
            assert edited is None

    @patch("ferrox.diff.render_diff_inline")
    @patch("ferrox.diff.prompt_accept_reject")
    def test_rejected(self, mock_prompt, mock_render):
        mock_panel = MagicMock()
        mock_render.return_value = mock_panel
        mock_prompt.return_value = False

        with patch("ferrox.diff.console"):
            accepted, edited = show_diff_and_prompt("a", "b", "test.py")
            assert accepted is False
            assert edited is None

    @patch("ferrox.diff.render_diff_inline")
    @patch("ferrox.diff.prompt_accept_reject")
    def test_edit(self, mock_prompt, mock_render):
        mock_panel = MagicMock()
        mock_render.return_value = mock_panel
        mock_prompt.return_value = "edit"

        with patch("ferrox.diff.console"):
            accepted, edited = show_diff_and_prompt("a", "b", "test.py")
            assert accepted is False
            assert edited == "edit"


class TestApplyFileEdit:
    def test_success(self, tmp_path):
        test_file = tmp_path / "test.py"
        result = apply_file_edit(str(test_file), "new content")
        assert "Successfully updated" in result
        assert test_file.exists()
        assert test_file.read_text(encoding="utf-8") == "new content"

    def test_creates_directories(self, tmp_path):
        test_file = tmp_path / "nested" / "dir" / "test.py"
        result = apply_file_edit(str(test_file), "content")
        assert "Successfully updated" in result
        assert test_file.exists()

    def test_error_on_invalid_path(self):
        # Path with null byte is invalid on all platforms
        result = apply_file_edit("\x00invalid/path", "content")
        assert "Error writing file" in result
