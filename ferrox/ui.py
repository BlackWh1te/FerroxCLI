"""UI module for terminal interface - Devin-style layout"""

import os
import sys
import tempfile
import subprocess
import platform
import asyncio
from typing import Optional, Callable, List
from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.styles import Style
from prompt_toolkit.layout.containers import HSplit, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.widgets import TextArea, Label
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table


console = Console()

custom_style = Style.from_dict({
    "prompt": "cyan bold",
    "user-input": "green",
    "ai-response": "blue",
    "system": "yellow bold",
    "error": "red bold",
    "success": "green bold",
    "warning": "yellow",
    "mode-normal": "green bold",
    "mode-plan": "yellow bold",
    "mode-bypass": "red bold",
})

devin_style = Style.from_dict({
    "top-toolbar": "bg:#1e1e1e #cccccc",
    "prompt": "#0088ff bold",
    "placeholder": "#666666 italic",
    "mode-normal": "#00ff00 bold",
    "mode-plan": "#ffff00 bold",
    "mode-bypass": "#ff0000 bold",
    "input-field": "bg:#2d2d2d #ffffff",
    "status-footer": "bg:#1e1e1e #aaaaaa",
    "footer-label": "#888888 italic",
    "footer-value": "#cccccc bold",
    "spacer": "bg:#1e1e1e",
    "chat-area": "bg:#1e1e1e #dddddd",
    "border": "#333333",
    "separator": "#444444",
})


def get_status_footer_text(config, session_state):
    """Generates formatted text for the bottom status bar."""
    workspace_path = os.getcwd()
    if len(workspace_path) > 40:
        workspace_path = "..." + workspace_path[-37:]
    
    sandbox_status = "no sandbox"
    
    active_provider = next((p for p in config.providers if p.id == config.active_provider_id), None)
    model_name = active_provider.default_model if active_provider else "none"
    
    # Quota logic
    if active_provider and active_provider.type in ["openai", "anthropic", "custom"]:
        tokens_used = session_state.get("tokens_used", 0)
        tokens_limit = session_state.get("tokens_limit", 200_000)
        percent_used = int((tokens_used / tokens_limit) * 100) if tokens_limit > 0 else 0
        quota_text = f"{percent_used}% used"
    else:
        quota_text = "N/A"
    
    return [
        ("class:footer-label", "workspace "),
        ("class:footer-value", f"({workspace_path})"),
        ("class:spacer", " " * 10),
        ("class:footer-label", "sandbox "),
        ("class:footer-value", sandbox_status),
        ("class:spacer", " " * 10),
        ("class:footer-label", "/model "),
        ("class:footer-value", model_name),
        ("class:spacer", " " * 10),
        ("class:footer-label", "quota "),
        ("class:footer-value", quota_text),
    ]


def create_devin_style_input_layout(config, session_state):
    """Creates the Devin-style layout with input bar and status footer."""
    input_field = TextArea(
        prompt="> ■ ",
        style="class:input-field",
        focusable=True,
        multiline=False,
        wrap_lines=False
    )
    
    status_footer = Window(
        content=FormattedTextControl(lambda: get_status_footer_text(config, session_state)),
        height=1,
        style="class:status-footer"
    )
    
    root_container = HSplit([
        input_field,
        Window(height=1, char="─", style="class:border"),
        status_footer
    ])
    
    return Layout(root_container)


def get_devin_style():
    return devin_style

