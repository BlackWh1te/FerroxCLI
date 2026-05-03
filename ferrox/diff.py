"""Diff viewer module for Ferrox - Devin-style file edit preview"""

import difflib
import os
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


console = Console()


def generate_diff(original_content: str, new_content: str, filename: str) -> list:
    """Generate unified diff lines"""
    original_lines = original_content.splitlines() if original_content else []
    new_lines = new_content.splitlines() if new_content else []

    diff = list(
        difflib.unified_diff(
            original_lines,
            new_lines,
            fromfile=f"original/{filename}",
            tofile=f"modified/{filename}",
            lineterm="",
        )
    )

    return diff


def render_diff_inline(original_content: str, new_content: str, filename: str) -> Panel:
    """Render diff with colors in a table format"""
    diff_lines = generate_diff(original_content, new_content, filename)

    table = Table(
        title=f"Proposed Changes to {filename}", show_header=False, box=None, padding=(0, 1, 0, 1)
    )

    table.add_column("Line #", style="dim", width=6)
    table.add_column("Content", overflow="fold")

    line_num = 0
    for line in diff_lines:
        if line.startswith("---") or line.startswith("+++"):
            continue
        elif line.startswith("@@"):
            table.add_row("", f"[cyan bold]{line}[/cyan bold]")
        elif line.startswith("-"):
            line_num -= 1
            table.add_row(str(line_num), f"[red]{line}[/red]")
        elif line.startswith("+"):
            table.add_row("+", f"[green]{line}[/green]")
            line_num += 1
        else:
            if line.strip():
                line_num += 1
                table.add_row(str(line_num), line)

    return Panel(table, border_style="blue", title=f"[EDIT] {filename}", title_align="left")


def render_diff_side_by_side(original_content: str, new_content: str, filename: str) -> Panel:
    """Render side-by-side diff view"""
    original_lines = original_content.splitlines() if original_content else []
    new_lines = new_content.splitlines() if new_content else []

    matcher = difflib.SequenceMatcher(None, original_lines, new_lines)
    output = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for idx in range(i2 - i1):
                output.append((" ", original_lines[i1 + idx], new_lines[j1 + idx]))
        elif tag == "insert":
            for idx in range(j2 - j1):
                output.append(("+", "", new_lines[j1 + idx]))
        elif tag == "delete":
            for idx in range(i2 - i1):
                output.append(("-", original_lines[i1 + idx], ""))
        elif tag == "replace":
            for idx in range(max(i2 - i1, j2 - j1)):
                old = original_lines[i1 + idx] if idx < (i2 - i1) else ""
                new = new_lines[j1 + idx] if idx < (j2 - j1) else ""
                output.append(("~", old, new))

    table = Table(title=f"📝 {filename}", show_header=True, box=None)
    table.add_column(" ", width=3)
    table.add_column("Original", width=40, overflow="fold")
    table.add_column("Modified", width=40, overflow="fold")

    for marker, old, new in output:
        if marker == " ":
            table.add_row(" ", old, new)
        elif marker == "-":
            table.add_row("[red]-[/red]", f"[red]{old}[/red]", "")
        elif marker == "+":
            table.add_row("[green]+[/green]", "", f"[green]{new}[/green]")
        elif marker == "~":
            table.add_row("[yellow]~[/yellow]", f"[red]{old}[/red]", f"[green]{new}[/green]")

    return Panel(table, border_style="blue")


def prompt_accept_reject(filename: str, timeout: int = 30) -> Optional[bool]:
    """Prompt user to accept or reject changes with keyboard input"""
    import sys

    print(f"\n[cyan]Review changes to {filename} above.[/cyan]")
    print(
        "[green]Press Enter[/green] to accept, [red]Esc[/red] to reject, [yellow]E[/yellow] to edit:"
    )

    if sys.stdin.isatty():
        try:
            import termios
            import tty

            old_settings = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())
            try:
                key = sys.stdin.read(1)
                if key == "\r" or key == "\n":
                    return True
                elif key == "\x1b":
                    return False
                elif key.lower() == "e":
                    return "edit"
            finally:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
        except:
            pass

    response = input("> ").strip().lower()
    if response == "":
        return True
    elif response in ("n", "no"):
        return False
    elif response == "e":
        return "edit"
    return True


def show_diff_and_prompt(original_content: str, new_content: str, filename: str) -> tuple:
    """
    Show diff and get user decision.
    Returns: (accepted: bool, edited_content: str or None)
    """
    diff_panel = render_diff_inline(original_content, new_content, filename)
    console.print(diff_panel)

    result = prompt_accept_reject(filename)

    if result is True:
        return (True, None)
    elif result is False:
        return (False, None)
    elif result == "edit":
        return (False, "edit")
    return (False, None)


def apply_file_edit(file_path: str, content: str) -> str:
    """Apply the edit to the file"""
    try:
        abs_path = os.path.abspath(file_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)

        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)

        return f"Successfully updated {file_path} ({len(content)} characters)"
    except Exception as e:
        return f"Error writing file: {str(e)}"
