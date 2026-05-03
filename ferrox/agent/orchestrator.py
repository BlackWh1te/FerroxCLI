import os
from dataclasses import dataclass
from datetime import datetime

from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models.ollama import OllamaModel

from ..exceptions import AgentError, ModelNotFoundError, NetworkError, ProviderError, TimeoutError
from ..modes import Mode
from .event_bus import AgentEvent, EventType, event_bus


@dataclass
class AgentDeps:
    mode: Mode
    config: "FerroxConfig"


# OpenTelemetry tracing imports
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

# Initialize tracer (setup provider, but skip console exporter for clean UI)
trace.set_tracer_provider(TracerProvider())
tracer = trace.get_tracer(__name__)
# span_processor = SimpleSpanProcessor(ConsoleSpanExporter())
# trace.get_tracer_provider().add_span_processor(span_processor)

_current_agent = None

from ..config import FerroxConfig
from ..skills.manager import SkillManager
from .subagents import delegate_task
from .tools_api import (
    api_diff_tool,
    api_history_tool,
    api_mock_tool,
    api_test_tool,
    openapi_parse_tool,
)
from .tools_browser import browse_url_tool, click_element_tool, extract_text_tool, screenshot_tool
from .tools_database import (
    db_migrate_tool,
    db_query_tool,
    db_schema_tool,
)
from .tools_git import (
    git_blame_tool,
    git_branch_tool,
    git_checkout_tool,
    git_commit_tool,
    git_diff_tool,
    git_log_tool,
    git_stash_tool,
    git_status_tool,
)
from .tools_pydantic import (
    brew_install_tool,
    cargo_install_tool,
    extract_article_content,
    fetch_url_tool,
    get_job_logs_tool,
    go_install_tool,
    kill_job_tool,
    list_directory_tool,
    list_jobs_tool,
    npm_install_tool,
    pip_install_tool,
    read_file_tool,
    run_background_tool,
    run_command_tool,
    search_code_tool,
    verify_response_quality,
    web_search_tool,
    webfetch_tool,
    write_file_tool,
)
from .tools_social import (
    check_account_health_tool,
    check_visibility_tool,
    delete_tweet_tool,
    get_mentions_tool,
    get_recent_posts_tool,
    get_trends_tool,
    like_tweet_tool,
    post_thread_tool,
    post_tweet_tool,
    retweet_tweet_tool,
    search_tweets_tool,
)

# MCP (Model Context Protocol) integration — browser automation, fetch, etc.
try:
    from pydantic_ai.mcp import MCPServerStdio
except Exception:
    MCPServerStdio = None


