"""Devin-style terminal UI for Ferrox"""

import os
import platform
import shutil
import subprocess
import tempfile
from typing import Callable, Dict, List, Optional

from prompt_toolkit.buffer import Buffer
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

console = Console()


FERROX_STYLE = Style.from_dict(
    {
        "top-bar": "bg:#1e1e1e #cccccc",
        "top-bar.mode-normal": "#00ff00 bold",
        "top-bar.mode-plan": "#ffff00 bold",
        "top-bar.mode-bypass": "#ff0000 bold",
        "input": "bg:#252525 #ffffff",
        "input.prompt": "#00aaff bold",
        "output": "bg:#1e1e1e #dddddd",
        "output.user": "#00ff00 bold",
        "output.ai": "#00aaff bold",
        "output.system": "#ffff00 bold",
        "output.error": "#ff4444 bold",
        "output.tool": "#aa88ff bold",
        "output.tool-header": "#aa88ff bold",
        "status": "bg:#1e1e1e #666666",
        "status.model": "#00aaff bold",
        "status.info": "#888888",
        "border": "#333333",
        "slash-menu": "bg:#2a2a2a #cccccc",
        "slash-menu.selected": "bg:#00aaff #ffffff",
        "slash-menu.title": "bold #ffffff",
        "slash-menu.item": "#cccccc",
        "slash-menu.desc": "italic #888888",
        "permission-prompt": "bg:#2a2a2a #ffffff",
        "permission-prompt.title": "bold #ffaa00",
        "permission-prompt.option": "#cccccc",
        "permission-prompt.selected": "bg:#00aaff #ffffff",
        "diff.add": "bg:#1a3d1a #4caf50",
        "diff.remove": "bg:#3d1a1a #f44336",
        "diff.header": "italic #888888",
    }
)


COMMANDS = [
    ("/cfg", "Configure provider", "Open config file in editor"),
    ("/model", "Select model", "List and select available models"),
    ("/plan", "Plan mode", "Switch to Plan mode (read-only)"),
    ("/bypass", "Bypass mode", "Switch to Bypass mode (auto-approve)"),
    ("/normal", "Normal mode", "Switch to Normal mode"),
    ("/clear", "Clear chat", "Clear chat history"),
    ("/exit", "Exit", "Exit CLI"),
    ("/help", "Help", "Show all commands"),
]


class SlashCommandMenu:
    """Slash command autocomplete menu"""

    def __init__(self):
        self.visible = False
        self.selected_index = 0
        self.filtered_commands = COMMANDS.copy()
        self.input_text = ""

    def show(self, partial: str):
        self.visible = True
        self.input_text = partial
        self.selected_index = 0

        if partial.startswith("/"):
            search = partial[1:].lower()
            self.filtered_commands = [
                (cmd, desc, help_text)
                for cmd, desc, help_text in COMMANDS
                if cmd.lower().startswith("/" + search)
                or search in cmd.lower()
                or search in desc.lower()
            ]
        else:
            self.filtered_commands = COMMANDS.copy()

    def hide(self):
        self.visible = False
        self.selected_index = 0

    def move_up(self):
        if self.filtered_commands:
            self.selected_index = (self.selected_index - 1) % len(self.filtered_commands)

    def move_down(self):
        if self.filtered_commands:
            self.selected_index = (self.selected_index + 1) % len(self.filtered_commands)

    def get_selected(self) -> Optional[tuple]:
        if self.filtered_commands:
            return self.filtered_commands[self.selected_index]
        return None


class PermissionPrompt:
    """Navigable permission prompt"""

    def __init__(self):
        self.visible = False
        self.selected_index = 0
        self.prompt_text = ""
        self.command = ""
        self.path = ""

    def show(self, prompt: str, command: str = "", path: str = ""):
        self.visible = True
        self.prompt_text = prompt
        self.command = command
        self.path = path
        self.selected_index = 0

    def hide(self):
        self.visible = False
        self.selected_index = 0

    def move_up(self):
        self.selected_index = (self.selected_index - 1) % 4

    def move_down(self):
        self.selected_index = (self.selected_index + 1) % 4

    def get_option(self) -> int:
        return self.selected_index


