"""Devin-style output formatting for Ferrox CLI.

Handles all model/tool response formatting so the UI feels like Devin.
"""

import os
import textwrap
from typing import Any, Dict, Optional
from rich.console import Console
from rich.text import Text
from rich.panel import Panel
from rich.syntax import Syntax
from rich.markdown import Markdown
from rich.rule import Rule
from rich.tree import Tree

console = Console()


# ── Agent Thinking / Activity Log ───────────────────────────────────────────

_agent_step_counter = 0


def reset_step_counter():
    global _agent_step_counter
    _agent_step_counter = 0


def format_agent_thought(thought: str, step: int = None) -> None:
    """Print an agent thinking/reasoning step with enhanced visibility."""
    global _agent_step_counter
    if step is None:
        _agent_step_counter += 1
        step = _agent_step_counter

    # Plain-text labels avoid ANSI garbage on Windows when
    # prompt_toolkit patch_stdout intercepts stdout.
    if thought.startswith("Tool call:"):
        label = "[TOOL]"
    elif "SUCCESS" in thought or "successfully" in thought.lower():
        label = "[OK]"
    elif "FAILED" in thought or "failed" in thought.lower() or "error" in thought.lower():
        label = "[ERROR]"
    elif "URL:" in thought or "http" in thought.lower():
        label = "[LINK]"
    elif thought.startswith("Result "):
        label = "[RESULT]"
    elif "Starting" in thought or "initiating" in thought.lower():
        label = "[START]"
    else:
        label = "[THINK]"
    console.file.write(f"  {label} {thought}\n")
    console.file.flush()


def format_task_start(task_name: str, task_num: int = 1, total_tasks: int = 1) -> None:
    """Print the start of a new task/sub-task."""
    if total_tasks > 1:
        console.print(Text(f"  ● Task {task_num}/{total_tasks}: {task_name}", style="bold yellow"))
    else:
        console.print(Text(f"  ● {task_name}", style="bold yellow"))


def format_task_complete(task_name: str, success: bool = True) -> None:
    """Print task completion."""
    icon = "✓" if success else "✗"
    color = "green" if success else "red"
    console.print(Text(f"  {icon} {task_name}", style=f"bold {color}"))


# ── Monolog / Tool Result Formatters ────────────────────────────────────────


def format_read_file_result(result: dict) -> None:
    """Devin-style monolog for file reads — shows ● bullet and └ line count."""
    file_path = result.get("file_path", "unknown")
    lines_read = result.get("lines_read", (1, 1))
    total_lines = result.get("total_lines", 0)

    start_line, end_line = lines_read
    num_lines = end_line - start_line + 1

    # Make path relative to cwd for cleaner display
    cwd = os.getcwd()
    rel_path = os.path.relpath(file_path, cwd) if os.path.isabs(file_path) else file_path

    header = Text()
    header.append("● ", style="bold cyan")
    header.append(f"Read lines {start_line}-{end_line}", style="cyan")
    header.append(" in ", style="dim")
    header.append(rel_path, style="bold white")
    console.print(header)

    # Line count indicator
    console.print(Text(f"  └ {num_lines} lines", style="dim"))

    # If truncated, show remaining
    if total_lines > 0 and end_line < total_lines:
        console.print(
            Text(f"  … ({total_lines - end_line} more lines in file)", style="dim italic")
        )


def format_list_directory_result(result: str) -> None:
    """Devin-style monolog for directory listings."""
    if isinstance(result, dict):
        result = result.get("content", str(result))

    # Extract path from the result string if present
    lines = result.splitlines()
    header_line = lines[0] if lines else "Directory listing"
    items = lines[1:] if len(lines) > 1 else []

    header = Text()
    header.append("● ", style="bold cyan")
    header.append("Listed ", style="cyan")
    header.append(f"{len(items)} items", style="cyan")
    header.append(" in ", style="dim")
    # Try to extract path
    path = "."
    if "Contents of" in header_line:
        path = header_line.replace("Contents of ", "").strip()
    header.append(path, style="bold white")

    console.print(header)

    # Show first few items
    for item in items[:8]:
        icon = "📁" if "📁" in item else "📄"
        name = item.replace("📁 ", "").replace("📄 ", "")
        console.print(Text(f"     {icon} {name}", style="dim"))
    if len(items) > 8:
        console.print(Text(f"     … ({len(items) - 8} more items)", style="dim italic"))


