"""Hermes Agent integration tools for FerroxCLI.

Provides tools to interact with the Hermes Agent (https://github.com/NousResearch/hermes-agent):
- Chat with Hermes agent
- Model management
- Gateway control (Telegram, Discord, Slack, WhatsApp, etc.)
- Skills sync
- Memory access
- Cron scheduling
- Kanban task management
- Session management
- Config get/set
"""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path
from typing import Any

from pydantic_ai import RunContext

# Optional telemetry / mode dependencies (imported lazily to avoid heavy deps)
try:
    from opentelemetry import trace  # type: ignore

    tracer = trace.get_tracer(__name__)
except Exception:  # pragma: no cover
    tracer = None  # type: ignore

try:
    from ..modes import Mode  # type: ignore
except Exception:  # pragma: no cover
    Mode = None  # type: ignore


# ---------------------------------------------------------------------------
# Hermes discovery
# ---------------------------------------------------------------------------


def _default_hermes_path() -> Path:
    """Return the default Hermes installation path for the current platform."""
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            return Path(local) / "hermes" / "hermes-agent"
        return Path.home() / "AppData" / "Local" / "hermes" / "hermes-agent"
    return Path.home() / ".hermes" / "hermes-agent"


def _resolve_hermes_path(ctx: RunContext[Any] | None = None) -> Path:
    """Resolve the Hermes installation path from env / config / default."""
    env_path = os.environ.get("HERMES_PATH")
    if env_path:
        return Path(env_path)

    config = getattr(getattr(ctx, "deps", None), "config", None) if ctx else None
    if config is not None:
        custom = getattr(config, "hermes_path", None)
        if custom:
            return Path(custom)
    return _default_hermes_path()


def _hermes_python(hermes_path: Path) -> str:
    """Return the Python executable used to run Hermes (venv if present)."""
    venv_py = hermes_path / "venv"
    if os.name == "nt":
        candidate = venv_py / "Scripts" / "python.exe"
    else:
        candidate = venv_py / "bin" / "python"
    if candidate.exists():
        return str(candidate)
    return "python"


def _hermes_cli_cmd(hermes_path: Path) -> list[str]:
    """Return the base command used to invoke the Hermes CLI.

    Hermes ships a top-level ``cli.py`` that can be executed directly.
    We also fall back to the ``hermes`` wrapper when present in PATH.
    """
    cli_py = hermes_path / "cli.py"
    if cli_py.exists():
        return [_hermes_python(hermes_path), str(cli_py)]
    return ["hermes"]


def _hermes_available(hermes_path: Path) -> bool:
    """Return True if a usable Hermes installation is detected."""
    return (hermes_path / "cli.py").exists() or shutil.which("hermes") is not None


def _format_tool_call(name: str, args: dict) -> str:
    """Return a short, human-friendly description of a Hermes tool call."""
    return f"hermes:{name}({', '.join(f'{k}={v!r}' for k, v in args.items())})"


# ---------------------------------------------------------------------------
# Low-level runner
# ---------------------------------------------------------------------------


