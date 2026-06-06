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
        # New tools
        "hermes_tools_list_tool",
        "hermes_setup_tool",
        "hermes_update_tool",
        "hermes_portal_info_tool",
        "hermes_skills_browse_tool",
        "hermes_skills_hub_tool",
        "hermes_background_tool",
        "hermes_sessions_list_tool",
        "hermes_sessions_resume_tool",
        "hermes_personality_set_tool",
        "hermes_voice_status_tool",
        "hermes_voice_toggle_tool",
        "hermes_reasoning_set_tool",
        "hermes_usage_tool",
        "hermes_insights_tool",
        "hermes_compress_tool",
        "hermes_claw_migrate_tool",
        "hermes_status_tool",
        "hermes_mcp_list_tool",
        "hermes_mcp_serve_tool",
        "hermes_skills_export_tool",
        "hermes_skills_import_tool",
        "hermes_skills_sync_status_tool",
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


# ---------------------------------------------------------------------------
# Tests: Skills sync (Ferrox ↔ Hermes)
# ---------------------------------------------------------------------------


def test_sync_state_roundtrip(tmp_path):
    """SyncState should persist to JSON and reload cleanly."""
    # Use a tmp path as the state file
    import ferrox.skills.sync as sync_mod
    from ferrox.skills.sync import SyncRecord, SyncState

    orig = sync_mod._sync_state_file
    sync_mod._sync_state_file = lambda: tmp_path / "state.json"  # type: ignore[assignment]
    try:
        state = SyncState()
        state.add(
            SyncRecord(
                direction="export",
                skill="demo",
                source="/src",
                target="/dst",
                timestamp="2026-06-06T00:00:00Z",
                bytes=1234,
                status="ok",
            )
        )
        state.save()
        loaded = SyncState.load()
        assert len(loaded.records) == 1
        assert loaded.records[0].skill == "demo"
        assert loaded.records[0].bytes == 1234
    finally:
        sync_mod._sync_state_file = orig  # type: ignore[assignment]


def test_export_ferrox_skill_creates_hermes_skill(tmp_path):
    """export_ferrox_skill should copy SKILL.md and ensure frontmatter."""
    from ferrox.skills.sync import export_ferrox_skill

    # Ferrox skill source
    ferrox_skill = tmp_path / "ferrox_src" / "demo_skill"
    ferrox_skill.mkdir(parents=True)
    (ferrox_skill / "SKILL.md").write_text("# Demo skill body\n", encoding="utf-8")
    (ferrox_skill / "extra.txt").write_text("hello", encoding="utf-8")

    # Hermes target
    target = tmp_path / "hermes" / "demo_skill"

    # Patch SKILLS_DIR to point at our fake ferrox source
    import ferrox.skills.sync as sync_mod

    orig = sync_mod.SKILLS_DIR
    sync_mod.SKILLS_DIR = ferrox_skill.parent  # type: ignore[assignment]
    try:
        rec = export_ferrox_skill("demo_skill", target_dir=target)
        assert rec.status == "ok"
        assert (target / "SKILL.md").exists()
        assert (target / "extra.txt").exists()
        # Frontmatter was added
        text = (target / "SKILL.md").read_text(encoding="utf-8")
        assert text.startswith("---")
        assert "name: demo_skill" in text
    finally:
        sync_mod.SKILLS_DIR = orig  # type: ignore[assignment]


def test_export_missing_skill_records_error(tmp_path):
    """export_ferrox_skill should record an error when skill doesn't exist."""
    from ferrox.skills.sync import export_ferrox_skill

    rec = export_ferrox_skill("nonexistent", target_dir=tmp_path / "out")
    assert rec.status == "error"
    assert "not found" in rec.message.lower()


def test_import_hermes_skill_copies_into_ferrox(tmp_path):
    """import_hermes_skill should copy SKILL.md into the Ferrox skill tree."""
    from ferrox.skills.sync import import_hermes_skill

    # Hermes skill source
    hermes_skill = tmp_path / "hermes_src" / "remote_skill"
    hermes_skill.mkdir(parents=True)
    (hermes_skill / "SKILL.md").write_text(
        "---\nname: remote_skill\n---\n# remote\n", encoding="utf-8"
    )

    # Ferrox target
    ferrox_target = tmp_path / "ferrox_skills" / "remote_skill"

    import ferrox.skills.sync as sync_mod

    orig = sync_mod.SKILLS_DIR
    sync_mod.SKILLS_DIR = ferrox_target.parent  # type: ignore[assignment]
    orig_hermes = sync_mod._default_hermes_skills_dir
    sync_mod._default_hermes_skills_dir = lambda: hermes_skill.parent  # type: ignore[assignment]
    try:
        rec = import_hermes_skill("remote_skill")
        assert rec.status == "ok"
        assert (ferrox_target / "SKILL.md").exists()
    finally:
        sync_mod.SKILLS_DIR = orig  # type: ignore[assignment]
        sync_mod._default_hermes_skills_dir = orig_hermes  # type: ignore[assignment]


def test_format_records_empty():
    """format_records should return a friendly message for empty input."""
    from ferrox.skills.sync import format_records

    assert (
        "no sync" in format_records([]).lower() or "no sync history" in format_records([]).lower()
    )


def test_format_records_renders_table():
    """format_records should produce a header + rows."""
    from ferrox.skills.sync import format_records

    recs = [
        {
            "direction": "export",
            "skill": "demo",
            "source": "/a",
            "target": "/b",
            "timestamp": "2026-06-06T00:00:00Z",
            "bytes": 100,
            "status": "ok",
            "message": "",
        }
    ]
    out = format_records(recs)
    assert "direction" in out
    assert "export" in out
    assert "demo" in out


# ---------------------------------------------------------------------------
# Tests: chat tool uses correct CLI args
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_tool_uses_q_flag(monkeypatch):
    """hermes_chat_tool should call `hermes chat -q <message>`, not --oneshot."""
    from ferrox.agent import tools_hermes

    captured_args = []

    async def fake_run_hermes(ctx, args, timeout=120):
        captured_args.extend(args)
        return {"success": True, "stdout": "ok", "stderr": "", "returncode": 0}

    monkeypatch.setattr(tools_hermes, "_run_hermes", fake_run_hermes)
    monkeypatch.setattr(tools_hermes, "_hermes_available", lambda p: True)

    result = await tools_hermes.hermes_chat_tool(MockCtx(), "hello world")
    assert "ok" in result
    assert "chat" in captured_args
    assert "-q" in captured_args
    assert "hello world" in captured_args
    assert "--oneshot" not in captured_args


@pytest.mark.asyncio
async def test_chat_tool_with_model_override(monkeypatch):
    """When model is provided, hermes_chat_tool should pass --model."""
    from ferrox.agent import tools_hermes

    captured = []

    async def fake_run_hermes(ctx, args, timeout=120):
        captured.extend(args)
        return {"success": True, "stdout": "x", "stderr": "", "returncode": 0}

    monkeypatch.setattr(tools_hermes, "_run_hermes", fake_run_hermes)
    monkeypatch.setattr(tools_hermes, "_hermes_available", lambda p: True)

    await tools_hermes.hermes_chat_tool(MockCtx(), "ping", model="anthropic/claude-sonnet-4")
    assert "--model" in captured
    assert "anthropic/claude-sonnet-4" in captured
