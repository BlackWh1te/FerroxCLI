# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install for development
pip install -e ".[dev]"
pip install -e ".[browser,dev]"      # with browser automation support

# Run the CLI
ferrox                                # interactive chat (default)
ferrox config                         # open config editor
ferrox models                         # list available models
ferrox validate                       # validate configured providers

# Lint & format
ruff check ferrox/
ruff format ferrox/
mypy ferrox/
bandit -r ferrox/

# Test
pytest
pytest tests/test_config.py           # single file
pytest -m unit                        # by marker
pytest --cov=ferrox --cov-report=html # with coverage
```

## Architecture

FerroxCLI is an autonomous AI engineering agent (Devin-style) for the terminal. It wraps pydantic-ai with a multi-provider LLM backend, permission system, and rich TUI.

### Entry Point & Chat Loop

`ferrox/cli.py::main()` → `start()` → `start_chat_loop()` (async)

The loop: reads input → parses slash commands or delegates to `FerroxAgent.run()` → executes tools → formats output. Special commands: `/fix`, `/index`, `/plan`, `/jobs`, `/status`, `/verbose`, `/metrics`.

### Core Data Flow

```
User input
  → FerroxAgent.run()          [ferrox/agent/orchestrator.py] — pydantic-ai wrapper
      → pydantic-ai auto tool-calling
      → tool implementations   [ferrox/agent/tools_*.py]
      → PermissionEngine check [ferrox/permissions.py]
  → response formatted & displayed
```

Fallback path: if primary provider fails, `FallbackEngine` (`ferrox/fallback.py`) cascades to next configured provider.

### Major Modules

| Module | Role |
|--------|------|
| `ferrox/config.py` | `FerroxConfig` + `ProviderConfig` — loads/saves `~/.ferrox/config.json` |
| `ferrox/api.py` | Raw LLM calls — `send_message()`, `send_message_with_tool_loop()`, `fetch_models()` |
| `ferrox/cli.py` | CLI commands (Click), chat loop, command dispatch |
| `ferrox/modes.py` | `Mode` enum: NORMAL / PLAN / EDIT / BYPASS — controls auto-approve level |
| `ferrox/permissions.py` | `PermissionEngine` — guards file/shell access per mode and scope |
| `ferrox/tools.py` | Legacy `execute_tool()` dispatcher (used by api.py path) |
| `ferrox/fallback.py` | Provider cascade on auth/network errors |
| `ferrox/agent/orchestrator.py` | `FerroxAgent` — pydantic-ai `Agent` with 20+ registered tools |
| `ferrox/agent/loop.py` | `AgentLoop` — test-driven autonomous fix loop for `/fix <cmd>` |
| `ferrox/agent/tools_pydantic.py` | File ops, shell, web search — core tool set |
| `ferrox/agent/tools_browser.py` | Browser automation (optional dep) |
| `ferrox/agent/tools_git.py` | git status/commit/diff/etc. |
| `ferrox/agent/tools_database.py` | DB query/schema/migrate |
| `ferrox/agent/event_bus.py` | `EventBus` — streams thoughts/tool events for `/verbose`, `/metrics` |
| `ferrox/providers/registry.py` | Dynamic model discovery with 1-hour cache |
| `ferrox/utils/memory.py` | Token counting + history compression (threshold: 32k tokens) |
| `ferrox/utils/indexer.py` | Symbol indexer for `/index` |

### MCP (Model Context Protocol) Servers

Ferrox can connect to external MCP servers via pydantic-ai's native `MCPServerStdio` support (v1.89+).
This enables browser automation, web fetching, and any third-party MCP tool without custom bridges.

**How it works:**
- MCP servers are configured in `~/.ferrox/config.json` under `mcp_servers`
- `FerroxAgent` builds `MCPServerStdio` instances from config and passes them as `toolsets=` to `Agent()`
- pydantic-ai auto-starts servers on `agent.run()` and stops them after — no manual lifecycle needed

**Recommended servers for X/Reddit bot content pipeline:**
- **Playwright MCP** (`npx -y @playwright/mcp@latest`) — real browser navigation, clicking, screenshots, JS evaluation
- **Fetch MCP** (`pip install mcp-server-fetch` / `uvx mcp-server-fetch`) — pull any URL as markdown

**Example config:**
```json
{
  "mcp_servers": [
    {
      "name": "playwright",
      "command": "npx",
      "args": ["-y", "@playwright/mcp@latest"],
      "timeout": 30,
      "enabled": true
    },
    {
      "name": "fetch",
      "command": "uvx",
      "args": ["mcp-server-fetch"],
      "timeout": 15,
      "enabled": true
    }
  ]
}
```

**Tool naming:** `tool_prefix` is set to the server `name`, so Playwright tools appear as e.g. `playwright:browser_navigate`.

**Windows/MINGW note:** The bridge resolves `npx`/`uvx` via `shutil.which()` automatically. If Node.js is not in PATH, the agent logs a warning and skips the server.

### Two Tool Systems

There are two parallel tool execution paths — be aware of both:

1. **Legacy** (`ferrox/api.py` + `ferrox/tools.py`): `execute_tool(name, args)` dispatcher, used in the streaming `send_message_with_tool_loop()` path.
2. **Modern** (`ferrox/agent/orchestrator.py` + `ferrox/agent/tools_*.py`): pydantic-ai `@agent.tool()` decorated async functions, used by `FerroxAgent.run()`.

New tools should be added to the pydantic-ai path.

### Mode System

Modes control how the permission engine responds to file write and shell execution requests:

- **NORMAL** (`●`): ask before write/exec
- **PLAN** (`◎`): shell allowed, write asks
- **EDIT** (`✎`): scoped edits, shell asks
- **BYPASS** (`⚡`): auto-approve all

Toggle with `Shift+Tab` or `/normal`, `/plan`, `/edit`, `/bypass`.

### Configuration

- Config file: `~/.ferrox/config.json`
- Model cache: `~/.ferrox/model_cache.json` (1-hour TTL)
- Env vars: `OLLAMA_BASE_URL`, `FERROX_TIMEOUT`, `FERROX_MAX_TOKENS`, `SENTRY_DSN`, `PROMETHEUS_PORT`
- Supported providers: OpenAI, Anthropic, Ollama, LM-Studio, vLLM, any OpenAI-compatible endpoint
- MCP servers: configured in `~/.ferrox/config.json` under `mcp_servers` (see MCP section above). Requires Node.js (for `npx`) or `uv`/`uvx` on the host.

### Observability (optional)

OpenTelemetry spans, Sentry error tracking, and Prometheus metrics are opt-in. The `EventBus` is always active and feeds the in-session `/verbose`, `/metrics`, and `Ctrl+O` trace viewer.