async def _run_hermes(
    ctx: RunContext[Any],
    args: list[str],
    timeout: int = 120,
) -> dict:
    """Run a Hermes CLI command asynchronously and return a structured result."""
    if tracer:
        with tracer.start_as_current_span("hermes_cli") as span:
            span.set_attribute("hermes.args", " ".join(args))
            hermes_path = _resolve_hermes_path(ctx)
            span.set_attribute("hermes.path", str(hermes_path))

            hermes_path = _resolve_hermes_path(ctx)
            cmd = _hermes_cli_cmd(hermes_path) + args

            if not _hermes_available(hermes_path):
                return {
                    "success": False,
                    "error": f"Hermes not found at {hermes_path}. Set HERMES_PATH or install Hermes.",
                    "stdout": "",
                    "stderr": "",
                }

            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    cwd=str(hermes_path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
                return {
                    "success": proc.returncode == 0,
                    "returncode": proc.returncode,
                    "stdout": stdout.decode("utf-8", errors="replace"),
                    "stderr": stderr.decode("utf-8", errors="replace"),
                    "command": " ".join(cmd),
                }
            except asyncio.TimeoutError:
                return {
                    "success": False,
                    "error": f"Timeout after {timeout}s",
                    "command": " ".join(cmd),
                }
            except Exception as exc:
                return {"success": False, "error": str(exc), "command": " ".join(cmd)}
    else:
        hermes_path = _resolve_hermes_path(ctx)
        cmd = _hermes_cli_cmd(hermes_path) + args

        if not _hermes_available(hermes_path):
            return {
                "success": False,
                "error": f"Hermes not found at {hermes_path}. Set HERMES_PATH or install Hermes.",
                "stdout": "",
                "stderr": "",
            }

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(hermes_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return {
                "success": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout": stdout.decode("utf-8", errors="replace"),
                "stderr": stderr.decode("utf-8", errors="replace"),
                "command": " ".join(cmd),
            }
        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": f"Timeout after {timeout}s",
                "command": " ".join(cmd),
            }
        except Exception as exc:
            return {"success": False, "error": str(exc), "command": " ".join(cmd)}


def _short_result(result: dict, max_chars: int = 4000) -> str:
    """Return a printable summary of a Hermes command result."""
    if not result.get("success"):
        return f"[hermes error] {result.get('error') or result.get('stderr', '').strip()[:500]}"
    out = result.get("stdout", "").strip()
    if not out:
        out = result.get("stderr", "").strip() or "(no output)"
    if len(out) > max_chars:
        out = out[:max_chars] + f"... ({len(out) - max_chars} more chars)"
    return out


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


async def hermes_chat_tool(ctx: RunContext[Any], message: str, timeout: int = 180) -> str:
    """Send a message to the Hermes agent and return its reply.

    Args:
        ctx: pydantic-ai run context (auto-injected).
        message: Natural language message to send to Hermes.
        timeout: Maximum seconds to wait for a response.

    Returns:
        Hermes' response text (or a structured error).
    """
    if tracer:
        with tracer.start_as_current_span("hermes_chat") as span:
            span.set_attribute("hermes.message_length", len(message))
            result = await _run_hermes(ctx, ["--oneshot", message], timeout=timeout)
    else:
        result = await _run_hermes(ctx, ["--oneshot", message], timeout=timeout)
    return _short_result(result)


async def hermes_model_list_tool(ctx: RunContext[Any]) -> str:
    """List the models available to the Hermes agent."""
    result = await _run_hermes(ctx, ["models", "list"], timeout=30)
    return _short_result(result)


async def hermes_model_switch_tool(ctx: RunContext[Any], model: str) -> str:
    """Switch the active Hermes model (e.g. ``openrouter:anthropic/claude-3-opus``).

    Args:
        model: Provider/model string accepted by Hermes' ``/model`` command.
    """
    result = await _run_hermes(ctx, ["model", model], timeout=30)
    return _short_result(result)


async def hermes_gateway_status_tool(ctx: RunContext[Any]) -> str:
    """Return the current status of the Hermes messaging gateway."""
    result = await _run_hermes(ctx, ["gateway", "status"], timeout=30)
    return _short_result(result)


async def hermes_gateway_start_tool(ctx: RunContext[Any]) -> str:
    """Start the Hermes messaging gateway (Telegram, Discord, Slack, ...)."""
    result = await _run_hermes(ctx, ["gateway", "start"], timeout=30)
    return _short_result(result)


async def hermes_gateway_stop_tool(ctx: RunContext[Any]) -> str:
    """Stop the Hermes messaging gateway."""
    result = await _run_hermes(ctx, ["gateway", "stop"], timeout=30)
    return _short_result(result)


async def hermes_skills_list_tool(ctx: RunContext[Any]) -> str:
    """List all Hermes skills available locally and via the Skills Hub."""
    result = await _run_hermes(ctx, ["skills", "list"], timeout=30)
    return _short_result(result)


async def hermes_skill_install_tool(ctx: RunContext[Any], skill_name: str) -> str:
    """Install a skill from the Hermes Skills Hub.

    Args:
        skill_name: Name of the skill to install.
    """
    result = await _run_hermes(ctx, ["skills", "install", skill_name], timeout=120)
    return _short_result(result)


async def hermes_skill_create_tool(ctx: RunContext[Any], name: str, description: str) -> str:
    """Create a new Hermes skill with the given name and description.

    Args:
        name: Skill name (kebab-case preferred).
        description: One-paragraph description of what the skill does.
    """
    result = await _run_hermes(
        ctx, ["skills", "create", name, "--description", description], timeout=60
    )
    return _short_result(result)


async def hermes_memory_query_tool(ctx: RunContext[Any], query: str) -> str:
    """Query Hermes' persistent memory for the given natural-language query.

    Args:
        query: Natural-language question to search Hermes memory.
    """
    result = await _run_hermes(ctx, ["memory", "query", query], timeout=30)
    return _short_result(result)


async def hermes_memory_add_tool(ctx: RunContext[Any], entry: str) -> str:
    """Add a new entry to Hermes' persistent memory.

    Args:
        entry: Markdown / natural-language memory entry.
    """
    result = await _run_hermes(ctx, ["memory", "add", entry], timeout=30)
    return _short_result(result)


async def hermes_cron_list_tool(ctx: RunContext[Any]) -> str:
    """List all configured Hermes cron jobs."""
    result = await _run_hermes(ctx, ["cron", "list"], timeout=30)
    return _short_result(result)


async def hermes_cron_add_tool(ctx: RunContext[Any], schedule: str, command: str) -> str:
    """Schedule a new Hermes cron job.

    Args:
        schedule: Cron-style schedule expression (e.g. ``0 9 * * *``).
        command: Hermes command (or natural language prompt) to run.
    """
    result = await _run_hermes(ctx, ["cron", "add", schedule, command], timeout=30)
    return _short_result(result)


async def hermes_cron_remove_tool(ctx: RunContext[Any], job_id: str) -> str:
    """Remove a Hermes cron job by its id.

    Args:
        job_id: Identifier of the cron job to remove.
    """
    result = await _run_hermes(ctx, ["cron", "remove", job_id], timeout=30)
    return _short_result(result)


async def hermes_kanban_list_tool(ctx: RunContext[Any]) -> str:
    """List Hermes kanban boards."""
    result = await _run_hermes(ctx, ["kanban", "list"], timeout=30)
    return _short_result(result)


async def hermes_kanban_create_tool(ctx: RunContext[Any], name: str) -> str:
    """Create a new Hermes kanban board.

    Args:
        name: Name of the new board.
    """
    result = await _run_hermes(ctx, ["kanban", "create", name], timeout=30)
    return _short_result(result)


async def hermes_kanban_task_add_tool(
    ctx: RunContext[Any], board: str, title: str, description: str = ""
) -> str:
    """Add a task to a Hermes kanban board.

    Args:
        board: Board name or id.
        title: Short task title.
        description: Optional longer description.
    """
    args = ["kanban", "add", board, title]
    if description:
        args += ["--description", description]
    result = await _run_hermes(ctx, args, timeout=30)
    return _short_result(result)


async def hermes_session_list_tool(ctx: RunContext[Any], limit: int = 10) -> str:
    """List recent Hermes sessions.

    Args:
        limit: Maximum number of sessions to return.
    """
    result = await _run_hermes(ctx, ["session", "list", "--limit", str(limit)], timeout=30)
    return _short_result(result)


async def hermes_session_recap_tool(ctx: RunContext[Any], session_id: str) -> str:
    """Get a recap / summary of a specific Hermes session.

    Args:
        session_id: Session id to summarize.
    """
    result = await _run_hermes(ctx, ["session", "recap", session_id], timeout=60)
    return _short_result(result)


async def hermes_config_get_tool(ctx: RunContext[Any], key: str) -> str:
    """Get a Hermes config value.

    Args:
        key: Dot-notation config key (e.g. ``model.default``).
    """
    result = await _run_hermes(ctx, ["config", "get", key], timeout=30)
    return _short_result(result)


async def hermes_config_set_tool(ctx: RunContext[Any], key: str, value: str) -> str:
    """Set a Hermes config value.

    Args:
        key: Dot-notation config key.
        value: Value to set (string form; numbers / JSON literals are accepted).
    """
    result = await _run_hermes(ctx, ["config", "set", key, value], timeout=30)
    return _short_result(result)


async def hermes_doctor_tool(ctx: RunContext[Any]) -> str:
    """Run the ``hermes doctor`` diagnostics command."""
    result = await _run_hermes(ctx, ["doctor"], timeout=60)
    return _short_result(result)


# ---------------------------------------------------------------------------
# Tool registry (for orchestrator import)
# ---------------------------------------------------------------------------

HERMES_TOOLS = [
    hermes_chat_tool,
    hermes_model_list_tool,
    hermes_model_switch_tool,
    hermes_gateway_status_tool,
    hermes_gateway_start_tool,
    hermes_gateway_stop_tool,
    hermes_skills_list_tool,
    hermes_skill_install_tool,
    hermes_skill_create_tool,
    hermes_memory_query_tool,
    hermes_memory_add_tool,
    hermes_cron_list_tool,
    hermes_cron_add_tool,
    hermes_cron_remove_tool,
    hermes_kanban_list_tool,
    hermes_kanban_create_tool,
    hermes_kanban_task_add_tool,
    hermes_session_list_tool,
    hermes_session_recap_tool,
    hermes_config_get_tool,
    hermes_config_set_tool,
    hermes_doctor_tool,
]
