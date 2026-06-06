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

| Tool | Description |
|------|-------------|
| `hermes_chat` | Send message to Hermes agent, get response |
| `hermes_model_list` | List available models in Hermes |
| `hermes_model_switch` | Switch Hermes active model |
| `hermes_gateway_status` | Check Hermes gateway status |
| `hermes_gateway_start` | Start Hermes gateway |
| `hermes_gateway_stop` | Stop Hermes gateway |
| `hermes_skills_list` | List Hermes skills |
| `hermes_skill_install` | Install skill from Hermes Hub |
| `hermes_skill_create` | Create new Hermes skill |
| `hermes_memory_query` | Query Hermes memory |
| `hermes_memory_add` | Add memory to Hermes |
| `hermes_cron_list` | List Hermes cron jobs |
| `hermes_cron_add` | Add cron job to Hermes |
| `hermes_cron_remove` | Remove cron job |
| `hermes_kanban_list` | List kanban boards |
| `hermes_kanban_create` | Create kanban board |
| `hermes_kanban_task_add` | Add task to kanban |
| `hermes_session_list` | List Hermes sessions |
| `hermes_session_recap` | Get session summary |
| `hermes_config_get` | Get Hermes config value |
| `hermes_config_set` | Set Hermes config value |

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