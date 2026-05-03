import asyncio
import contextlib
import os
import shutil
from typing import Optional, Dict, Any
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import Completer, Completion, WordCompleter
from prompt_toolkit.styles import Style
from prompt_toolkit.lexers import PygmentsLexer
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.shortcuts import prompt, CompleteStyle
from prompt_toolkit.filters import vi_insert_mode, emacs_insert_mode
from prompt_toolkit.formatted_text import HTML
from pygments.lexers.shell import BashLexer
from rich.console import Console

console = Console()

# ─── Devin-Style Theme ──────────────────────────────────────────────────────
# A dark, high-contrast theme inspired by Devin CLI and modern dev tools.

DEVIN_STYLE = Style.from_dict(
    {
        # Input field styling
        "prompt": "#00d4ff bold",
        "input-field": "#e0e0e0 bg:#1a1a2e",
        "input-field.cursor-line": "#e0e0e0 bg:#1a1a2e",
        # Bottom toolbar / status bar
        "status-toolbar": "bg:#0f0f1a #a0a0b0",
        "status-toolbar.text": "#a0a0b0",
        "status-mode-normal": "#00ff7f bold",
        "status-mode-plan": "#ffa500 bold",
        "status-mode-edit": "#00bfff bold",
        "status-mode-bypass": "#ff4757 bold",
        "status-key": "#808080 italic",
        "status-value": "#e0e0e0 bold",
        "status-separator": "#444466",
        "status-workspace": "#ffd700 bold",
        "status-model": "#7bed9f",
        "status-branch": "#70a1ff",
        # Syntax highlighting via Pygments -> prompt_toolkit mapping
        "pygments.comment": "#6272a4 italic",
        "pygments.keyword": "#ff79c6 bold",
        "pygments.string": "#f1fa8c",
        "pygments.name.builtin": "#8be9fd",
        "pygments.name.function": "#50fa7b",
        "pygments.literal.number": "#bd93f9",
        "pygments.operator": "#ff79c6",
        "pygments.punctuation": "#f8f8f2",
        "pygments.text": "#e0e0e0",
        # ── Claude-style input box chrome ───────────────────────────────
        # Top separator line above the input area
        "separator-line": "#3a3a5c",
        # Prompt label (the mode icon + arrow prefix)
        "prompt-label": "#00d4ff bold",
        # Placeholder text when buffer is empty
        "placeholder": "#555577 italic",
        # Completion dropdown
        "completion-menu.completion": "bg:#1e1e35 #c0c0d8",
        "completion-menu.completion.current": "bg:#00d4ff #0a0a1a bold",
        "completion-menu.meta.completion": "bg:#16162a #808098 italic",
        "completion-menu.meta.completion.current": "bg:#0099bb #e0e0f0 italic",
    }
)

# ─── Slash Commands with Descriptions ──────────────────────────────────────

COMMAND_META: dict = {
    "/cfg": "open config file in editor",
    "/model": "list and select AI models",
    "/plan": "switch to Plan mode",
    "/bypass": "switch to Bypass mode (auto-approve all)",
    "/normal": "switch to Normal mode",
    "/edit": "switch to Edit mode (scoped edits)",
    "/clear": "clear chat history",
    "/exit": "quit Ferrox",
    "/status": "show health, quota and mode status",
    "/help": "show all commands",
    "/index": "index project symbols for context",
    "/steps": "view current plan steps",
    "/next": "execute the next plan step",
    "/step": "jump to a specific plan step",
    "/browse": "open a URL in the headless browser",
    "/jobs": "list background jobs",
    "/fix": "start autonomous test/fix loop",
    "/update": "auto-update Ferrox from upstream",
    "/pip": "install a Python package via pip",
    "/npm": "install a Node package via npm",
    "/cargo": "install a Rust crate via cargo",
    "/brew": "install a macOS package via brew",
    "/go": "install a Go package",
    "/dashboard": "check real-time dashboard status",
    "/agents": "show agent pool status",
    "/metrics": "display system and agent metrics",
    "/events": "show recent agent events",
    "/verbose": "toggle detailed agent thoughts output",
    "/thoughts": "show recent agent thoughts",
    # X Bot Social Commands
    "/x-mode": "switch to X Bot Expert mode",
    "/x-login": "browser login to X (no password stored, cookies only)",
    "/social": "show X Bot status and commands",
    "/social login": "manual login to X with username/password",
    "/social start": "start background X Bot daemon",
    "/social stop": "stop X Bot daemon",
    "/social panic": "emergency stop and logout",
    "/social undo": "delete last tweet",
}