def format_shell_result(result: dict) -> None:
    """Devin-style monolog for shell commands."""
    command = result.get("command", "")
    exit_code = result.get("exit_code", -1)
    cwd = result.get("working_dir", ".")

    rel_cwd = os.path.relpath(cwd) if os.path.isabs(cwd) else cwd

    header = Text()
    header.append("● ", style="bold green" if exit_code == 0 else "bold red")
    if exit_code == 0:
        header.append("Ran ", style="bold green")
    else:
        header.append("Failed ", style="bold red")
    header.append(f"$ {command}", style="white")
    header.append(f"  (exit {exit_code})", style="dim")
    if rel_cwd != ".":
        header.append(f"  in {rel_cwd}", style="dim italic")

    console.print(header)

    stdout = result.get("stdout", "")
    stderr = result.get("stderr", "")
    if stdout:
        out_lines = stdout.strip().splitlines()[:5]
        for line in out_lines:
            console.print(Text(f"     {line[:120]}", style="dim green"))
        if len(stdout.splitlines()) > 5:
            console.print(
                Text(f"     … ({len(stdout.splitlines()) - 5} more lines)", style="dim italic")
            )
    if stderr:
        err_lines = stderr.strip().splitlines()[:3]
        for line in err_lines:
            console.print(Text(f"     {line[:120]}", style="dim red"))
        if len(stderr.splitlines()) > 3:
            console.print(
                Text(f"     … ({len(stderr.splitlines()) - 3} more lines)", style="dim italic")
            )


def format_write_file_result(file_path: str, content_len: int, success: bool = True) -> None:
    """Devin-style monolog for file writes."""
    rel_path = os.path.relpath(file_path) if os.path.isabs(file_path) else file_path

    header = Text()
    header.append("● ", style="bold green" if success else "bold red")
    if success:
        header.append("Wrote ", style="bold green")
    else:
        header.append("Failed to write ", style="bold red")
    header.append(f"{content_len} chars", style="cyan")
    header.append(" to ", style="dim")
    header.append(rel_path, style="bold white")

    console.print(header)


def format_tool_call(tool_name: str, args: dict) -> None:
    """Print a thinking-style tool call notice."""
    header = Text()
    header.append("  └─ ", style="dim")
    header.append("Using ", style="bold yellow")
    header.append(tool_name, style="yellow")
    if args:
        # Summarize args
        summary = ", ".join(f"{k}={str(v)[:30]}" for k, v in list(args.items())[:3])
        header.append(f"  ({summary})", style="dim italic")
    console.print(header)


def format_thinking(text: str) -> None:
    """Print a thinking/observation line."""
    console.print(Text(f"  └─ {text}", style="dim italic"))


# ── Response Formatters ─────────────────────────────────────────────────────


def format_agent_response(content: str) -> None:
    """Print the agent's final response nicely."""
    # If it looks like markdown, render it
    if "```" in content or "#" in content or "**" in content or "- " in content:
        try:
            console.print(Markdown(content))
            return
        except Exception:
            pass
    console.print(content)


def _strip_wrapper_objects(text: str) -> str:
    """Strip common raw object wrapper patterns from LLM output.

    Handles nested wrappers (e.g. AgentRunResult(output="AgentRunResult(output='...')"))
    and escaped quotes inside strings (e.g. you\\'re).
    """

    def _extract_quoted_value(s: str, prefix: str) -> str | None:
        import re

        s = s.strip()
        if not s.startswith(prefix):
            return None
        body = s[len(prefix) :]
        if not body or body[0] not in ('"', "'"):
            return None
        quote = body[0]

        # Scan backwards from the end to find the closing quote.
        # A valid closer is followed by optional whitespace, an optional ')', and
        # then end-of-string — this avoids stopping at unescaped quotes inside
        # the content (e.g. "you're").
        for i in range(len(body) - 1, 0, -1):
            if body[i] == quote:
                after = body[i + 1 :]
                if re.match(r"\s*\)?\s*$", after):
                    return body[1:i]
        return None

    prefixes = [
        "AgentRunResult(output=",
        "AgentRun(output=",
        "RunResult(data=",
        "RunResult(output=",
        "AgentResult(content=",
        "Response(content=",
    ]

    changed = True
    while changed:
        changed = False
        stripped = text.strip()
        for prefix in prefixes:
            extracted = _extract_quoted_value(stripped, prefix)
            if extracted is not None:
                text = extracted
                changed = True
                break

    return text


def _unescape_newlines(text: str) -> str:
    """Convert literal \\n strings into actual newlines."""
    return text.replace("\\n", "\n")


