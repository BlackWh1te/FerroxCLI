"""Tests for the Hermes Agent integration tools."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class MockCtx:
    """Minimal mock for pydantic-ai RunContext."""

    def __init__(self, deps: object | None = None) -> None:
        self.deps = deps


class MockDeps:
    def __init__(self, hermes_path: str | None = None) -> None:
        self.hermes_path = hermes_path


# ---------------------------------------------------------------------------
# Tests: discovery helpers
# ---------------------------------------------------------------------------


def test_default_hermes_path_windows(monkeypatch):
    """On Windows, default path should be %LOCALAPPDATA%/hermes/hermes-agent."""
    monkeypatch.setattr("os.name", "nt")
    monkeypatch.setattr("os.environ", {"LOCALAPPDATA": "C:\\Users\\Test\\AppData\\Local"})

    # Reimport to pick up monkeypatched values
    if "ferrox.agent.tools_hermes" in sys.modules:
        del sys.modules["ferrox.agent.tools_hermes"]
    from ferrox.agent.tools_hermes import _default_hermes_path

    p = _default_hermes_path()
    assert isinstance(p, Path)
    assert "hermes" in str(p)


def test_resolve_hermes_path_env(monkeypatch):
    """HERMES_PATH env var wins over defaults and config."""
    monkeypatch.setenv("HERMES_PATH", "/custom/hermes/path")

    if "ferrox.agent.tools_hermes" in sys.modules:
        del sys.modules["ferrox.agent.tools_hermes"]
    from ferrox.agent.tools_hermes import _resolve_hermes_path

    p = _resolve_hermes_path()
    assert str(p).replace("\\", "/") == "/custom/hermes/path"


def test_resolve_hermes_path_from_config(monkeypatch):
    """If env var is missing, config value should be used."""
    monkeypatch.delenv("HERMES_PATH", raising=False)

    from ferrox.agent.tools_hermes import _resolve_hermes_path

    # The function looks for ctx.deps.config.hermes_path
    fake_config = MagicMock()
    fake_config.hermes_path = "/from/config"
    ctx = MagicMock()
    ctx.deps.config = fake_config
    p = _resolve_hermes_path(ctx)
    assert str(p).replace("\\", "/") == "/from/config"


def test_hermes_available_when_cli_exists(tmp_path):
    """_hermes_available returns True when cli.py exists in hermes path."""
    (tmp_path / "cli.py").write_text("# fake")
    from ferrox.agent.tools_hermes import _hermes_available

    assert _hermes_available(tmp_path) is True


def test_hermes_unavailable_when_no_cli(tmp_path):
    """_hermes_available returns False when no cli.py and hermes not in PATH."""
    from ferrox.agent import tools_hermes

    original = tools_hermes.shutil.which
    tools_hermes.shutil.which = lambda _: None
    try:
        assert tools_hermes._hermes_available(tmp_path) is False
    finally:
        tools_hermes.shutil.which = original


# ---------------------------------------------------------------------------
# Tests: tool surface
# ---------------------------------------------------------------------------


def test_all_hermes_tools_have_docstrings():
    """Every public tool should have a docstring for the agent."""
    from ferrox.agent import tools_hermes

    for tool in tools_hermes.HERMES_TOOLS:
        assert tool.__doc__, f"Tool {tool.__name__} is missing a docstring"


def test_hermes_tools_count():
    """We expect at least 20 Hermes tools registered."""
    from ferrox.agent.tools_hermes import HERMES_TOOLS

    assert len(HERMES_TOOLS) >= 20


def test_specific_tools_exposed():
    """All the documented integration points should be present."""
    from ferrox.agent import tools_hermes

    expected = [
        "hermes_chat_tool",
        "hermes_model_list_tool",
        "hermes_model_switch_tool",
        "hermes_gateway_status_tool",
        "hermes_gateway_start_tool",
        "hermes_gateway_stop_tool",
        "hermes_skills_list_tool",
        "hermes_skill_install_tool",
        "hermes_skill_create_tool",
        "hermes_memory_query_tool",
        "hermes_memory_add_tool",
        "hermes_cron_list_tool",
        "hermes_cron_add_tool",
        "hermes_cron_remove_tool",
        "hermes_kanban_list_tool",
        "hermes_kanban_create_tool",
        "hermes_kanban_task_add_tool",
        "hermes_session_list_tool",
        "hermes_session_recap_tool",
        "hermes_config_get_tool",
        "hermes_config_set_tool",
        "hermes_doctor_tool",
    ]
    exposed = {t.__name__ for t in tools_hermes.HERMES_TOOLS}
    missing = [name for name in expected if name not in exposed]
    assert not missing, f"Missing tools: {missing}"


# ---------------------------------------------------------------------------
# Tests: _run_hermes behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_hermes_success(monkeypatch):
    """_run_hermes should return success=True on exit code 0."""
    from ferrox.agent import tools_hermes

    fake_proc = AsyncMock()
    fake_proc.communicate = AsyncMock(return_value=(b"ok", b""))
    fake_proc.returncode = 0

    async def fake_exec(*args, **kwargs):
        return fake_proc

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)
    monkeypatch.setattr(tools_hermes, "_hermes_available", lambda p: True)

    ctx = MockCtx()
    result = await tools_hermes._run_hermes(ctx, ["--help"], timeout=5)
    assert result["success"] is True
    assert "ok" in result["stdout"]


@pytest.mark.asyncio
async def test_run_hermes_missing():
    """_hermes_available=False should short-circuit with a clean error."""
    from ferrox.agent import tools_hermes

    monkey = pytest.MonkeyPatch()
    try:
        monkey.setattr(tools_hermes, "_hermes_available", lambda p: False)
        ctx = MockCtx()
        result = await tools_hermes._run_hermes(ctx, ["anything"], timeout=5)
        assert result["success"] is False
        assert "not found" in result["error"].lower() or "Hermes" in result["error"]
    finally:
        monkey.undo()


# ---------------------------------------------------------------------------
# Tests: short-result formatting
# ---------------------------------------------------------------------------


def test_short_result_truncates_long_output():
    """_short_result should truncate very long stdout with an ellipsis."""
    from ferrox.agent.tools_hermes import _short_result

    long = "x" * 10_000
    out = _short_result({"success": True, "stdout": long, "stderr": ""}, max_chars=100)
    assert "more chars" in out
    assert len(out) < 500


def test_short_result_handles_error():
    """_short_result should report errors clearly."""
    from ferrox.agent.tools_hermes import _short_result

    out = _short_result({"success": False, "error": "boom"})
    assert "[hermes error]" in out
    assert "boom" in out


# ---------------------------------------------------------------------------
# Tests: orchestrator registration
# ---------------------------------------------------------------------------


def test_orchestrator_imports_hermes_tools():
    """The orchestrator module should import the Hermes tool functions."""
    # Just importing the orchestrator should not raise
    from ferrox.agent import orchestrator

    # The Hermes tools should be bound to module-level names
    for name in (
        "hermes_chat_tool",
        "hermes_gateway_status_tool",
        "hermes_skills_list_tool",
        "hermes_memory_query_tool",
        "hermes_cron_list_tool",
        "hermes_kanban_list_tool",
    ):
        assert hasattr(orchestrator, name), f"orchestrator missing {name}"


# ---------------------------------------------------------------------------
# Tests: skill registration
# ---------------------------------------------------------------------------


def test_hermes_skill_loadable():
    """The hermes_integration skill should be discoverable by SkillManager."""
    from ferrox.skills.manager import list_skills

    skills = list_skills()
    assert "hermes_integration" in skills


def test_hermes_skill_metadata():
    """Skill loader should return a populated metadata dict for Hermes."""
    from ferrox.skills.manager import load_skill

    meta = load_skill("hermes_integration")
    assert meta["exists"] is True
    assert meta["content"]
    assert "Hermes" in meta["content"]
