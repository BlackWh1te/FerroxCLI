# 🦊 Ferrox CLI

Ferrox is an autonomous, provider-agnostic AI engineering agent designed to run directly in your terminal. It combines the power of LLMs with local tool execution, permission-based security, and a Devin-style terminal interface.

## ✨ Core Features
- **Autonomous Agent Loop:** Features an `/fix` command that executes tests and auto-corrects code upon failure.
- **Resilient Fallbacks:** Automatically cascades requests across multiple LLM providers if the primary fails.
- **Provider Agnostic:** Supports OpenAI, Anthropic, Ollama, Groq, and any OpenAI-compatible endpoint.
- **Context Aware:** Uses a local symbol indexer (`/index`) to map your codebase for the AI.
- **Secure:** Scoped permission system ensures the agent asks before modifying files or running sensitive commands.
- **Devin-Style UI:** Responsive, non-blocking interface with a real-time status footer.
- **Trace Viewer:** Press `Ctrl+O` to see the agent's internal thoughts, tool calls, and results in real-time.
- **Enhanced Error Handling:** Comprehensive error handling with custom exceptions and recovery mechanisms.

## 🚀 Quick Start

1. **Installation:**
   ```bash
   pip install -e .
   ```

2. **Configuration:**
   ```bash
   ferrox /cfg
   ```
   *Edit the config to add your provider's `base_url` and `api_key`.*

3. **Initialization:**
   ```bash
   ferrox /index
   ```

4. **Start Chatting:**
   ```bash
   ferrox
   ```

## ⌨️ Command Reference

| Command | Action |
| :--- | :--- |
| `/fix <cmd>` | Starts an autonomous test/fix loop. |
| `/index` | Indexes project functions/classes for context. |
| `/status` | Displays health, quota, and system mode. |
| `/update` | Auto-updates Ferrox from the upstream repo. |
| `/cfg` | Opens configuration in your system editor. |
| `/model` | Lists and selects available LLM models. |

## ⌨️ Keyboard Shortcuts

| Shortcut | Action |
| :--- | :--- |
| `Ctrl+O` | Open Trace/Thinking Viewer - see agent's thoughts and tool execution |
| `Ctrl+L` | Clear screen |
| `Ctrl+R` | Refresh/Reset display |
| `Shift+Tab` | Cycle between Normal/Plan/Bypass modes |
| `Ctrl+G` | Open external editor for multi-line inputs |
| `Ctrl+C` | Exit Ferrox |
| `Esc` | Cancel current agent thinking |
| `Enter` | Submit message |

## 🔧 Tools Available

The pydantic-ai agent has access to the following tools:
- **read_file**: Read content from a text file
- **write_file**: Write content to a file
- **run_command**: Execute shell commands
- **list_directory**: List files and directories
- **search_code**: Search for symbol usage in codebase

## 🏗️ Architecture

- **pydantic-ai Integration:** Modern agent framework with structured tool definitions
- **OpenTelemetry Tracing:** Built-in observability for agent execution
- **Custom Exceptions:** Comprehensive error handling with specific exception types
- **Lazy Imports:** Optimized imports to avoid dependency conflicts

## 📁 Project Structure

```
ferrox/
├── agent/
│   ├── orchestrator.py     # pydantic-ai agent with tracing
│   ├── tools_pydantic.py   # Tool definitions
│   └── loop.py            # Autonomous fix loop
├── providers/
│   ├── config.py          # Provider configuration
│   └── registry.py        # Dynamic model discovery
├── ui/
│   ├── trace_viewer.py    # Trace/Thinking Viewer
│   └── ...
├── tools.py               # File system and shell tools
├── config.py              # Configuration management
├── cli.py                 # Entry point and chat controller
├── exceptions.py          # Custom exception classes
└── api.py                 # LLM API integration
```

## 📦 Dependencies

- **pydantic-ai** - Enhanced agent framework
- **instructor** - Structured output
- **langgraph** - Agent orchestration
- **mirascope** - LLM integration layer
- **opentelemetry** - Observability and tracing

## 🛠️ Development

### Environment Setup

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd FerroxCLI
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   # Install with development tools
   pip install -e ".[dev]"

   # Or install with browser support
   pip install -e ".[browser,dev]"
   ```

4. **Configure environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys and configuration
   ```

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=ferrox --cov-report=html

# Run specific test file
pytest tests/test_config.py

# Run with markers
pytest -m unit          # Run only unit tests
pytest -m integration   # Run only integration tests
pytest -m "not slow"     # Skip slow tests
```

### Code Quality

```bash
# Lint with ruff
ruff check ferrox/

# Format with ruff
ruff format ferrox/

# Type check with mypy
mypy ferrox/

# Security scan with bandit
bandit -r ferrox/

# Run all quality checks
ruff check ferrox/ && ruff format ferrox/ && mypy ferrox/ && bandit -r ferrox/
```

### Monitoring & Observability

**Sentry Integration:**
- Set `SENTRY_DSN` in `.env` to enable error tracking
- Errors are automatically captured and sent to Sentry
- Configure `SENTRY_ENVIRONMENT` for environment-specific tracking

**Prometheus Metrics:**
- Set `PROMETHEUS_PORT` in `.env` (default: 9090)
- Metrics are automatically exposed at `http://localhost:PROMETHEUS_PORT/metrics`
- Available metrics include:
  - `ferrox_agent_requests_total` - Total agent requests
  - `ferrox_agent_request_duration_seconds` - Request duration
  - `ferrox_tool_calls_total` - Tool call counts
  - `ferrox_tokens_used_total` - Token usage
  - `ferrox_errors_total` - Error counts

### AI Enhancements

**Semantic Search:**
- Uses sentence-transformers for code understanding
- FAISS for fast vector similarity search
- Can be used for intelligent code context retrieval

**Official SDK Integration:**
- OpenAI SDK: `ferrox.providers.openai_sdk.OpenAISDKProvider`
- Anthropic SDK: `ferrox.providers.anthropic_sdk.AnthropicSDKProvider`
- Use these for more reliable API interactions

---

Built with passion for autonomous engineering. 🦊🚀