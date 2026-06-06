# Hermes Integration Skill

This skill provides integration between FerroxCLI and Hermes Agent (https://github.com/NousResearch/hermes-agent).

## Overview

Hermes Agent is a self-improving AI agent with:
- Persistent memory across sessions
- Skills system for procedural memory
- Multi-platform messaging gateway (Telegram, Discord, Slack, WhatsApp, Signal, Email)
- Cron scheduling for automated tasks
- Kanban task management
- MCP (Model Context Protocol) server support
- Tool gateway (web search, image generation, TTS, cloud browser)
- Subagent delegation for parallel work

## Integration Points

### 1. Hermes CLI Commands
Execute Hermes commands directly from FerroxCLI:
```python
# Chat with Hermes agent
result = await hermes_chat("Analyze this codebase and suggest improvements")

# Switch model
await hermes_model_switch("openrouter:claude-3-opus")

# Check gateway status
status = await hermes_gateway_status()
```

### 2. Hermes Gateway API (if running)
Connect to Hermes gateway for:
- Real-time messaging platform status
- Session management
- Cross-platform conversation sync

### 3. Skills Sync
- Export Ferrox skills to Hermes format
- Import Hermes skills to Ferrox
- Bidirectional skill sharing

### 4. Memory Integration
- Query Hermes persistent memory
- Share context between agents
- Cross-session recall

### 5. Kanban/Task Management
- Access Hermes kanban boards
- Create tasks from Ferrox
- Sync task status

## Available Tools

### Core
| Tool | Description |
|------|-------------|
| `hermes_chat` | Send a single query to Hermes (non-interactive) |
| `hermes_model_list` | List available models |
| `hermes_model_switch` | Switch active model |
| `hermes_status` | Show session / system status |
| `hermes_usage` | Token / cost breakdown |
| `hermes_insights` | Usage insights over N days |
| `hermes_compress` | Manually trigger context compression |
| `hermes_doctor` | Run diagnostics |
| `hermes_setup` | Run setup wizard (optionally `--portal`) |
| `hermes_update` | Self-update Hermes |
| `hermes_portal_info` | Show Nous Portal info |

### Gateway & platforms
| Tool | Description |
|------|-------------|
| `hermes_gateway_status` | Check gateway status |
| `hermes_gateway_start` | Start gateway |
| `hermes_gateway_stop` | Stop gateway |

### Skills
| Tool | Description |
|------|-------------|
| `hermes_skills_list` | List installed skills |
| `hermes_skills_browse` | Browse the Skills Hub |
| `hermes_skills_hub` | Generic hub action (browse / search / install) |
| `hermes_skill_install` | Install a skill from the Hub |
| `hermes_skill_create` | Create a new skill |
| `hermes_skills_export` | Export a Ferrox skill → Hermes layout |
| `hermes_skills_import` | Import a Hermes skill → Ferrox |
| `hermes_skills_sync_status` | Show sync history |

### Memory, Cron, Kanban
| Tool | Description |
|------|-------------|
| `hermes_memory_query` | Query persistent memory |
| `hermes_memory_add` | Add to memory |
| `hermes_cron_list` | List scheduled jobs |
| `hermes_cron_add` | Schedule a job |
| `hermes_cron_remove` | Remove a job |
| `hermes_kanban_list` | List kanban boards |
| `hermes_kanban_create` | Create a board |
| `hermes_kanban_task_add` | Add a task |

### Sessions
| Tool | Description |
|------|-------------|
| `hermes_sessions_list` | List recent sessions |
| `hermes_sessions_resume` | Resume a session by id |
| `hermes_session_list` | Legacy session list |
| `hermes_session_recap` | Get session summary |

### Config, Tools, Migration
| Tool | Description |
|------|-------------|
| `hermes_config_get` | Get config value |
| `hermes_config_set` | Set config value |
| `hermes_tools_list` | List active toolsets |
| `hermes_claw_migrate` | Migrate from OpenClaw |

### Personality, Voice, Reasoning
| Tool | Description |
|------|-------------|
| `hermes_personality_set` | Set active personality (e.g. `concise`, `pirate`) |
| `hermes_voice_status` | Show voice mode status |
| `hermes_voice_toggle` | Enable / disable voice mode |
| `hermes_reasoning_set` | Set reasoning effort (`low` / `medium` / `high`) |

### Background & MCP
| Tool | Description |
|------|-------------|
| `hermes_background` | Start a background agent session |
| `hermes_mcp_list` | List configured MCP servers |
| `hermes_mcp_serve` | Start Hermes as an MCP server |

## Configuration

Set `HERMES_PATH` environment variable or config option to point to Hermes installation:
- Default Windows: `%LOCALAPPDATA%\hermes\hermes-agent`
- Default Linux/macOS: `~/.hermes/hermes-agent`

Or set in Ferrox config:
```json
{
  "hermes_path": "C:/Users/Shukhrat/AppData/Local/hermes/hermes-agent"
}
```

## Usage Examples

### Chat with Hermes
```
/hermes chat "Review my Python code for security issues"
```

### Switch Model
```
/hermes model openrouter:gpt-4o
```

### Check Gateway
```
/hermes gateway status
```

### Sync Skills
```
/hermes skills sync
```

### Query Memory
```
/hermes memory "What did I work on last week?"
```

## Architecture

The integration uses subprocess calls to Hermes CLI for most operations.
For real-time features (gateway, streaming), it connects via HTTP/WebSocket to the Hermes gateway when running.

## Security

- All Hermes CLI commands run with user's permissions
- Gateway connections use local HTTP (no external exposure unless configured)
- No API keys shared between Ferrox and Hermes - each manages its own credentials