# Keep a plain list for backward-compat references
COMMANDS = list(COMMAND_META.keys())


# ─── Slash Command Completer ────────────────────────────────────────────────


class SlashCommandCompleter(Completer):
    """
    Completes /commands with inline descriptions shown in the right column.
    Only activates when the line starts with '/'.
    """

    def get_completions(self, document, complete_event):
        text_before = document.text_before_cursor.lstrip()

        if not text_before.startswith("/"):
            return

        # Extract the partial command token
        parts = text_before.split()
        word = parts[0] if parts else "/"

        for cmd, description in COMMAND_META.items():
            if cmd.startswith(word):
                yield Completion(
                    text=cmd,
                    start_position=-len(word),
                    display=cmd,
                    display_meta=description,
                )


def _get_git_branch() -> str:
    """Quick git branch lookup."""
    try:
        import subprocess

        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            cwd=os.getcwd(),
            timeout=1,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "no repo"


def _truncate_path(path: str, max_len: int = 40) -> str:
    """Truncate a path from the left if too long."""
    path = os.path.normpath(path)
    if len(path) <= max_len:
        return path
    return "…" + path[-(max_len - 1) :]


def _get_mode_style_class(mode_name: str) -> str:
    """Return the style class for a given mode."""
    return f"class:status-mode-{mode_name.lower()}"


def get_status_footer_text(mode_manager, config, session_state: Dict[str, Any]) -> Any:
    """Generates a rich Devin-style bottom status bar."""
    # Mode block
    mode = mode_manager.current_mode
    mode_name = mode.value
    mode_icon = mode_manager.get_mode_icon()
    mode_color_class = _get_mode_style_class(mode_name)
    mode_desc = mode_manager.get_mode_description()

    # Workspace
    workspace = _truncate_path(os.getcwd(), 38)

    # Git branch
    branch = _get_git_branch()

    # Model
    provider = config.get_active_provider() if config else None
    model_name = provider.default_model if provider else "none"
    if len(model_name) > 25:
        model_name = model_name[:22] + "…"

    # Tokens
    tokens_used = session_state.get("tokens_used", 0)
    tokens_limit = session_state.get("tokens_limit", 200_000)
    tokens_pct = min(100, int((tokens_used / tokens_limit) * 100)) if tokens_limit else 0

    result = [
        ("class:status-separator", " ┃ "),
        (mode_color_class, f" {mode_icon} {mode_name} "),
        ("class:status-key", f"({mode_desc})"),
        ("class:status-separator", " ┃ "),
        ("class:status-key", " workspace "),
        ("class:status-workspace", f" {workspace} "),
        ("class:status-separator", " ┃ "),
        ("class:status-key", " branch "),
        ("class:status-branch", f" ({branch}) "),
        ("class:status-separator", " ┃ "),
        ("class:status-key", " model "),
        ("class:status-model", f" {model_name} "),
        ("class:status-separator", " ┃ "),
        ("class:status-key", " tokens "),
        ("class:status-value", f" {tokens_used:,}/{tokens_limit:,} "),
        ("class:status-separator", " ┃ "),
    ]
    return result


