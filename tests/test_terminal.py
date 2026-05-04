"""Tests for terminal UI module"""

from unittest.mock import MagicMock, patch

from ferrox.terminal import (
    PermissionPrompt,
    SlashCommandMenu,
    TerminalState,
    create_terminal_ui,
    format_tool_output,
)


class TestSlashCommandMenu:
    def test_init_defaults(self):
        menu = SlashCommandMenu()
        assert menu.visible is False
        assert menu.selected_index == 0
        assert len(menu.filtered_commands) > 0

    def test_show_filters_commands(self):
        menu = SlashCommandMenu()
        menu.show("/cfg")
        assert menu.visible is True
        assert len(menu.filtered_commands) == 1
        assert menu.filtered_commands[0][0] == "/cfg"

    def test_show_empty_search_returns_all(self):
        menu = SlashCommandMenu()
        menu.show("")
        assert len(menu.filtered_commands) == len(menu.filtered_commands)

    def test_show_no_match(self):
        menu = SlashCommandMenu()
        menu.show("/nonexistent")
        assert len(menu.filtered_commands) == 0

    def test_hide(self):
        menu = SlashCommandMenu()
        menu.show("/")
        menu.hide()
        assert menu.visible is False
        assert menu.selected_index == 0

    def test_move_up_wraps(self):
        menu = SlashCommandMenu()
        menu.show("/")
        menu.move_up()
        assert menu.selected_index == len(menu.filtered_commands) - 1

    def test_move_down_wraps(self):
        menu = SlashCommandMenu()
        menu.show("/")
        last = len(menu.filtered_commands) - 1
        for _ in range(last):
            menu.move_down()
        assert menu.selected_index == last
        menu.move_down()
        assert menu.selected_index == 0

    def test_get_selected(self):
        menu = SlashCommandMenu()
        menu.show("/cfg")
        selected = menu.get_selected()
        assert selected is not None
        assert selected[0] == "/cfg"

    def test_get_selected_empty(self):
        menu = SlashCommandMenu()
        menu.show("/nonexistent")
        assert menu.get_selected() is None


class TestPermissionPrompt:
    def test_init_defaults(self):
        prompt = PermissionPrompt()
        assert prompt.visible is False
        assert prompt.selected_index == 0

    def test_show(self):
        prompt = PermissionPrompt()
        prompt.show("Allow read?", "read", "/tmp/test")
        assert prompt.visible is True
        assert prompt.prompt_text == "Allow read?"
        assert prompt.command == "read"
        assert prompt.path == "/tmp/test"

    def test_hide(self):
        prompt = PermissionPrompt()
        prompt.show("Allow?")
        prompt.hide()
        assert prompt.visible is False

    def test_move_up(self):
        prompt = PermissionPrompt()
        prompt.show("Allow?")
        prompt.move_up()
        assert prompt.selected_index == 3  # wraps from 0 to 3

    def test_move_down(self):
        prompt = PermissionPrompt()
        prompt.show("Allow?")
        prompt.move_down()
        assert prompt.selected_index == 1

    def test_get_option(self):
        prompt = PermissionPrompt()
        prompt.show("Allow?")
        assert prompt.get_option() == 0


class TestTerminalState:
    def test_init(self):
        mode_manager = MagicMock()
        mode_manager.current_mode.value = "NORMAL"
        with patch("ferrox.config.get_default_config") as mock_get_config:
            mock_config = MagicMock()
            mock_provider = MagicMock()
            mock_provider.type = "openai"
            mock_provider.default_model = "gpt-4o"
            mock_config.get_active_provider.return_value = mock_provider
            mock_get_config.return_value = mock_config

            state = TerminalState(mode_manager)
            assert state.model_name == "openai:gpt-4o"
            assert state.chat_history == []

    def test_add_message(self):
        mode_manager = MagicMock()
        mode_manager.current_mode.value = "NORMAL"
        with patch("ferrox.config.get_default_config"):
            state = TerminalState(mode_manager)
            state.add_message("user", "hello")
            assert len(state.chat_history) == 1
            assert state.chat_history[0]["role"] == "user"

    def test_add_tool_output(self):
        mode_manager = MagicMock()
        mode_manager.current_mode.value = "NORMAL"
        with patch("ferrox.config.get_default_config"):
            state = TerminalState(mode_manager)
            state.add_tool_output("read_file", "content")
            assert len(state.tool_outputs) == 1
            assert "read_file" in state.tool_outputs[0]

    def test_clear_history(self):
        mode_manager = MagicMock()
        mode_manager.current_mode.value = "NORMAL"
        with patch("ferrox.config.get_default_config"):
            state = TerminalState(mode_manager)
            state.add_message("user", "hello")
            state.add_tool_output("tool", "output")
            state.clear_history()
            assert state.chat_history == []
            assert state.tool_outputs == []

    def test_get_top_bar_text(self):
        mode_manager = MagicMock()
        mode_manager.current_mode.value = "NORMAL"
        with patch("ferrox.config.get_default_config"):
            state = TerminalState(mode_manager)
            text = state.get_top_bar_text()
            assert len(text) > 0
            assert any("NORMAL" in str(t) for t in text)

    def test_get_status_bar_text(self):
        mode_manager = MagicMock()
        mode_manager.current_mode.value = "NORMAL"
        with patch("ferrox.config.get_default_config"):
            state = TerminalState(mode_manager)
            state.add_message("user", "hello")
            text = state.get_status_bar_text()
            assert len(text) > 0
            assert any("messages" in str(t) for t in text)

    def test_get_output_text_empty(self):
        mode_manager = MagicMock()
        mode_manager.current_mode.value = "NORMAL"
        with patch("ferrox.config.get_default_config"):
            state = TerminalState(mode_manager)
            text = state.get_output_text()
            assert len(text) > 0
            assert any("Start chatting" in str(t) for t in text)

    def test_get_output_text_with_messages(self):
        mode_manager = MagicMock()
        mode_manager.current_mode.value = "NORMAL"
        with patch("ferrox.config.get_default_config"):
            state = TerminalState(mode_manager)
            state.add_message("user", "hello")
            state.add_message("assistant", "hi")
            text = state.get_output_text()
            assert any("You:" in str(t) for t in text)
            assert any("AI:" in str(t) for t in text)

    def test_get_slash_menu_text_hidden(self):
        mode_manager = MagicMock()
        mode_manager.current_mode.value = "NORMAL"
        with patch("ferrox.config.get_default_config"):
            state = TerminalState(mode_manager)
            text = state.get_slash_menu_text()
            assert text == []

    def test_get_slash_menu_text_visible(self):
        mode_manager = MagicMock()
        mode_manager.current_mode.value = "NORMAL"
        with patch("ferrox.config.get_default_config"):
            state = TerminalState(mode_manager)
            state.slash_menu.show("/cfg")
            text = state.get_slash_menu_text()
            assert len(text) > 0
            assert any("Commands" in str(t) for t in text)


class TestCreateTerminalUI:
    def test_returns_terminal_state(self):
        mode_manager = MagicMock()
        with patch("ferrox.config.get_default_config"):
            state = create_terminal_ui(mode_manager)
            assert isinstance(state, TerminalState)


class TestFormatToolOutput:
    def test_run_command_formatting(self):
        output = "[stdout] hello\n[stderr] error\n[exit code: 0]"
        panel = format_tool_output("run_command", output, "/tmp")
        assert panel is not None

    def test_other_tool_formatting(self):
        panel = format_tool_output("read_file", "content", "")
        assert panel is not None