class FerroxAgent:
    def __init__(self, config: FerroxConfig, agent_id: str = "main", agent_role: str = "main"):
        global _current_agent
        self.config = config
        self.agent_id = agent_id
        self.agent_role = agent_role
        self.session_logs = []
        self.skill_manager = SkillManager()
        _current_agent = self

        # Activate skill if x_bot_expert role
        if agent_role == "x_bot_expert":
            self.skill_manager.activate_skill("x_bot")

        # Initial model setup
        model = self._get_model_from_config()

        # Build system prompt with optional skill injection
        base_prompt = (
            "You are Ferrox, a software engineering agent. You MUST use your available tools for every task. "
            "\n\n## TOOL USAGE RULES (FOLLOW STRICTLY)\n"
            "1. If the user asks about ANYTHING on the internet (news, games, GitHub, docs, APIs, websites): "
            "   FIRST call web_search(query, fetch_content=True) to get actual content, THEN extract and present specific information. "
            "2. For news/factual queries: Use web_search with fetch_content=True to get actual article content. "
            "   NEVER describe what a site is - always show the ACTUAL headlines, facts, dates, and content. "
            "3. Extract and present SPECIFIC information: headlines, dates, names, locations, numbers, quotes. "
            "4. Synthesize information from multiple sources - don't just list them. Create a coherent summary. "
            "5. If the user asks about local files or code: call read_file or list_directory tools. "
            "6. If the user asks to run a command or install something: call run_command or pip_install tools. "
            "7. For git operations (status, diff, commit, branch, checkout, log, stash, blame): use the git_* tools. "
            "8. For database operations (query, schema, migrate): use the db_* tools. Database queries are read-only by default. "
            "9. For API testing and HTTP operations: use the api_* tools (test, mock, openapi_parse, history, diff). "
            "10. NEVER guess, hallucinate, or make up facts. ALWAYS fetch real data with tools first. "
            "11. After using tools, summarize the results in plain English or markdown with clear structure. "
            "12. Do NOT return raw JSON unless the user explicitly asks for it. "
            f"\n\n## WEB SEARCH BEST PRACTICES\n"
            "- Use web_search(query, fetch_content=True) for news and factual queries\n"
            "- Extract ACTUAL content: headlines, facts, dates, quotes\n"
            "- Format news with clear sections: Headlines, Key Facts, Sources\n"
            "- Be specific: include dates, names, locations, numbers\n"
            "- Synthesize multiple sources into a coherent answer\n"
            "\n\n## SOCIAL / X (TWITTER) AUTOMATION TOOLS\n"
            "You are running inside FerroxCLI — an AI-powered terminal assistant with built-in X/Twitter automation.\n"
            "The user's X account may already be connected via '/x-login' (browser cookies).\n"
            "Unlike SaaS platforms that require Twitter Developer Portal + API Keys + OAuth 2.0,\n"
            "Ferrox uses browser cookie auth: just '/x-login', log in via browser, done. No dev account. No API keys. Free.\n"
            "When the user asks about X/Twitter, ALWAYS use the appropriate tool — NEVER give generic instructions.\n\n"
            "Available social tools and when to use them:\n"
            "- post_tweet_tool(text) — Use when user says 'post a tweet', 'tweet this', 'send a tweet', etc.\n"
            "- post_thread_tool(tweets: list[str]) — Use when user wants multiple connected tweets.\n"
            "- search_tweets_tool(query, max_results) — Use when user asks 'search X for...', 'find tweets about...'\n"
            "- check_account_health_tool() — Use when user asks 'how's my account', 'check my X status', 'how many followers', 'follower count', 'my X profile', 'account info'\n"
            "- get_trends_tool() — Use when user asks 'what's trending', 'show trends'\n"
            "- get_mentions_tool(max_results) — Use when user asks 'check my mentions', 'who mentioned me'\n"
            "- like_tweet_tool(tweet_id) — Use when user asks to like a specific tweet.\n"
            "- retweet_tweet_tool(tweet_id) — Use when user asks to retweet.\n"
            "- delete_tweet_tool(tweet_id) — Use when user asks to delete a tweet.\n"
            "- get_recent_posts_tool(max_results) — Use when user asks 'show my recent tweets'\n"
            "- check_visibility_tool() — Use when user asks if their account is shadowbanned.\n\n"
            "Important rules:\n"
            "- If user says 'post a tweet about AI' → IMMEDIATELY call post_tweet_tool with appropriate text.\n"
            "- If user says 'reply to my mentions' → FIRST get_mentions_tool, THEN decide replies.\n"
            "- If user says 'what's trending' → IMMEDIATELY call get_trends_tool.\n"
            "- If user asks about their account, followers, profile → IMMEDIATELY call check_account_health_tool.\n"
            "- NEVER ask the user to 'go to X.com' or 'log in manually' — Ferrox handles this via cookies.\n"
            "- If the user asks about connecting their X account, RECOMMEND '/x-login' first.\n"
            "- NEVER ask for API keys, bearer tokens, or OAuth credentials.\n"
            "- If NOT in SOCIAL mode but user asks about X/Twitter, call the tool anyway if cookies exist.\n"
            "  If it fails, tell user to run '/social start' first.\n\n"
            "When in SOCIAL mode (activated via /social start), the user's X account is already connected.\n"
            "You should proactively offer to use X tools when relevant.\n"
            f"\n\nYou are running on {os.name} ({'Windows' if os.name == 'nt' else 'Unix-like'}). "
            "Use OS-appropriate shell commands (e.g., 'dir' or 'cls' on Windows, 'ls' or 'clear' on Unix)."
            "\n\n## MCP (BROWSER / WEB) TOOLS\n"
            "If configured, you have access to external MCP servers for browser automation and web fetching.\n"
            "These tools appear automatically when MCP servers are enabled in ~/.ferrox/config.json.\n"
            "Common MCP tools include:\n"
            "- browser_navigate, browser_click, browser_type, browser_scroll — for real browser interaction\n"
            "- browser_screenshot — capture page state\n"
            "- browser_evaluate — run JavaScript in the page\n"
            "- fetch — pull any URL and get clean markdown content\n"
            "Use these when the user asks to 'open a browser', 'check a website', 'screenshot', or 'scrape'.\n"
            "MCP browser tools are ideal for content discovery (news, blogs, docs) to synthesize into tweets or posts."
        )

        # Inject skill content if active
        skill_prompt = self.skill_manager.get_active_skills_prompt()
        if skill_prompt:
            base_prompt += skill_prompt

        mcp_toolsets = self._build_mcp_toolsets()
        self._agent = Agent(
            model=model,
            system_prompt=base_prompt,
            toolsets=mcp_toolsets,
        )
        self._agent.tool(read_file_tool)
        self._agent.tool(write_file_tool)
        self._agent.tool(run_command_tool)
        self._agent.tool(list_directory_tool)
        self._agent.tool(search_code_tool)
        self._agent.tool(run_background_tool)
        self._agent.tool(list_jobs_tool)
        self._agent.tool(kill_job_tool)
        self._agent.tool(get_job_logs_tool)
        self._agent.tool(delegate_task)
        self._agent.tool(browse_url_tool)
        self._agent.tool(click_element_tool)
        self._agent.tool(screenshot_tool)
        self._agent.tool(extract_text_tool)
        self._agent.tool(pip_install_tool)
        self._agent.tool(npm_install_tool)
        self._agent.tool(cargo_install_tool)
        self._agent.tool(brew_install_tool)
        self._agent.tool(go_install_tool)
        self._agent.tool(fetch_url_tool)
        self._agent.tool(webfetch_tool)
        self._agent.tool(web_search_tool)
        self._agent.tool(extract_article_content)
        self._agent.tool(verify_response_quality)
        self._agent.tool(git_status_tool)
        self._agent.tool(git_diff_tool)
        self._agent.tool(git_commit_tool)
        self._agent.tool(git_branch_tool)
        self._agent.tool(git_checkout_tool)
        self._agent.tool(git_log_tool)
        self._agent.tool(git_stash_tool)
        self._agent.tool(git_blame_tool)
        self._agent.tool(db_query_tool)
        self._agent.tool(db_schema_tool)
        self._agent.tool(db_migrate_tool)
        self._agent.tool(api_test_tool)
        self._agent.tool(api_mock_tool)
        self._agent.tool(openapi_parse_tool)
        self._agent.tool(api_history_tool)
        self._agent.tool(api_diff_tool)
        # Social/X Bot tools
        self._agent.tool(check_account_health_tool)
        self._agent.tool(search_tweets_tool)
        self._agent.tool(post_tweet_tool)
        self._agent.tool(post_thread_tool)
        self._agent.tool(get_recent_posts_tool)
        self._agent.tool(check_visibility_tool)
        self._agent.tool(get_trends_tool)
        self._agent.tool(get_mentions_tool)
        self._agent.tool(like_tweet_tool)
        self._agent.tool(retweet_tweet_tool)
        self._agent.tool(delete_tweet_tool)

    def _build_mcp_toolsets(self):
        """Build MCPServerStdio instances from FerroxConfig.

        Returns a list of pydantic-ai toolsets that auto-manage MCP server lifecycle.
        On Windows/MINGW we resolve the full executable path to avoid PATH issues.
        """
        if not MCPServerStdio or not self.config.mcp_servers:
            return []

        toolsets = []
        import shutil

        for srv in self.config.mcp_servers:
            if not srv.enabled:
                continue

            cmd = srv.command
            # On Windows, try to resolve full path for npx/node common commands
            if os.name == "nt" and not os.path.isabs(cmd):
                resolved = shutil.which(cmd)
                if resolved:
                    cmd = resolved

            try:
                ts = MCPServerStdio(
                    command=cmd,
                    args=srv.args,
                    env=srv.env,
                    timeout=srv.timeout,
                    tool_prefix=srv.name,
                )
                toolsets.append(ts)
                self._log_thought(f"[MCP] Registered server '{srv.name}': {cmd} {' '.join(srv.args)}")
            except Exception as e:
                self._log_thought(f"[MCP] Skipped server '{srv.name}' due to error: {e}")

        return toolsets

    def _get_model_from_config(self, model_override=None):
        """Helper to get a pydantic-ai model object or string based on config"""
        active_provider = self.config.get_active_provider()
        if not active_provider:
            return "openai:gpt-4o"

        model_name = model_override or active_provider.default_model or "llama3.2:latest"

        # 1. Handle Ollama specifically (check for port 11434 or explicit type)
        if active_provider.type == "ollama" or (
            active_provider.base_url and "11434" in active_provider.base_url
        ):
            # pydantic-ai's OllamaModel uses OLLAMA_BASE_URL env var
            # It expects the OpenAI-compatible endpoint, usually ending in /v1
            base_url = active_provider.base_url or "http://localhost:11434/v1"
            if not base_url.endswith("/v1") and not base_url.endswith("/v1/"):
                base_url = base_url.rstrip("/") + "/v1"

            os.environ["OLLAMA_BASE_URL"] = base_url
            return OllamaModel(model_name=model_name)

        # 2. Handle Known Providers
        if active_provider.type == "openai" and not active_provider.base_url:
            return f"openai:{model_name}"
        if active_provider.type == "anthropic":
            return f"anthropic:{model_name}"

        # 3. Handle OpenAI-compatible (Custom) providers with base_url
        if active_provider.base_url:
            from pydantic_ai.models.openai import OpenAIChatModel
            from pydantic_ai.providers.openai import OpenAIProvider

            provider = OpenAIProvider(
                base_url=active_provider.base_url, api_key=active_provider.api_key or "no-key"
            )
            # Use OpenAIChatModel with custom provider for local/compatible endpoints
            return OpenAIChatModel(model_name, provider=provider)

        # Default to whatever pydantic-ai can infer or just the name
        return model_name

    def _convert_history(self, history: list) -> list[ModelMessage]:
        """Convert standard dict history to pydantic-ai ModelMessage objects"""
        pydantic_history = []
        for msg in history:
            role = msg.get("role")
            content = msg.get("content", "")

            if role == "user":
                pydantic_history.append(ModelRequest(parts=[UserPromptPart(content=content)]))
            elif role == "assistant":
                pydantic_history.append(ModelResponse(parts=[TextPart(content=content)]))
            elif role == "system":
                pydantic_history.append(ModelRequest(parts=[SystemPromptPart(content=content)]))

        return pydantic_history

    def _needs_web_search(self, prompt: str) -> tuple[bool, str]:
        """Detect if the user is asking about something that requires fresh web data.
        Only the FIRST line/paragraph of the prompt is checked — anything after
        [CURRENT_PROJECT_ROOT: or tool outputs is ignored.
        """
        import re

        # Strip any injected project context or tool outputs — only check the user's message
        user_message = prompt
        if "[CURRENT_PROJECT_ROOT:" in user_message:
            user_message = user_message.split("[CURRENT_PROJECT_ROOT:")[0]
        if "[WEB SEARCH RESULTS" in user_message:
            user_message = user_message.split("[WEB SEARCH RESULTS")[0]

        p = user_message.strip().lower()
        if not p or len(p) < 3:
            return False, ""

        # ── HIGH-CONFIDENCE explicit web commands ──
        explicit_patterns = [
            r"\bsearch\s+(?:the\s+)?(?:web|internet|online|google|duckduckgo|bing)\b",
            r"\bsearch\s+for\s+(.+)",
            r"\b(?:google|duckduckgo|bing|wiki|wikipedia)\s+(?:for\s+)?(.+)",
            r"\b(?:look\s+up|fetch|check\s+online|find\s+online)\s+(.+)",
            r"\b(?:tell\s+me\s+about|what\s+is|who\s+is|when\s+is)\s+(.+)",
            r"\b(?:latest|current|recent|today)\s+(?:news|update|version|release|price|weather|stock)\b",
            r"\b(?:news\s+about|weather\s+in|price\s+of|stock\s+price)\b",
            r"\b(?:github|reddit|twitter|youtube|stackoverflow)\b",
            r"\b(?:bitcoin|ethereum|crypto|nft)\b",
            r"\b(?:20(?:24|25|26|27|28))\b",  # future/past year references
        ]
        for pat in explicit_patterns:
            m = re.search(pat, p)
            if m:
                # Extract the query from the capture group if available, else whole message
                query = (
                    m.group(1).strip()
                    if m.lastindex
                    else re.sub(r'[?"\']', "", user_message).strip()
                )
                # Truncate query to reasonable length
                query = query[:200]
                return True, query

        # ── MEDIUM-CONFIDENCE: question-like phrasing about external topics ──
        # Only if the sentence starts with a question word
        question_starters = [
            "what is",
            "what's",
            "what are",
            "who is",
            "who's",
            "when is",
            "when was",
            "where is",
            "where was",
            "how do",
            "how does",
            "how can",
            "how to",
            "why is",
            "why does",
        ]
        first_sentence = re.split(r"[.!?\n]", p)[0].strip()
        for starter in question_starters:
            if first_sentence.startswith(starter):
                query = re.sub(r'[?"\']', "", first_sentence).strip()
                query = query[:200]
                return True, query

        return False, ""

    async def run(self, user_prompt: str, model_id: str, history: list, mode: Mode = Mode.NORMAL):
        # Start a tracing span for the agent execution
        with tracer.start_as_current_span("ferrox_agent_run") as span:
            # Record basic attributes
            span.set_attribute("model_id", model_id)
            span.set_attribute("prompt_length", len(user_prompt))

            try:
                self._log_thought(f"Starting task execution with model: {model_id}")
                self._log_thought(f"User prompt: {user_prompt[:100]}{'...' if len(user_prompt) > 100 else ''}")

                # Update model if it changed (model_id is usually type:name from cli.py)
                if ":" in model_id:
                    actual_model_name = model_id.split(":", 1)[1]
                    self._agent.model = self._get_model_from_config(actual_model_name)
                    self._log_thought(f"Switched to model: {actual_model_name}")

                # ── SOCIAL MODE: Inject X account context ──
                augmented_prompt = user_prompt
                if mode == Mode.SOCIAL:
                    augmented_prompt = (
                        "[SOCIAL MODE ACTIVE — user's X account is connected. "
                        "Use social tools directly when relevant. "
                        "Do NOT ask the user to 'go to X.com' or 'log in manually'.]\n\n"
                        + augmented_prompt
                    )

                # ── PRE-SEARCH: Local models often can't use tools reliably ──
                # Detect if the user wants web info and fetch it BEFORE calling the model
                needs_search, search_query = self._needs_web_search(user_prompt)

                if needs_search:
                    self._log_thought(f"Detected web query: '{search_query}' — initiating search")
                    try:
                        from ddgs import DDGS

                        self._log_thought(f"Calling DuckDuckGo search API for: '{search_query}'")
                        results = DDGS().text(search_query, max_results=5)

                        if results:
                            self._log_thought(f"Successfully retrieved {len(results)} search results")
                            # Log each result individually for real-time visibility
                            for idx, r in enumerate(results, 1):
                                title = r.get('title', 'No title')
                                url = r.get('href', '')
                                body = r.get('body', '')[:100] + '...' if len(r.get('body', '')) > 100 else r.get('body', '')
                                self._log_thought(f"Result {idx}: {title}")
                                self._log_thought(f"  URL: {url}")
                                self._log_thought(f"  Preview: {body}")

                            lines = [f"[WEB SEARCH RESULTS for '{search_query}']\n"]
                            for idx, r in enumerate(results, 1):
                                lines.append(f"{idx}. {r.get('title', 'No title')}")
                                lines.append(f"   URL: {r.get('href', '')}")
                                lines.append(f"   {r.get('body', '')}\n")
                            lines.append("[END SEARCH RESULTS]\n")
                            search_text = "\n".join(lines)
                            # Limit context size
                            max_len = 8000
                            if len(search_text) > max_len:
                                search_text = search_text[:max_len] + "\n\n... (truncated)"
                            augmented_prompt = (
                                f"{search_text}\n"
                                f"Based on the search results above, answer the user's question:\n{user_prompt}"
                            )
                            self._log_thought("Integrating search results into context for response generation")
                        else:
                            self._log_thought("No search results found - will proceed without web data")
                    except Exception as e:
                        self._log_thought(f"Pre-search failed: {e} - proceeding with original prompt")
                        # Continue with original prompt if search fails

                # Convert history to pydantic-ai format
                self._log_thought(f"Converting {len(history)} messages to pydantic-ai format")
                pydantic_history = self._convert_history(history)

                # Create deps for tools
                deps = AgentDeps(mode=mode, config=self.config)
                self._log_thought(f"Creating agent dependencies with mode: {mode.value}")

                self._log_thought("Invoking pydantic-ai agent for task execution")
                result = await self._agent.run(
                    augmented_prompt, message_history=pydantic_history, deps=deps
                )
                self._log_thought("Agent execution completed")

                # Robustly get result data
                if hasattr(result, "data"):
                    self._log_thought(f"Extracting result data (length: {len(str(result.data))} chars)")
                    return result.data
                elif hasattr(result, "message") and hasattr(result.message, "content"):
                    self._log_thought(f"Extracting message content (length: {len(result.message.content)} chars)")
                    return result.message.content
                else:
                    self._log_thought(f"Converting result to string (length: {len(str(result))} chars)")
                    return str(result)

            except ModelNotFoundError as e:
                span.set_attribute("error", f"Model not found: {e}")
                self._log_thought(f"Error: Model {model_id} not found")
                raise ProviderError(
                    f"Model '{model_id}' not found. Available models may have changed.",
                    {"model": model_id},
                )

            except TimeoutError as e:
                span.set_attribute("error", f"Timeout: {e}")
                self._log_thought("Error: Request timeout")
                raise TimeoutError("Agent request timed out", {"model": model_id})

            except Exception as e:
                error_type = type(e).__name__
                error_msg = str(e)
                span.set_attribute("error", f"{error_type}: {error_msg}")
                self._log_thought(f"Error: {error_type} - {error_msg}")

                # Re-raise as appropriate exception
                if "authentication" in error_msg.lower() or "api key" in error_msg.lower():
                    raise ProviderError(f"Authentication failed: {error_msg}", {"model": model_id})
                elif "rate limit" in error_msg.lower():
                    raise ProviderError(f"Rate limit exceeded: {error_msg}", {"model": model_id})
                elif "network" in error_msg.lower() or "connection" in error_msg.lower():
                    raise NetworkError(f"Network error: {error_msg}", {"model": model_id})
                else:
                    raise AgentError(f"Agent execution failed: {error_msg}", {"model": model_id})

    def _log(self, entry: dict):
        self.session_logs.append(entry)

    def _log_thought(self, content: str):
        self._log({"type": "thought", "content": content, "timestamp": datetime.now()})

        # Publish to event bus for real-time monitoring
        try:
            asyncio.create_task(event_bus.publish(AgentEvent(
                event_type=EventType.THOUGHT,
                agent_id=self.agent_id,
                agent_role=self.agent_role,
                timestamp=datetime.now(),
                data={"content": content}
            )))
        except Exception:
            pass  # Event bus might not be initialized

        # Real-time display of agent reasoning
        try:
            from ..ui.output import format_agent_thought
            format_agent_thought(content)
        except Exception:
            pass

    def _log_tool_call(self, name: str, args: dict):
        self._log({"type": "tool_call", "name": name, "args": args, "timestamp": datetime.now()})

        # Enhanced logging with detailed parameters
        args_summary = []
        for key, value in args.items():
            if isinstance(value, str) and len(value) > 100:
                value = value[:100] + "..."
            args_summary.append(f"{key}={value}")

        self._log_thought(f"Tool call: {name}({', '.join(args_summary)})")

        # Publish to event bus for real-time monitoring
        try:
            asyncio.create_task(event_bus.publish(AgentEvent(
                event_type=EventType.TOOL_CALL,
                agent_id=self.agent_id,
                agent_role=self.agent_role,
                timestamp=datetime.now(),
                data={"tool_name": name, "args": args, "args_summary": args_summary}
            )))
        except Exception:
            pass  # Event bus might not be initialized

        # Real-time display of tool calls
        try:
            from ..ui.output import format_tool_call
            format_tool_call(name, args)
        except Exception:
            pass

    def _log_tool_result(self, name: str, result: str, success: bool):
        self._log(
            {
                "type": "tool_result",
                "name": name,
                "content": result,
                "success": success,
                "timestamp": datetime.now(),
            }
        )

        # Enhanced logging with result details
        result_preview = result[:200] + "..." if len(result) > 200 else result
        status = "SUCCESS" if success else "FAILED"
        self._log_thought(f"Tool result: {name} -> {status} ({len(result)} chars)")
        self._log_thought(f"  Preview: {result_preview}")

        # Publish to event bus for real-time monitoring
        try:
            asyncio.create_task(event_bus.publish(AgentEvent(
                event_type=EventType.TOOL_RESULT,
                agent_id=self.agent_id,
                agent_role=self.agent_role,
                timestamp=datetime.now(),
                data={
                    "tool_name": name,
                    "content": result,
                    "success": success,
                    "result_preview": result_preview
                }
            )))
        except Exception:
            pass  # Event bus might not be initialized


def get_current_session_logs():
    return _current_agent.session_logs if _current_agent else []