def create_prompt_session(mode_manager=None, config=None, session_state=None):
    """
    Creates a PromptSession with Claude-CLI style input bar:
      - Multiline input: Enter submits, Meta+Enter (Esc then Enter) / Ctrl+J for newline
      - Separator line drawn above the input area on each prompt
      - Placeholder text when the buffer is empty
      - Slash command autocomplete with inline description column
      - Compact bottom toolbar: mode / workspace / branch / model / tokens
      - Shift+Tab to cycle modes, Ctrl+G to open external editor
    """
    history_file = os.path.expanduser("~/.ferrox/history.txt")
    os.makedirs(os.path.dirname(history_file), exist_ok=True)

    # ── Message callable: separator line + mode-labeled prompt ──────────
    def message_callable():
        try:
            cols = shutil.get_terminal_size(fallback=(80, 24)).columns
        except Exception:
            cols = 80

        sep_line = "─" * cols

        if mode_manager:
            mode_icon = mode_manager.get_mode_icon()
            mode = mode_manager.current_mode
            label = f" {mode_icon} "
            label_class = f"class:status-mode-{mode.value.lower()}"
        else:
            label = " » "
            label_class = "class:prompt-label"

        return [
            ("class:separator-line", sep_line + "\n"),
            (label_class, label),
        ]

    # ── Bottom toolbar ───────────────────────────────────────────────────
    def bottom_toolbar_callable():
        if mode_manager and config and session_state is not None:
            status = get_status_footer_text(mode_manager, config, session_state)
            guide = [
                ("class:status-key", " Meta+↵ "),
                ("class:status-value", "newline "),
                ("class:status-separator", " ┃ "),
                ("class:status-key", " Shift+Tab "),
                ("class:status-value", "mode "),
                ("class:status-separator", " ┃ "),
                ("class:status-key", " Ctrl+G "),
                ("class:status-value", "editor "),
                ("class:status-separator", " ┃ "),
                ("class:status-key", " /help "),
            ]
            return status + guide
        return [("class:status-toolbar", " Ferrox ")]

    # ── Multiline continuation indicator ────────────────────────────────
    def prompt_continuation(width, line_number, wrap_count):
        """Show a subtle '· ' indicator on continuation lines."""
        return [("class:prompt-label", " " * max(0, width - 2) + "· ")]

    # ── Key bindings ─────────────────────────────────────────────────────
    kb = KeyBindings()

    insert_mode = vi_insert_mode | emacs_insert_mode

    @kb.add("enter", filter=insert_mode, eager=True)
    def _enter_submits(event):
        """Enter always submits."""
        event.current_buffer.validate_and_handle()

    @kb.add("escape", "enter", filter=insert_mode, eager=True)
    def _meta_enter_newline(event):
        """Meta+Enter (Alt+Enter / Esc then Enter) inserts a newline."""
        event.current_buffer.newline(copy_margin=False)

    @kb.add("c-j", filter=insert_mode)
    def _ctrl_j_newline(event):
        """Ctrl+J inserts a newline (fallback for terminals where Alt+Enter is unreliable)."""
        event.current_buffer.newline(copy_margin=False)

    @kb.add("s-tab")
    def _cycle_mode(event):
        """Shift+Tab cycles Normal → Plan → Edit → Bypass → Normal."""
        if mode_manager:
            mode_manager.cycle_mode()
            if event.app:
                event.app.invalidate()

    @kb.add("c-g")
    def _open_editor(event):
        """Ctrl+G opens the system editor for the current buffer content."""
        from .ui_legacy import open_external_editor

        buf = event.app.current_buffer
        edited = open_external_editor(buf.text)
        if edited is not None:
            buf.text = edited
            buf.cursor_position = len(edited)

    return PromptSession(
        history=FileHistory(history_file),
        completer=SlashCommandCompleter(),
        complete_style=CompleteStyle.MULTI_COLUMN,
        complete_while_typing=True,
        style=DEVIN_STYLE,
        message=message_callable,
        bottom_toolbar=bottom_toolbar_callable,
        multiline=True,
        wrap_lines=True,
        prompt_continuation=prompt_continuation,
        lexer=PygmentsLexer(BashLexer),
        key_bindings=kb,
        placeholder=HTML("<placeholder>How can Ferrox help?</placeholder>"),
        reserve_space_for_menu=8,
    )


async def get_user_input(session: PromptSession) -> str:
    """
    Asynchronously gets user input using prompt_toolkit.
    Uses patch_stdout so the input bar stays pinned at the bottom
    while model output streams above it.
    """
    from prompt_toolkit.patch_stdout import patch_stdout

    try:
        with patch_stdout():
            text = await session.prompt_async(
                auto_suggest=AutoSuggestFromHistory(),
                enable_history_search=True,
                complete_in_thread=True,
            )
        return text.strip()
    except EOFError:
        return "/exit"
    except KeyboardInterrupt:
        return "/exit"


# ── Persistent busy bar shown while the agent is running ─────────────────────


