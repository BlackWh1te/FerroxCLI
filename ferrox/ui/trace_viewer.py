from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich.text import Text

console = Console()


def show_help_panel():
    """Display keyboard shortcuts help panel."""
    console.print("\n" + "=" * 50)
    console.print("  ⌨️  FERROX KEYBOARD SHORTCUTS")
    console.print("=" * 50 + "\n")

    table = Table(box=None, padding=(0, 2))
    table.add_column("Shortcut", style="cyan bold", width=12)
    table.add_column("Action", style="white")

    shortcuts = [
        ("Ctrl+O", "Open Trace/Thinking Viewer"),
        ("Ctrl+L", "Clear screen"),
        ("Ctrl+R", "Refresh/Reset display"),
        ("Shift+Tab", "Cycle modes (Normal/Plan/Bypass)"),
        ("Ctrl+G", "Open external editor for multi-line input"),
        ("Ctrl+C", "Exit Ferrox"),
        ("Enter", "Submit message"),
        ("Esc", "Cancel current thinking"),
    ]

    for shortcut, action in shortcuts:
        table.add_row(shortcut, action)

    console.print(table)
    console.print("\n" + "-" * 50)
    console.print("[dim]Press Enter to return...[/dim]")
    input()


def show_trace_viewer(agent_logs: list):
    """Display a full-screen overlay of agent thoughts and tool calls."""
    console.print("\n" + "=" * 60)
    console.print("  🧠 FERROX TRACE VIEWER")
    console.print("=" * 60 + "\n")

    if not agent_logs:
        console.print("[dim]No logs recorded yet.[/dim]")
    else:
        # Summary stats
        thoughts = sum(1 for log in agent_logs if log["type"] == "thought")
        tool_calls = sum(1 for log in agent_logs if log["type"] == "tool_call")
        successes = sum(
            1 for log in agent_logs if log["type"] == "tool_result" and log.get("success")
        )
        failures = sum(
            1 for log in agent_logs if log["type"] == "tool_result" and not log.get("success")
        )

        console.print(
            f"[dim]Summary:[/dim] {thoughts} thoughts | {tool_calls} tool calls | {successes} ✅ | {failures} ❌\n"
        )
        console.print("-" * 60 + "\n")

        for i, log in enumerate(agent_logs):
            timestamp = log.get("timestamp", "")
            ts_str = (
                timestamp.strftime("%H:%M:%S") if hasattr(timestamp, "strftime") else str(timestamp)
            )

            if log["type"] == "thought":
                console.print(
                    Panel(
                        log["content"],
                        title=f"🧠 Thought [{ts_str}]",
                        border_style="blue",
                        padding=(0, 1),
                    )
                )

            elif log["type"] == "tool_call":
                table = Table(box=None, show_header=False, padding=(0, 1))
                table.add_column("Key", style="cyan bold")
                table.add_column("Value", style="white")
                for k, v in log.get("args", {}).items():
                    table.add_row(f"{k}:", str(v)[:60])
                console.print(
                    Panel(
                        table,
                        title=f"🛠️ Tool Call: {log['name']} [{ts_str}]",
                        border_style="yellow",
                        padding=(0, 1),
                    )
                )

            elif log["type"] == "tool_result":
                status = "✅ Success" if log.get("success") else "❌ Failed"
                color = "green" if log.get("success") else "red"
                content = log.get("content", "")
                if len(content) > 200:
                    content = content[:200] + "..."
                console.print(
                    Panel(
                        f"[{color}]{status}[/{color}]\n{content}",
                        title=f"📤 Result: {log['name']} [{ts_str}]",
                        border_style=color,
                        padding=(0, 1),
                    )
                )

            console.print()  # Add spacing between entries

    console.print("-" * 60)
    console.print("[dim]Press Enter to return to chat...[/dim]")
    input()
