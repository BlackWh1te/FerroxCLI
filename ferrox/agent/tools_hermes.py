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


async def hermes_chat_tool(
    ctx: RunContext[Any],
    message: str,
    model: str | None = None,
    timeout: int = 180,
) -> str:
    """Send a single query to the Hermes agent and return its reply.

    Uses Hermes' non-interactive mode: ``hermes chat -q "<message>"``.

    Args:
        ctx: pydantic-ai run context (auto-injected).
        message: Natural language message to send to Hermes.
        model: Optional model override (e.g. ``anthropic/claude-sonnet-4``).
        timeout: Maximum seconds to wait for a response.

    Returns:
        Hermes' response text (or a structured error).
    """
    args = ["chat", "-q", message]
    if model:
        args += ["--model", model]
    if tracer:
        with tracer.start_as_current_span("hermes_chat") as span:
            span.set_attribute("hermes.message_length", len(message))
            span.set_attribute("hermes.model", model or "(default)")
            result = await _run_hermes(ctx, args, timeout=timeout)
    else:
        result = await _run_hermes(ctx, args, timeout=timeout)
    return _short_result(result)


async def hermes_model_list_tool(ctx: RunContext[Any]) -> str:
    """List the models available to the Hermes agent (``hermes model``)."""
    result = await _run_hermes(ctx, ["model"], timeout=30)
    return _short_result(result)