class TerminalState:
    """Manages terminal state and rendering"""

    def __init__(self, mode_manager, on_submit: Callable = None):
        self.mode_manager = mode_manager
        self.on_submit = on_submit
        self.slash_menu = SlashCommandMenu()
        self.permission_prompt = PermissionPrompt()
        self.chat_history: List[Dict[str, str]] = []
        self.tool_outputs: List[str] = []
        self.input_buffer = Buffer()
        self.model_name = "llama3.2:latest"
        self.context_tokens = 2000
        self.max_tokens = 128000

    def add_message(self, role: str, content: str):
        self.chat_history.append({"role": role, "content": content})

    def add_tool_output(self, tool_name: str, output: str):
        self.tool_outputs.append(f"[{tool_name}]\n{output}")

    def clear_history(self):
        self.chat_history.clear()
        self.tool_outputs.clear()

    def get_top_bar_text(self) -> List:
        mode = self.mode_manager.current_mode
        mode_colors = {"NORMAL": "#00ff00", "PLAN": "#ffff00", "BYPASS": "#ff0000"}
        color = mode_colors.get(mode.value, "#ffffff")

        mode_text = f" {mode.value} "
        if mode.value == "NORMAL":
            mode_text += "(accept edits off)"
        elif mode.value == "PLAN":
            mode_text += "(read-only)"
        elif mode.value == "BYPASS":
            mode_text += "(bypass active)"

        placeholder = "Ask Ferrox to build features, fix bugs, or work on your code"

        return [
            ("class:top-bar", f" > {placeholder}"),
            ("", " " * 20),
            (f"class:top-bar.mode-{mode.value.lower()}", mode_text),
        ]

    def get_status_bar_text(self) -> List:
        percent = int((self.context_tokens / self.max_tokens) * 100)
        return [
            ("class:status.model", self.model_name),
            ("class:status.info", f" · {len(self.chat_history)} messages"),
            (
                "class:status.info",
                f" · Context: {self.context_tokens // 1000}k / {self.max_tokens // 1000}k tokens ({percent}%)",
            ),
        ]

    def get_output_text(self) -> List:
        lines = []

        for msg in self.chat_history:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "user":
                lines.append(("class:output.user", "You: "))
                lines.append(("", content))
            elif role == "assistant":
                lines.append(("class:output.ai", "AI: "))
                lines.append(("", content))
            elif role == "system":
                lines.append(("class:output.system", content))
            elif role == "tool":
                lines.append(("class:output.tool", content))

            lines.append(("", "\n"))

        for tool_output in self.tool_outputs:
            lines.append(("class:output.tool-header", tool_output))
            lines.append(("", "\n"))

        if not lines:
            lines.append(("class:output.system", "Start chatting..."))

        return lines

    def get_slash_menu_text(self) -> List:
        if not self.slash_menu.visible:
            return []

        lines = [("class:slash-menu.title", "Commands"), ("", "\n")]

        for idx, (cmd, desc, help_text) in enumerate(self.slash_menu.filtered_commands):
            prefix = "» " if idx == self.slash_menu.selected_index else "  "
            style = (
                "class:slash-menu.selected"
                if idx == self.slash_menu.selected_index
                else "class:slash-menu.item"
            )
            lines.append((style, f"{prefix}{cmd}"))
            lines.append(("class:slash-menu.desc", f" - {help_text}"))
            lines.append(("", "\n"))

        return lines


def create_terminal_ui(mode_manager, on_submit: Callable = None) -> TerminalState:
    """Create and return terminal state"""
    return TerminalState(mode_manager, on_submit)