def _fence_bare_json(text: str) -> str:
    """If the text contains a bare JSON block not wrapped in ```, wrap it."""
    import json, re

    def _try_fence(match: re.Match) -> str:
        block = match.group(0)
        # Skip if it looks like it's already inside a code block
        before = text[: match.start()]
        after = text[match.end() :]
        # Simple heuristic: if the last ``` before us is unclosed, skip
        backticks_before = before.count("```")
        backticks_after = after.count("```")
        if backticks_before % 2 == 1:
            return block  # inside a fenced block
        try:
            json.loads(block)
            return f"\n```json\n{block}\n```\n"
        except Exception:
            return block

    # Look for bare JSON objects/arrays that are not inside backticks
    pattern = re.compile(r"((?:\{(?:[^{}]|\{[^{}]*\])*\})|(?:\[(?:[^\[\]]|\[[^\[\]]*\])*\]))")
    return pattern.sub(_try_fence, text)


def format_assistant_message(content: str) -> None:
    """Print the assistant's message in Devin style."""
    content = _strip_wrapper_objects(content)
    content = _unescape_newlines(content)
    content = _fence_bare_json(content)
    # Try markdown first
    if "```" in content or "#" in content or "**" in content or "- " in content or "[" in content:
        try:
            console.print(Markdown(content))
            return
        except Exception:
            pass
    console.print(Text(content, style="white"))


def format_user_message(content: str) -> None:
    """Print the user's message in a clean Devin-style single line."""
    console.print(Text(f"> {content}", style="bold green"))


def format_error(message: str) -> None:
    """Print an error message."""
    console.print(
        Panel(
            Text(message, style="red"),
            title="[bold red]Error[/bold red]",
            border_style="red",
            padding=(0, 1),
        )
    )


def format_warning(message: str) -> None:
    """Print a warning message."""
    console.print(
        Panel(
            Text(message, style="yellow"),
            title="[bold yellow]Warning[/bold yellow]",
            border_style="yellow",
            padding=(0, 1),
        )
    )


def format_success(message: str) -> None:
    """Print a success message."""
    console.print(
        Panel(
            Text(message, style="green"),
            title="[bold green]Success[/bold green]",
            border_style="green",
            padding=(0, 1),
        )
    )


def format_system(message: str) -> None:
    """Print a system message."""
    console.print(Text(f"[dim]System: {message}[/dim]"))


def format_mode_change(mode_name: str, description: str, color: str = "white") -> None:
    """Print a mode change notification."""
    console.print(
        Rule(
            title=f"[bold {color}]{mode_name}[/bold {color}]  {description}",
            style=color,
            align="center",
        )
    )


def format_separator() -> None:
    """Print a subtle separator line."""
    console.print(Rule(style="dim", characters="─"))


def format_web_search_results(results: str) -> None:
    """Format web search results with enhanced structure.

    Args:
        results: Raw web search results string
    """
    console.print(Rule("[bold cyan]Web Search Results[/bold cyan]", style="cyan"))

    # Parse the results and format them nicely
    lines = results.split("\n")
    current_section = None

    for line in lines:
        line = line.rstrip()

        # Detect numbered results
        if line and line[0].isdigit() and ". " in line[:5]:
            console.print(f"\n[bold white]{line}[/bold white]")
        # Detect URLs
        elif line.strip().startswith("URL:"):
            console.print(f"[dim cyan]{line}[/dim cyan]")
        # Detect content previews
        elif "Content Preview:" in line or "Summary:" in line:
            console.print(f"[bold yellow]{line}[/bold yellow]")
        # Detect separators
        elif "---" in line:
            console.print(Rule(style="dim"))
        # Regular content
        elif line.strip():
            # Highlight key information patterns
            if any(
                keyword in line.lower()
                for keyword in ["headline", "breaking", "update", "announced"]
            ):
                console.print(f"[bold green]{line}[/bold green]")
            elif any(keyword in line.lower() for keyword in ["said", "stated", "according to"]):
                console.print(f"[italic]{line}[/italic]")
            else:
                console.print(line)

    console.print(Rule(style="dim"))


def format_elapsed(elapsed_sec: float, tokens_used: int = 0) -> None:
    """Print a compact elapsed-time / token summary after thinking finishes."""
    msg = Text()
    msg.append("  └─ ", style="dim")
    msg.append(f"{elapsed_sec:.1f}s", style="cyan")
    if tokens_used > 0:
        msg.append("  ·  ", style="dim")
        msg.append(f"{tokens_used:,} tokens", style="cyan")
    console.print(msg)