async def hermes_model_switch_tool(ctx: RunContext[Any], model: str) -> str:
    """Switch the active Hermes model (e.g. ``anthropic/claude-sonnet-4``).

    Args:
        model: Provider/model string accepted by Hermes' ``hermes model <x>`` command.
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
# New tools (extended integration)
# ---------------------------------------------------------------------------


async def hermes_tools_list_tool(ctx: RunContext[Any]) -> str:
    """List Hermes tools and currently active toolsets."""
    result = await _run_hermes(ctx, ["tools"], timeout=30)
    return _short_result(result)


async def hermes_setup_tool(ctx: RunContext[Any], portal: bool = False) -> str:
    """Run the Hermes setup wizard.

    Args:
        portal: If True, run ``hermes setup --portal`` (use Nous Portal as provider).
    """
    args = ["setup"]
    if portal:
        args.append("--portal")
    result = await _run_hermes(ctx, args, timeout=120)
    return _short_result(result)


async def hermes_update_tool(ctx: RunContext[Any]) -> str:
    """Run ``hermes update`` to self-update the Hermes installation."""
    result = await _run_hermes(ctx, ["update"], timeout=180)
    return _short_result(result)


async def hermes_portal_info_tool(ctx: RunContext[Any]) -> str:
    """Show Nous Portal info (``hermes portal info``)."""
    result = await _run_hermes(ctx, ["portal", "info"], timeout=30)
    return _short_result(result)


async def hermes_skills_browse_tool(ctx: RunContext[Any]) -> str:
    """Browse the Hermes Skills Hub and official optional skills."""
    result = await _run_hermes(ctx, ["skills", "browse"], timeout=30)
    return _short_result(result)


async def hermes_skills_hub_tool(ctx: RunContext[Any], action: str = "list") -> str:
    """Interact with the Hermes Skills Hub (browse / install / search).

    Args:
        action: One of ``list``, ``browse``, ``search <query>``, ``install <name>``.
    """
    args = ["skills", "hub"]
    parts = action.split(maxsplit=1)
    sub = parts[0].lower()
    rest = parts[1] if len(parts) > 1 else ""
    if sub in ("browse", "list"):
        args.append("browse")
    elif sub == "search" and rest:
        args += ["search", rest]
    elif sub == "install" and rest:
        args += ["install", rest]
    else:
        return "Usage: hermes_skills_hub(action='browse|list|search <q>|install <name>')"
    result = await _run_hermes(ctx, args, timeout=60)
    return _short_result(result)


async def hermes_background_tool(ctx: RunContext[Any], prompt: str) -> str:
    """Start a Hermes background session with a prompt.

    Args:
        prompt: Natural language prompt to run in a background agent session.
    """
    result = await _run_hermes(ctx, ["chat", "-q", prompt, "--background"], timeout=60)
    return _short_result(result)


async def hermes_sessions_list_tool(ctx: RunContext[Any], limit: int = 20) -> str:
    """List recent Hermes CLI sessions (``hermes sessions list``).

    Args:
        limit: Maximum number of sessions to return.
    """
    result = await _run_hermes(ctx, ["sessions", "list", "--limit", str(limit)], timeout=30)
    return _short_result(result)


async def hermes_sessions_resume_tool(ctx: RunContext[Any], session_id: str) -> str:
    """Resume a Hermes session by id (``hermes --resume <id>``).

    Args:
        session_id: Session id to resume (from ``hermes_sessions_list``).
    """
    result = await _run_hermes(ctx, ["--resume", session_id, "-q", "resume"], timeout=60)
    return _short_result(result)


async def hermes_personality_set_tool(ctx: RunContext[Any], personality: str) -> str:
    """Set the active Hermes personality (e.g. ``concise``, ``pirate``, ``teacher``).

    Args:
        personality: Name of the personality to activate.
    """
    result = await _run_hermes(ctx, ["personality", personality], timeout=15)
    return _short_result(result)


async def hermes_voice_status_tool(ctx: RunContext[Any]) -> str:
    """Check Hermes voice mode / TTS status."""
    result = await _run_hermes(ctx, ["voice", "status"], timeout=15)
    return _short_result(result)


async def hermes_voice_toggle_tool(ctx: RunContext[Any], on: bool = True) -> str:
    """Toggle Hermes voice mode on or off.

    Args:
        on: True to enable voice mode, False to disable.
    """
    args = ["voice", "on" if on else "off"]
    result = await _run_hermes(ctx, args, timeout=15)
    return _short_result(result)


async def hermes_reasoning_set_tool(ctx: RunContext[Any], level: str) -> str:
    """Set Hermes reasoning effort.

    Args:
        level: One of ``low``, ``medium``, ``high`` (e.g. ``hermes /reasoning high``).
    """
    result = await _run_hermes(ctx, ["reasoning", level], timeout=15)
    return _short_result(result)


async def hermes_usage_tool(ctx: RunContext[Any]) -> str:
    """Show Hermes session usage / token breakdown."""
    result = await _run_hermes(ctx, ["usage"], timeout=15)
    return _short_result(result)


async def hermes_insights_tool(ctx: RunContext[Any], days: int = 7) -> str:
    """Show Hermes usage insights for the last N days.

    Args:
        days: Number of days to summarize (default 7).
    """
    result = await _run_hermes(ctx, ["insights", str(days)], timeout=30)
    return _short_result(result)


async def hermes_compress_tool(ctx: RunContext[Any]) -> str:
    """Manually trigger Hermes context compression for the current session."""
    result = await _run_hermes(ctx, ["compress"], timeout=60)
    return _short_result(result)


async def hermes_claw_migrate_tool(
    ctx: RunContext[Any], dry_run: bool = True, overwrite: bool = False
) -> str:
    """Migrate settings, memories, skills, and keys from OpenClaw.

    Args:
        dry_run: If True, only show what would be migrated (default True).
        overwrite: If True, overwrite conflicting files.
    """
    args = ["claw", "migrate"]
    if dry_run:
        args.append("--dry-run")
    if overwrite:
        args.append("--overwrite")
    result = await _run_hermes(ctx, args, timeout=120)
    return _short_result(result)


async def hermes_status_tool(ctx: RunContext[Any]) -> str:
    """Show Hermes session / system status (model, tokens, gateway, etc.)."""
    result = await _run_hermes(ctx, ["status"], timeout=15)
    return _short_result(result)


async def hermes_mcp_list_tool(ctx: RunContext[Any]) -> str:
    """List configured Hermes MCP servers."""
    result = await _run_hermes(ctx, ["mcp", "list"], timeout=15)
    return _short_result(result)


async def hermes_mcp_serve_tool(ctx: RunContext[Any], transport: str = "stdio") -> str:
    """Start the Hermes MCP server (so external clients can call Hermes).

    Args:
        transport: ``stdio`` (default) or ``sse`` / ``http``.
    """
    result = await _run_hermes(ctx, ["mcp", "serve", "--transport", transport], timeout=15)
    return _short_result(result)


# ---------------------------------------------------------------------------
# Skills sync (Ferrox ↔ Hermes)
# ---------------------------------------------------------------------------

from ..skills.sync import (  # noqa: E402
    export_ferrox_skill,
    format_records,
    import_hermes_skill,
    list_exported,
    sync_all,
)


async def hermes_skills_export_tool(ctx: RunContext[Any], skill_name: str = "") -> str:
    """Export a Ferrox skill into the Hermes skills directory.

    Args:
        skill_name: Name of the Ferrox skill to export. Empty = sync all.
    """

    if skill_name:
        rec = export_ferrox_skill(skill_name)
        return f"[{rec.status}] {rec.skill}: {rec.source} -> {rec.target} ({rec.bytes} bytes)"
    records = sync_all("export")
    return format_records([r.to_dict() if hasattr(r, "to_dict") else r.__dict__ for r in records])


async def hermes_skills_import_tool(ctx: RunContext[Any], skill_name: str = "") -> str:
    """Import a Hermes skill into the Ferrox skill tree.

    Args:
        skill_name: Name of the Hermes skill to import. Empty = sync all.
    """

    if skill_name:
        rec = import_hermes_skill(skill_name)
        return f"[{rec.status}] {rec.skill}: {rec.source} -> {rec.target} ({rec.bytes} bytes)"
    records = sync_all("import")
    return format_records([r.to_dict() if hasattr(r, "to_dict") else r.__dict__ for r in records])


async def hermes_skills_sync_status_tool(ctx: RunContext[Any]) -> str:
    """Show recent Ferrox ↔ Hermes skill sync history."""
    return format_records(list_exported())


# ---------------------------------------------------------------------------
# Tool registry (for orchestrator import)
# ---------------------------------------------------------------------------

HERMES_TOOLS = [
    # Core
    hermes_chat_tool,
    hermes_model_list_tool,
    hermes_model_switch_tool,
    hermes_status_tool,
    hermes_usage_tool,
    hermes_insights_tool,
    hermes_compress_tool,
    hermes_doctor_tool,
    hermes_setup_tool,
    hermes_update_tool,
    hermes_portal_info_tool,
    # Gateway & platforms
    hermes_gateway_status_tool,
    hermes_gateway_start_tool,
    hermes_gateway_stop_tool,
    # Skills
    hermes_skills_list_tool,
    hermes_skills_browse_tool,
    hermes_skills_hub_tool,
    hermes_skill_install_tool,
    hermes_skill_create_tool,
    # Memory
    hermes_memory_query_tool,
    hermes_memory_add_tool,
    # Cron
    hermes_cron_list_tool,
    hermes_cron_add_tool,
    hermes_cron_remove_tool,
    # Kanban
    hermes_kanban_list_tool,
    hermes_kanban_create_tool,
    hermes_kanban_task_add_tool,
    # Sessions
    hermes_sessions_list_tool,
    hermes_sessions_resume_tool,
    hermes_session_list_tool,
    hermes_session_recap_tool,
    # Config
    hermes_config_get_tool,
    hermes_config_set_tool,
    # Tools
    hermes_tools_list_tool,
    # Background
    hermes_background_tool,
    # Personality / voice / reasoning
    hermes_personality_set_tool,
    hermes_voice_status_tool,
    hermes_voice_toggle_tool,
    hermes_reasoning_set_tool,
    # Migration
    hermes_claw_migrate_tool,
    # MCP
    hermes_mcp_list_tool,
    hermes_mcp_serve_tool,
    # Skills sync (Ferrox ↔ Hermes)
    hermes_skills_export_tool,
    hermes_skills_import_tool,
    hermes_skills_sync_status_tool,
]