class FerroxUI:
    """Devin-style terminal UI for Ferrox"""

    def __init__(self, mode_manager, permission_engine, on_submit_callback: Callable = None):
        self.mode_manager = mode_manager
        self.permission_engine = permission_engine
        self.on_submit_callback = on_submit_callback
        self.chat_history: List[str] = []
        self.input_buffer = Buffer()
        self.application: Optional[Application] = None

    def get_top_toolbar_text(self) -> List:
        """Generate top toolbar text with mode indicator"""
        mode = self.mode_manager.current_mode
        mode_colors = {
            "NORMAL": "#00ff00",
            "PLAN": "#ffff00",
            "BYPASS": "#ff0000"
        }
        mode_color = mode_colors.get(mode.value, "#ffffff")

        mode_text = f" {mode.value} "
        if mode.value == "NORMAL":
            mode_text += "(accept edits off)"
        elif mode.value == "PLAN":
            mode_text += "(read-only)"
        elif mode.value == "BYPASS":
            mode_text += "(bypass active)"

        return [
            ("class:prompt", "> "),
            ("class:placeholder", "Ask Ferrox to build features, fix bugs, or work on your code"),
            ("", " " * 20),
            (f"class:mode-{mode.value.lower()}", mode_text)
        ]

    def get_status_bar_text(self) -> List:
        """Generate status bar text"""
        model = "llama3.2:latest"
        tokens_used = "2k"
        tokens_max = "128k"

        return [
            ("class:model-name", model),
            ("class:separator", " · "),
            ("class:subagents", "0 subagents"),
            ("class:separator", " · "),
            ("class:token-usage", f"Context: {tokens_used} / {tokens_max} tokens"),
        ]

    def get_chat_output_text(self) -> List:
        """Generate chat history output"""
        if not self.chat_history:
            return [("", "No messages yet. Start chatting!")]

        lines = []
        for msg in self.chat_history:
            lines.append(("", msg + "\n"))
        return lines

    def create_key_bindings(self) -> KeyBindings:
        """Create key bindings for the application"""
        kb = KeyBindings()

        @kb.add('s-tab')
        def handle_shift_tab(event):
            """Shift+Tab: Cycle modes"""
            new_mode = self.mode_manager.cycle_mode()
            self.update_display()

        @kb.add('c-g')
        def handle_ctrl_g(event):
            """Ctrl+G: Open external editor"""
            initial_text = self.input_buffer.text
            edited_text = open_external_editor(initial_text)
            if edited_text is not None:
                self.input_buffer.text = edited_text
                self.input_buffer.cursor_position = len(edited_text)

        @kb.add('enter')
        def handle_enter(event):
            """Enter: Submit message"""
            text = self.input_buffer.text.strip()
            if text and self.on_submit_callback:
                self.on_submit_callback(text)
                self.input_buffer.text = ""
            self.update_display()

        @kb.add('c-c')
        def handle_ctrl_c(event):
            """Ctrl+C: Exit"""
            event.app.exit()

        @kb.add('c-o')
        def handle_ctrl_o(event):
            """Ctrl+O: Open Trace/Thinking Viewer"""
            event.app.suspend_to_background()
            try:
                from ..agent.orchestrator import get_current_session_logs
                from .trace_viewer import show_trace_viewer
                logs = get_current_session_logs()
                show_trace_viewer(logs)
            finally:
                event.app.resume_from_background()

        @kb.add('c-l')
        def handle_ctrl_l(event):
            """Ctrl+L: Clear screen"""
            event.app.suspend_to_background()
            import os
            os.system('cls' if os.name == 'nt' else 'clear')
            event.app.resume_from_background()

        @kb.add('c-r')
        def handle_ctrl_r(event):
            """Ctrl+R: Refresh/Reset display"""
            self.update_display()

        return kb

    def create_layout(self):
        """Create the Devin-style layout"""
        top_toolbar = Window(
            FormattedTextControl(self.get_top_toolbar_text),
            height=1,
            style="class:top-toolbar"
        )

        input_area = TextArea(
            buffer=self.input_buffer,
            multiline=False,
            wrap_lines=False,
            accept_handler=self.on_enter_pressed,
            style="class:input-area"
        )

        chat_display = Window(
            FormattedTextControl(self.get_chat_output_text),
            style="class:chat-area"
        )

        separator = Window(char="─", height=1, style="class:border")

        status_bar = Window(
            FormattedTextControl(self.get_status_bar_text),
            height=1,
            style="class:status-bar"
        )

        root = HSplit([
            top_toolbar,
            VSplit([
                Window(width=1, char="│", style="class:border"),
                HSplit([
                    chat_display
                ])
            ]),
            separator,
            input_area,
            status_bar
        ])

        return Layout(root)

    def on_enter_pressed(self):
        """Handle enter key press"""
        text = self.input_buffer.text.strip()
        if text and self.on_submit_callback:
            self.on_submit_callback(text)
            self.input_buffer.text = ""
            self.update_display()

    def update_display(self):
        """Update the display after changes"""
        if self.application:
            self.application.layout.update()
            self.application.invalidate()

    def add_message(self, message: str):
        """Add a message to chat history"""
        self.chat_history.append(message)
        self.update_display()

    def run(self):
        """Run the application"""
        try:
            layout = self.create_layout()
            kb = self.create_key_bindings()

            self.application = Application(
                layout=layout,
                style=devin_style,
                full_screen=True,
                key_bindings=kb
            )

            self.application.run()
        except Exception as e:
            print(f"UI Error: {e}")
            return False
        return True