def format_tool_output(tool_name: str, output: str, cwd: str = "") -> Panel:
    """Format tool output with appropriate styling"""

    if tool_name == "run_command":
        lines = output.split("\n")
        formatted = []

        for line in lines:
            if "[stdout]" in line or "[stderr]" in line:
                formatted.append("[cyan bold]" + line + "[/cyan bold]")
            elif "[exit code:" in line:
                code = line.split(":")[-1].strip().rstrip("]")
                color = "green" if code == "0" else "red"
                formatted.append(f"[{color} bold]" + line + f"[/{color} bold]")
            else:
                formatted.append(line)

        return Panel(
            "\n".join(formatted),
            title=f"[run_command] {cwd}",
            border_style="purple",
            padding=(0, 1),
        )

    elif tool_name == "list_directory":
        lines = output.split("\n")
        formatted = []
        for line in lines:
            if line.startswith("Contents of"):
                formatted.append("[cyan bold]" + line + "[/cyan bold]")
            elif "📁" in line:
                formatted.append("[yellow]" + line.replace("📁", "[DIR]") + "[/yellow]")
            elif "📄" in line:
                formatted.append("[white]" + line.replace("📄", "[FILE]") + "[/white]")
            else:
                formatted.append(line)

        return Panel(
            "\n".join(formatted), title="[list_directory]", border_style="blue", padding=(0, 1)
        )

    elif tool_name == "read_file":
        lines = output.split("\n", 1)
        header = lines[0] if len(lines) > 1 else output
        content = lines[1] if len(lines) > 1 else ""

        try:
            syntax = Syntax(content, "python", theme="monokai", line_numbers=True)
            return Panel(
                syntax,
                title=f"[read_file] {header.replace('File: ', '')}",
                border_style="green",
                padding=(0, 1),
            )
        except:
            return Panel(
                content[:500] + ("..." if len(content) > 500 else ""),
                title=f"[read_file] {header}",
                border_style="green",
                padding=(0, 1),
            )

    elif tool_name == "write_file":
        return Panel(output, title="[write_file]", border_style="yellow", padding=(0, 1))

    elif tool_name == "web_search":
        lines = output.split("\n")
        formatted = []
        for line in lines:
            if line.startswith("[") and "]" in line:
                formatted.append(f"[bold cyan]{line}[/bold cyan]")
            elif line.startswith("URL:"):
                formatted.append(f"[dim]{line}[/dim]")
            elif line.startswith("Source:"):
                formatted.append(f"[italic]{line}[/italic]")
            else:
                formatted.append(line)

        return Panel(
            "\n".join(formatted), title="[web_search] Results", border_style="cyan", padding=(0, 1)
        )


def display_tool_output(tool_name: str, output: str, cwd: str = ""):
    """Display tool output using Rich"""
    panel = format_tool_output(tool_name, output, cwd)
    console.print(panel)


def display_permission_prompt(prompt: str, command: str = "", path: str = ""):
    """Display permission prompt"""
    console.print(
        Panel.fit(
            f"[yellow bold]Ferrox wants to:[/yellow bold]\n{command or prompt}\n\n"
            "[cyan]Options:[/cyan]\n"
            "  [green]↑↓[/green] Navigate  [green]Enter[/green] Select  [green]Esc[/green] Cancel",
            title="[yellow]Permission Request[/yellow]",
            border_style="yellow",
            padding=(1, 2),
        )
    )


def get_editor_command() -> str:
    return (
        os.environ.get("EDITOR")
        or os.environ.get("VISUAL")
        or (
            "notepad"
            if platform.system() == "Windows"
            else (
                "code"
                if subprocess.call(["where", "code"], stdout=subprocess.DEVNULL) == 0
                else (
                    "vim"
                    if subprocess.call(["which", "vim"], stdout=subprocess.DEVNULL) == 0
                    else "nano"
                )
            )
        )
    )


def open_external_editor(initial_text: str = "") -> Optional[str]:
    editor = get_editor_command()
    fd, temp_path = tempfile.mkstemp(suffix=".txt", prefix="ferrox_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(initial_text)

        console.print(f"[dim]Opening {editor}...[/dim]")
        subprocess.call([editor, temp_path])

        with open(temp_path, encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return None
    finally:
        try:
            os.unlink(temp_path)
        except:
            pass


def _command_exists(cmd: str) -> bool:
    return shutil.which(cmd) is not None
