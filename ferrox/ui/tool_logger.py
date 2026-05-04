import os

from rich.console import Console
from rich.text import Text

console = Console()


def log_tool_execution(tool_name: str, result: dict):
    """
    Logs tool execution in Devin-style format.
    """

    if tool_name == "read_file":
        file_path = result.get("file_path", "unknown")
        lines_read = result.get("lines_read", (1, 1))
        total_lines = result.get("total_lines", 0)

        start_line, end_line = lines_read
        if start_line == 1 and end_line == total_lines:
            summary = f"Read entire file ({total_lines} lines) from {file_path}"
        else:
            summary = f"Read lines {start_line}-{end_line} of {total_lines} from {file_path}"

        console.print(
            Text("✓ ", style="green bold")
            + Text(f"ReadFile {file_path} → {summary}", style="white")
        )

    elif tool_name == "search_text":
        query = result.get("query", "")
        file_path = result.get("file_path", "unknown")
        matches = result.get("matches", [])

        summary = f"Found {len(matches)} match(es)" if matches else "No matches found"

        console.print(
            Text("✓ ", style="green bold")
            + Text(f"SearchText '{query}' in {file_path} → {summary}", style="white")
        )

    elif tool_name == "edit_file":
        file_path = result.get("file_path", "unknown")
        additions = result.get("additions", 0)
        deletions = result.get("deletions", 0)
        accepted = result.get("accepted", False)

        if accepted:
            status = f"Accepted (+{additions}, -{deletions})"
            icon = "✓"
            color = "green bold"
        else:
            status = "Rejected"
            icon = "✗"
            color = "red bold"

        console.print(
            Text(f"{icon} ", style=color)
            + Text(f"Edit {os.path.basename(file_path)} → {status}", style="white")
        )

    elif tool_name == "run_command":
        command = result.get("command", "")
        exit_code = result.get("exit_code", -1)
        working_dir = result.get("working_dir", ".")

        if exit_code == 0:
            icon = "✓"
            color = "green bold"
            status = "Success"
        else:
            icon = "✗"
            color = "red bold"
            status = f"Failed (exit code {exit_code})"

        console.print(
            Text(f"{icon} ", style=color)
            + Text(f"Shell {working_dir} $ {command} → {status}", style="white")
        )

    else:
        console.print(Text(f"? {tool_name} → {result.get('summary', 'Executed')}", style="dim"))