def get_editor_command() -> str:
    """Get default editor from env vars"""
    return os.environ.get('EDITOR') or os.environ.get('VISUAL') or (
        "notepad" if platform.system() == "Windows" else (
            "code" if _command_exists("code") else (
                "vim" if _command_exists("vim") else "nano"
            )
        )
    )


def open_external_editor(initial_text: str = "") -> Optional[str]:
    """Opens system editor with initial text. Returns edited text."""
    editor = get_editor_command()

    fd, temp_path = tempfile.mkstemp(suffix=".txt", prefix="ferrox_input_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(initial_text)

        console.print(f"[dim]Opening {editor}... Edit and save to continue.[/dim]")

        if platform.system() == "Windows":
            subprocess.call([editor, temp_path])
        else:
            subprocess.call([editor, temp_path])

        with open(temp_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        console.print(f"[red]Error opening editor: {e}[/red]")
        return None
    finally:
        try:
            os.unlink(temp_path)
        except Exception:
            pass


def create_keybindings(mode_manager, on_cycle_callback: Optional[Callable] = None) -> KeyBindings:
    """Create key bindings for Shift+Tab (cycle modes) and Ctrl+G (external editor)"""
    kb = KeyBindings()

    @kb.add('s-tab')
    def handle_shift_tab(event):
        """Shift+Tab: Cycle modes"""
        new_mode = mode_manager.cycle_mode()
        console.print(f"\n[bold]Switched to {new_mode.value} mode[/bold]")
        if on_cycle_callback:
            on_cycle_callback(new_mode)
        if event.app:
            event.app.invalidate()

    @kb.add('c-g')
    def handle_ctrl_g(event):
        """Ctrl+G: Open external editor for current input"""
        current_buffer = event.app.current_buffer
        initial_text = current_buffer.text

        edited_text = open_external_editor(initial_text)

        if edited_text is not None:
            current_buffer.text = edited_text
            current_buffer.cursor_position = len(edited_text)

    return kb


def get_prompt_with_mode(mode_manager) -> str:
    """Get prompt string with mode indicator - Devin-style"""
    mode_colors = {
        "NORMAL": "ansigreen",
        "PLAN": "ansiyellow",
        "BYPASS": "ansired"
    }
    color = mode_colors.get(mode_manager.current_mode.value, "white")
    mode_icon = "*" if mode_manager.current_mode.value == "NORMAL" else "o"
    return f"[{color}]{mode_icon} [{mode_manager.current_mode.value}][/{color}] > "


def get_user_input(mode_manager, on_cycle_callback: Optional[Callable] = None) -> Optional[str]:
    """Get user input with mode-aware prompt - falls back to simple input"""
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.styles import Style

        kb = create_keybindings(mode_manager, on_cycle_callback)

        session = PromptSession(
            key_bindings=kb,
            style=custom_style,
            message=get_prompt_with_mode(mode_manager),
        )
        return session.prompt()
    except KeyboardInterrupt:
        return None
    except EOFError:
        return None
    except Exception:
        import sys
        if not sys.stdin.isatty():
            line = sys.stdin.readline()
            if line:
                return line.strip()
            return None
        mode_indicator = f"[{mode_manager.current_mode.value}]"
        print(f"{mode_indicator} > ", end="", flush=True)
        try:
            return sys.stdin.readline().strip() or None
        except:
            return None


def display_welcome() -> None:
    """Display minimal welcome message"""
    console.print(Panel.fit(
        "Ferrox CLI | Cross-platform AI CLI Tool\n"
        "Type your message or use /help for commands.\n\n"
        "[dim]Hotkeys: Shift+Tab (Modes), Ctrl+G (Editor), Esc (Cancel)[/dim]",
        title="Welcome",
        border_style="cyan"
    ))


def display_error(message: str) -> None:
    """Display error message"""
    console.print(f"[red bold]Error:[/red bold] {message}")


def display_success(message: str) -> None:
    """Display success message"""
    console.print(f"[green bold]Success:[/green bold] {message}")


def display_warning(message: str) -> None:
    """Display warning message"""
    console.print(f"[yellow]Warning:[/yellow] {message}")


def display_system(message: str) -> None:
    """Display system message"""
    console.print(f"[yellow bold]System:[/yellow bold] {message}")


def display_mode_change(new_mode: str) -> None:
    """Display mode change notification"""
    colors = {"NORMAL": "green", "PLAN": "yellow", "BYPASS": "red"}
    color = colors.get(new_mode, "white")
    console.print(f"\n[{color} bold]Mode: {new_mode}[/{color} bold]\n")


def display_message(role: str, content: str) -> None:
    """Display a chat message with formatting"""
    if role == "user":
        console.print(f"[green]You:[/green]")
        console.print(content)
    elif role == "assistant":
        console.print(f"[blue]AI:[/blue]")
        try:
            md = Markdown(content)
            console.print(md)
        except Exception:
            console.print(content)
    else:
        console.print(content)


def display_response(content: str) -> None:
    """Display AI response with code highlighting"""
    try:
        md = Markdown(content)
        console.print(md)
    except Exception:
        console.print(content)


def display_models(models: list) -> None:
    """Display models in a table"""
    table = Table(title="Available Models", show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim", width=4)
    table.add_column("Model ID", style="green")
    table.add_column("Description", style="white")

    for idx, model in enumerate(models, 1):
        model_id = getattr(model, "id", "N/A")
        description = getattr(model, "description", "") or "-"
        table.add_row(str(idx), model_id, description)

    console.print(table)
    console.print("\n[dim]Use /model <number> to select a model[/dim]")


def _command_exists(cmd: str) -> bool:
    """Check if command exists"""
    if platform.system() == "Windows":
        return subprocess.call(f"where {cmd}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
    return subprocess.call(f"which {cmd}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0


def ask_confirmation(prompt: str) -> tuple:
    """Ask user for confirmation with Y/n/Deny Always option"""
    while True:
        response = console.input(f"{prompt} [Y/n/d]: ")
        response = response.strip().lower()
        if response in ("", "y", "yes"):
            return (True, False)
        elif response in ("n", "no"):
            return (False, False)
        elif response in ("d", "deny"):
            return (False, True)
        console.print("[yellow]Please answer: Y (yes), n (no), or d (deny always)[/yellow]")


def clear_screen() -> None:
    """Clear the terminal screen"""
    os.system("cls" if platform.system() == "Windows" else "clear")


def print_help() -> None:
    """Print help message"""
    help_text = """
[bold cyan]Ferrox CLI Commands[/bold cyan]

[cyan]/cfg[/cyan]       Open config file in editor
[cyan]/model[/cyan]    List and select available models
[cyan]/plan[/cyan]     Switch to Plan mode (read-only)
[cyan]/bypass[/cyan]   Switch to Bypass mode (auto-approve)
[cyan]/normal[/cyan]   Switch to Normal mode
[cyan]/clear[/cyan]    Clear chat history
[cyan]/exit[/cyan]     Exit CLI
[cyan]/help[/cyan]     Show this help message

[yellow]Hotkeys:[/yellow]
[cyan]Shift+Tab[/cyan]  Cycle between Normal/Plan/Bypass modes
[cyan]Ctrl+G[/cyan]     Open external editor for current input

[dim]For more information, visit: https://github.com/ferrox/ferrox[/dim]
"""
    console.print(help_text)