def create_busy_session(mode_manager=None, config=None, session_state=None):
    """
    Creates a lightweight PromptSession shown while the agent is running.

    The bar is visually identical to the main input bar but labelled
    "agent running".  The user can type:
      /btw <message>  — inject context that the agent will see on the next turn
      /stop           — cancel the running agent
      Ctrl+C          — same as /stop
    """
    kb = KeyBindings()
    insert_mode = vi_insert_mode | emacs_insert_mode

    @kb.add("enter", filter=insert_mode, eager=True)
    def _submit(event):
        event.current_buffer.validate_and_handle()

    @kb.add("c-c")
    def _stop(event):
        event.app.exit(exception=KeyboardInterrupt)

    def busy_message():
        try:
            cols = shutil.get_terminal_size(fallback=(80, 24)).columns
        except Exception:
            cols = 80
        sep = "─" * cols
        if mode_manager:
            mode = mode_manager.current_mode
            icon = mode_manager.get_mode_icon()
            label_class = f"class:status-mode-{mode.value.lower()}"
            return [
                ("class:separator-line", sep + "\n"),
                (label_class, f" {icon} "),
                ("class:status-key", "agent "),
                ("class:status-separator", "· "),
            ]
        return [
            ("class:separator-line", sep + "\n"),
            ("class:prompt-label", " ⏳ "),
        ]

    def busy_toolbar():
        base = []
        if mode_manager and config and session_state is not None:
            base = get_status_footer_text(mode_manager, config, session_state)
        base += [
            ("class:status-key", " /btw <msg> "),
            ("class:status-value", "inject context "),
            ("class:status-separator", " ┃ "),
            ("class:status-key", " Ctrl+C "),
            ("class:status-value", "stop agent "),
        ]
        return base

    return PromptSession(
        history=FileHistory(os.path.expanduser("~/.ferrox/history.txt")),
        style=DEVIN_STYLE,
        message=busy_message,
        bottom_toolbar=busy_toolbar,
        completer=SlashCommandCompleter(),
        complete_style=CompleteStyle.MULTI_COLUMN,
        complete_while_typing=True,
        key_bindings=kb,
        placeholder=HTML(
            "<placeholder>/btw &lt;message&gt; to inject context  ·  Ctrl+C to stop</placeholder>"
        ),
        multiline=False,
        reserve_space_for_menu=8,
    )


async def run_agent_with_input_bar(agent_coro, busy_session: PromptSession):
    """
    Runs `agent_coro` while keeping a visible input bar at the bottom.

    Returns ``(agent_result, btw_messages)`` where ``btw_messages`` is a list
    of strings the user typed as ``/btw <message>`` during execution.

    How it works
    ------------
    prompt_toolkit's ``patch_stdout`` context redirects all stdout writes so
    they appear *above* the currently-rendered prompt.  We keep that context
    active for the entire duration of the agent call while simultaneously
    running ``busy_session.prompt_async()`` — so the input bar is always
    anchored at the bottom.

    When the agent finishes, we cancel the prompt task (prompt_toolkit restores
    terminal state cleanly on cancellation).  When the user submits a line, we
    handle it and immediately restart the prompt so the bar never disappears.
    """
    from prompt_toolkit.patch_stdout import patch_stdout

    btw_messages = []
    agent_task = asyncio.create_task(agent_coro)

    with patch_stdout():
        while not agent_task.done():
            prompt_task = asyncio.create_task(
                busy_session.prompt_async(
                    auto_suggest=AutoSuggestFromHistory(),
                    complete_in_thread=True,
                )
            )
            try:
                done, _ = await asyncio.wait(
                    {agent_task, prompt_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
            except asyncio.CancelledError:
                prompt_task.cancel()
                agent_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await asyncio.gather(prompt_task, agent_task, return_exceptions=True)
                raise

            if not prompt_task.done():
                # Agent finished — cleanly dismiss the prompt
                prompt_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await prompt_task
                break

            # User submitted something while the agent is running
            try:
                line = prompt_task.result().strip()
            except KeyboardInterrupt:
                agent_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await agent_task
                raise
            except (EOFError, Exception):
                line = ""

            if line.lower().startswith("/btw "):
                msg = line[5:].strip()
                if msg:
                    btw_messages.append(msg)
                    console.file.write(f'  [BTW] Injected -> "{msg[:80]}"\n')
                    console.file.flush()
            elif line in ("/stop", "/cancel"):
                agent_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await agent_task
                break
            elif line:
                console.file.write(
                    "  Agent is running. Use /btw <msg> to inject context or Ctrl+C to stop.\n"
                )
                console.file.flush()
            # Loop immediately — bar reappears without any gap

    return await agent_task, btw_messages
