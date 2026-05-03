"""Main CLI module for Ferrox"""

import os
import sys

# ── Windows console UTF-8 fix (must run before any emoji output) ──
if os.name == "nt":
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)  # UTF-8
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except Exception:
        pass
    # Also try to reconfigure stdout/stderr
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

import click

from .metrics import start_metrics_server

# Initialize monitoring and metrics
from .monitoring import init_sentry

# Initialize Sentry for error tracking
init_sentry()

# Start Prometheus metrics server if enabled
if os.getenv("PROMETHEUS_ENABLED", "false").lower() == "true":
    start_metrics_server()

from .agent.agent_pool import initialize_agent_pool
from .agent.event_bus import EventType, event_bus
from .agent.loop import AgentLoop
from .agent.orchestrator import FerroxAgent
from .api import (
    APIError,
    fetch_models,
    validate_provider,
)
from .config import (
    CONFIG_FILE,
    FerroxConfig,
    ensure_config_dir,
    get_default_config,
    load_config,
    save_config,
    validate_config,
)
from .exceptions import (
    AuthenticationError,
    FerroxError,
    NetworkError,
    ProviderError,
    RateLimitError,
    TimeoutError,
    ToolExecutionError,
)
from .fallback import FallbackEngine  # Import FallbackEngine
from .logger import get_logger
from .metrics_realtime import realtime_metrics
from .modes import Mode, ModeManager
from .permissions import PermissionAction, PermissionEngine
from .ui_legacy import (
    console,
    display_error,
    display_models,
    display_success,
    display_system,
    display_warning,
    get_user_input,
)
from .utils.indexer import build_project_index

SESSION_STATE_FILE = Path.home() / ".ferrox" / "session_state.json"


class ChatSession:
    """Chat session manager with mode support"""

    def __init__(
        self, config: FerroxConfig, mode_manager: ModeManager, permission_engine: PermissionEngine
    ):
        self.config = config
        self.mode_manager = mode_manager
        self.permissions = permission_engine
        self.messages: list[dict] = []
        # Get current provider and model
        provider = config.get_active_provider()
        self.current_model = provider.default_model if provider else None
        self.current_provider = provider

    def add_message(self, role: str, content: str) -> None:
        """Add a message to history"""
        self.messages.append({"role": role, "content": content})

    def get_last_message(self) -> Optional[dict]:
        """Get the last message"""
        return self.messages[-1] if self.messages else None

    def update_last_message(self, content: str) -> None:
        """Update the last message content"""
        if self.messages:
            self.messages[-1]["content"] = content

    def check_file_access(
        self, filepath: str, action: PermissionAction = PermissionAction.READ
    ) -> bool:
        """Check if file access is allowed based on current mode"""
        result = self.permissions.check_access(filepath, action, self.mode_manager.current_mode)

        if result is True:
            return True
        if result is False:
            display_warning(f"Access denied in {self.mode_manager.current_mode.value} mode")
            return False

        prompt = self.permissions.get_ask_prompt(filepath, action)
        allowed, deny_always = ask_confirmation(prompt)

        if allowed:
            self.permissions.grant_access(filepath, persistent=False)
            return True
        else:
            if deny_always:
                self.permissions.deny_access(filepath, persistent=True)
            return False


def check_config() -> Optional[FerroxConfig]:
    """Check if config exists and is valid"""
    config = load_config()
    if config is None:
        display_warning("No configuration found.")
        console.print("Run [cyan]/cfg[/cyan] to set up your provider.\n")
        return None

    is_valid, error_msg = validate_config(config)
    if not is_valid:
        display_error(f"Configuration invalid: {error_msg}")
        console.print("Run [cyan]/cfg[/cyan] to fix the configuration.\n")
        return None

    return config


def open_config_editor() -> bool:
    """Open config file in editor"""
    ensure_config_dir()

    if not CONFIG_FILE.exists():
        default_config = get_default_config()
        save_config(default_config)
        display_success("Created default config file")

    editor = (
        os.environ.get("EDITOR")
        or os.environ.get("VISUAL")
        or ("notepad" if os.name == "nt" else ("code" if _command_exists("code") else "vim"))
    )

    try:
        subprocess.call([editor, str(CONFIG_FILE)])

        config = load_config()
        if config is None:
            display_error("Failed to load config after editing")
            return False

        is_valid, error_msg = validate_config(config)
        if not is_valid:
            display_error(f"Config validation failed: {error_msg}")
            return False

        display_success("Configuration saved")
        return True
    except Exception as e:
        display_error(f"Failed to open editor: {e}")
        return False


def _command_exists(cmd: str) -> bool:
    """Check if command exists"""
    try:
        subprocess.run(
            ["where" if os.name == "nt" else "which", cmd], capture_output=True, check=False
        )
        return True
    except Exception:
        return False


def list_models(config: FerroxConfig) -> bool:
    """List and select models"""
    try:
        display_system("Fetching models...")
        models = fetch_models(config)

        if not models:
            display_warning("No models found")
            return False

        provider = config.get_active_provider()
        current_model = provider.default_model if provider else ""
        provider_name = provider.name if provider else ""
        display_models(models, current_model=current_model, provider_name=provider_name)

        selection = console.input("\nSelect model number (or press Enter to cancel): ")
        if not selection.strip():
            return False

        try:
            idx = int(selection) - 1
            if 0 <= idx < len(models):
                provider = config.get_active_provider()
                if provider:
                    provider.default_model = models[idx].id
                    save_config(config)
                    display_success(f"Selected model: {provider.default_model}")
                return True
            else:
                display_error("Invalid selection")
                return False
        except ValueError:
            display_error("Invalid input")
            return False
    except APIError as e:
        display_error(e.message)
        return False


import asyncio
import os
import sys

from rich.console import Console

from .async_ui import create_prompt_session, get_user_input
from .config import FerroxConfig
from .logger_new import logger

console = Console()


async def start_chat_loop(config: FerroxConfig, no_animation: bool = False):
    """
    Main async chat loop using prompt_toolkit.
    """
    # Hardcoded Ferrox Crew banner (animation removed)
    from .ui.header import render_ferrox_crew_banner
    from .ui.output import _strip_wrapper_objects

    render_ferrox_crew_banner()

    # Check environment variables for features
    dashboard_enabled = os.getenv("FERROX_DASHBOARD", "false").lower() == "true"
    agent_pool_enabled = os.getenv("FERROX_AGENT_POOL", "false").lower() == "true"

    # Initialize event bus
    await event_bus.start()
    console.print("[dim]🔄 Event bus started[/dim]")

    # Initialize metrics collection
    await realtime_metrics.start()
    console.print("[dim]📊 Metrics collection started[/dim]")

    # Initialize agent pool if enabled
    if agent_pool_enabled:
        console.print("[dim]🔄 Initializing agent pool...[/dim]")
        await initialize_agent_pool(config, max_concurrent=4)
        console.print("[green]✅ Agent pool ready[/green]")

    # Start dashboard if enabled
    if dashboard_enabled:
        console.print("[dim]🖥️  Starting real-time dashboard...[/dim]")
        from .ui.realtime_trace import dashboard

        asyncio.create_task(dashboard.run_async())
        console.print("[green]✅ Dashboard running - press Ctrl+C to exit dashboard view[/green]")

    session_state = {
        "tokens_used": 0,
        "tokens_limit": 200_000,
        "current_model": config.get_active_provider().default_model
        if config.get_active_provider()
        else "none",
        "dashboard_enabled": dashboard_enabled,
        "agent_pool_enabled": agent_pool_enabled,
    }

    from .modes import ModeManager
    from .permissions import PermissionEngine
    from .utils.history import HistoryManager
    from .utils.memory import count_tokens, summarize_history

    history_manager = HistoryManager()
    mode_manager = ModeManager()
    permission_engine = PermissionEngine()

    fallback_engine = FallbackEngine(config)
    agent_loop = AgentLoop(fallback_engine, permission_engine)

    # Initialize pydantic-ai agent with ID for tracking
    ferrox_agent = FerroxAgent(config, agent_id="main", agent_role="main")
    session_state["project_index"] = None
    TOKEN_LIMIT = 32000

    # Initialize prompt sessions with mode-aware styling
    from .async_ui import create_busy_session

    prompt_session = create_prompt_session(
        mode_manager=mode_manager, config=config, session_state=session_state
    )
    # Busy session: shown while the agent is running so the bar never disappears
    busy_session = create_busy_session(
        mode_manager=mode_manager, config=config, session_state=session_state
    )

    console.print("[green]✅ Ferrox Ready. Type /help for commands.[/green]")

    while True:
        # Update session state for status bar
        chat_history = history_manager.get_all()
        current_tokens = count_tokens(chat_history)
        session_state["tokens_used"] = current_tokens

        # 1. Get Input Async
        user_input = await get_user_input(session=prompt_session)

        # Memory Management
        if current_tokens > TOKEN_LIMIT:
            console.print("[dim]🧠 Compressing memory...[/dim]")
            provider = config.get_active_provider()
            model_name = provider.default_model if provider else "gpt-4o"
            summary = summarize_history(
                chat_history,
                fallback_engine,
                model_name,
            )
            # Logic to reset history_manager if needed
            # ...

        # Inject Index/Search context
        if session_state.get("project_index"):
            files = "\n".join(list(session_state["project_index"].keys())[:50])
            context = f"\n\nPROJECT_STRUCTURE:\n{files}"
            # This is a temporary injection, don't save to history manager

        # Add search count
        if "how many times" in user_input.lower() and "search" in user_input.lower():
            user_input += f" (Note: I have performed {history_manager.get_search_count()} web searches so far)"

        if not user_input:
            continue

        # 2. Handle Commands
        if user_input.startswith("/"):
            command = user_input.split()[0]
            if command == "/exit":
                break
            elif command == "/update":
                console.print("[dim]🔄 Updating Ferrox from repository...[/dim]")
                try:
                    # Execute git pull
                    from .tools import execute_tool

                    result = execute_tool("run_command", {"command": "git pull origin main"})
                    console.print(result)
                    console.print("[green]✅ Update complete. Please restart Ferrox.[/green]")
                except Exception as e:
                    console.print(f"[red]❌ Update failed: {e}[/red]")
                continue
            elif command == "/fix":
                args = user_input.split(" ", 1)[1] if len(user_input.split(" ")) > 1 else "pytest"
                console.print(f"[cyan]🔄 Starting Auto-Fix Loop with: {args}[/cyan]")
                result = await agent_loop.execute_task_with_test_loop(
                    task_description="Fix the issues found in the code.",
                    test_command=args,
                    cwd=os.getcwd(),
                )
                if result.get("success"):
                    console.print(
                        f"[green]✅ Issue resolved in {result['attempts']} attempt(s).[/green]"
                    )
                else:
                    console.print(f"[red]❌ Could not resolve: {result.get('error')}[/red]")
                continue
            elif command == "/index":
                console.print("[dim]🗺️ Indexing project symbols...[/dim]")
                index = await build_project_index(os.getcwd())
                session_state["project_index"] = index
                console.print(f"[green]✅ Indexed {len(index)} files.[/green]")
                continue
            elif command == "/status":
                # ...

                provider = config.get_active_provider()
                console.print("\n[bold cyan]🦊 Ferrox Status[/bold cyan]")
                console.print("───────────────────────────────────────────────")
                if provider:
                    console.print(f"● Active Provider: {provider.name} ({provider.base_url})")
                    console.print(f"● Current Model: {provider.default_model or 'Not set'}")
                console.print("───────────────────────────────────────────────\n")
                continue
            elif command == "/jobs":
                from .utils.process_manager import process_manager

                jobs = await process_manager.list_jobs()
                if not jobs:
                    console.print("[dim]No background jobs running.[/dim]")
                else:
                    from rich.table import Table

                    table = Table(title="📋 Background Jobs")
                    table.add_column("PID", style="cyan")
                    table.add_column("Command", style="white")
                    table.add_column("Status", style="green")
                    table.add_column("Log File", style="dim")
                    for job in jobs:
                        status = (
                            "🟢 running" if job["status"] == "running" else f"🔴 {job['status']}"
                        )
                        table.add_row(
                            str(job["pid"]), job["command"][:40] + "...", status, job["log_file"]
                        )
                    console.print(table)
                continue
            elif command.startswith("/jobs kill "):
                try:
                    pid = int(command.split(" ")[2])
                    from .utils.process_manager import process_manager

                    result = await process_manager.kill_job(pid)
                    if result["success"]:
                        console.print(f"[green]✅ {result['message']}[/green]")
                    else:
                        console.print(f"[red]❌ {result.get('error', 'Failed')}[/red]")
                except (IndexError, ValueError):
                    console.print("[red]Usage: /jobs kill <pid>[/red]")
                continue
            elif command == "/help":
                from .ui_legacy import print_help

                print_help()
                continue
            elif command == "/dashboard":
                if session_state.get("dashboard_enabled"):
                    console.print("[green]✅ Dashboard is already running[/green]")
                else:
                    console.print(
                        "[yellow]Dashboard not enabled. Set FERROX_DASHBOARD=true environment variable to enable.[/yellow]"
                    )
                continue
            elif command == "/agents":
                from .agent.agent_pool import agent_pool

                if agent_pool:
                    status = agent_pool.get_pool_status()
                    console.print("\n[bold cyan]🤖 Agent Pool Status[/bold cyan]")
                    console.print("───────────────────────────────────────────────")
                    console.print(f"● Total Agents: {status['total_agents']}")
                    console.print(f"● Available Agents: {status['available_agents']}")
                    console.print(f"● Active Tasks: {status['active_tasks']}")
                    console.print(f"● Queued Tasks: {status['queued_tasks']}")
                    console.print(f"● Completed Tasks: {status['completed_tasks']}")
                    console.print("───────────────────────────────────────────────\n")

                    # Show active tasks
                    active_tasks = agent_pool.get_active_tasks()
                    if active_tasks:
                        from rich.table import Table

                        table = Table(title="🔄 Active Tasks")
                        table.add_column("Task ID", style="cyan")
                        table.add_column("Role", style="white")
                        table.add_column("Status", style="green")
                        table.add_column("Assigned To", style="yellow")
                        for task in active_tasks:
                            table.add_row(
                                task.task_id,
                                task.agent_role,
                                task.status,
                                task.assigned_to or "Unassigned",
                            )
                        console.print(table)
                else:
                    console.print(
                        "[dim]Agent pool not enabled. Set FERROX_AGENT_POOL=true environment variable to enable.[/dim]"
                    )
                continue
            elif command == "/metrics":
                summary = realtime_metrics.get_summary()
                console.print("\n[bold cyan]📊 System Metrics[/bold cyan]")
                console.print("───────────────────────────────────────────────")
                console.print(f"● Active Agents: {summary['agents']['total']}")
                console.print(f"● Tasks Completed: {summary['agents']['tasks_completed']}")
                console.print(f"● Tasks Failed: {summary['agents']['tasks_failed']}")
                console.print(f"● Tokens Used: {summary['agents']['tokens_used']:,}")
                console.print(f"● Errors: {summary['agents']['errors']}")
                console.print("───────────────────────────────────────────────")
                console.print(f"● CPU Usage: {summary['system']['cpu_percent']:.1f}%")
                console.print(f"● Memory Usage: {summary['system']['memory_percent']:.1f}%")
                console.print(f"● Disk Usage: {summary['system']['disk_usage_percent']:.1f}%")
                console.print(f"● Uptime: {summary['system']['uptime_seconds']:.0f}s")
                console.print("───────────────────────────────────────────────\n")
                continue
            elif command == "/events":
                events = event_bus.get_recent_events(limit=20)
                console.print("\n[bold cyan]📋 Recent Events[/bold cyan]")
                console.print("───────────────────────────────────────────────")
                for event in events:
                    timestamp = event.timestamp.strftime("%H:%M:%S")
                    console.print(
                        f"[{timestamp}] {event.agent_id} ({event.agent_role}): {event.event_type.value}"
                    )
                console.print("───────────────────────────────────────────────\n")
                continue
            elif command == "/verbose":
                # Toggle verbose mode for detailed real-time output
                current_verbose = session_state.get("verbose_mode", False)
                session_state["verbose_mode"] = not current_verbose
                new_verbose = session_state["verbose_mode"]
                if new_verbose:
                    console.print(
                        "[green]✅ Verbose mode ENABLED - showing detailed agent thoughts[/green]"
                    )
                else:
                    console.print("[yellow]Verbose mode DISABLED - showing summary only[/yellow]")
                continue
            elif command == "/thoughts":
                # Show recent agent thoughts
                events = event_bus.get_recent_events(event_type=EventType.THOUGHT, limit=10)
                console.print("\n[bold cyan]💭 Recent Agent Thoughts[/bold cyan]")
                console.print("───────────────────────────────────────────────")
                for event in events:
                    timestamp = event.timestamp.strftime("%H:%M:%S")
                    content = event.data.get("content", "")[:100]
                    console.print(f"[{timestamp}] {event.agent_id}: {content}")
                console.print("───────────────────────────────────────────────\n")
                continue
            elif command == "/cfg":
                open_config_editor()
                continue
            elif command == "/model":

                list_models(config)
                continue
            elif command == "/plan":
                mode_manager.set_mode(Mode.PLAN)
                console.print("[yellow]Switched to Plan mode.[/yellow]")
                continue
            elif command == "/bypass":
                mode_manager.set_mode(Mode.BYPASS)
                console.print("[red]Switched to Bypass mode.[/red]")
                continue
            elif command == "/edit":
                mode_manager.set_mode(Mode.EDIT)
                console.print("[deep_sky_blue1]Switched to Edit mode.[/deep_sky_blue1]")
                continue
            elif command == "/normal":
                mode_manager.set_mode(Mode.NORMAL)
                console.print("[green]Switched to Normal mode.[/green]")
                continue
            elif command == "/clear":
                history_manager.clear()
                console.print("[dim]Chat history cleared.[/dim]")
                continue
            elif command.startswith("/browse "):
                url = command.split(" ", 1)[1].strip() if len(command.split(" ", 1)) > 1 else None
                if not url:
                    console.print(
                        "[red]Usage: /browse <url> [screenshot|click <selector>|extract][/red]"
                    )
                    console.print("[dim]Examples:[/dim]")
                    console.print("[dim]  /browse http://localhost:3000[/dim]")
                    console.print("[dim]  /browse http://localhost:3000 screenshot[/dim]")
                    console.print("[dim]  /browse http://localhost:3000 extract[/dim]")
                    continue

                # Determine action
                parts = url.split(" ")
                url = parts[0]
                action = parts[1] if len(parts) > 1 else "screenshot"
                selector = parts[2] if len(parts) > 2 else None

                console.print(f"[dim]🌐 Opening browser for {url}...[/dim]")

                from .agent.tools_browser import browse_url_tool

                class MockCtx:
                    pass

                result = await browse_url_tool(MockCtx(), url, action, selector)
                console.print(result)
                continue
            elif command.startswith("/plan "):
                task = command.split(" ", 1)[1].strip() if len(command.split(" ", 1)) > 1 else None
                if not task:
                    console.print("[red]Usage: /plan <task_description>[/red]")
                    continue

                console.print(f"[cyan]📝 Generating plan for: {task}[/cyan]")

                from .agent.planner import generate_plan, get_current_plan, save_plan_to_file

                plan = await generate_plan(task)

                # Save to PLAN.md
                filepath = save_plan_to_file(plan)

                console.print(f"[green]✅ Plan created with {len(plan.steps)} steps[/green]")
                console.print(f"[dim]Saved to: {filepath}[/dim]")
                console.print("\n[dim]Use /steps to view plan, /next to execute steps[/dim]")
                continue
            elif command == "/steps":
                from .agent.planner import get_plan_status

                console.print(get_plan_status())
                continue
            elif command == "/next":
                from .agent.planner import complete_step, execute_next_step, get_current_plan

                plan = get_current_plan()
                if not plan:
                    console.print("[red]No active plan. Use /plan <task> first.[/red]")
                    continue

                step = execute_next_step()
                if not step:
                    console.print("[green]✅ All steps completed![/green]")
                    continue

                console.print(f"[cyan]👉 Executing step {step.id}: {step.description}[/cyan]")

                # Execute the step via agent
                ferrox_agent._log_thought(f"Executing plan step {step.id}: {step.description}")

                try:
                    provider = config.get_active_provider()
                    model_id = (
                        f"{provider.type}:{provider.default_model}" if provider else "openai:gpt-4o"
                    )
                    history_msgs = [
                        {"role": m["role"], "content": m["content"]}
                        for m in history_manager.get_all()
                    ]

                    result = await ferrox_agent.run(
                        step.description, model_id, history_msgs, mode=mode_manager.current_mode
                    )
                    result_str = _strip_wrapper_objects(str(result))[:500]

                    complete_step(result_str)
                    console.print(f"[green]✅ Step {step.id} completed[/green]")
                    console.print(f"[dim]{result_str[:200]}...[/dim]")

                except Exception as e:
                    from .agent.planner import fail_step

                    fail_step(str(e))
                    console.print(f"[red]❌ Step {step.id} failed: {e}[/red]")
                continue
            elif command.startswith("/step "):
                try:
                    step_num = int(command.split(" ")[1])
                    from .agent.planner import get_current_plan, jump_to_step

                    plan = get_current_plan()
                    if not plan:
                        console.print("[red]No active plan. Use /plan <task> first.[/red]")
                        continue

                    step = jump_to_step(step_num)
                    if not step:
                        console.print(
                            f"[red]Invalid step number. Plan has {len(plan.steps)} steps.[/red]"
                        )
                        continue

                    console.print(f"[cyan]👉 Jumped to step {step_num}: {step.description}[/cyan]")
                except (IndexError, ValueError):
                    console.print("[red]Usage: /step <number>[/red]")
                continue

                rest = parts[2]
                model = None

                # Parse optional --model flag
                if "--model" in rest:
                    split_parts = rest.split("--model", 1)
                    task = split_parts[0].strip()
                    model = split_parts[1].strip()
                else:
                    task = rest.strip()

                console.print(f"[cyan]🤖 Delegating to {role} on {model or 'default'}...[/cyan]")

                from .agent.subagents import delegate_task

                # Create a mock context
                class MockCtx:
                    pass

                result = await delegate_task(MockCtx(), role, task, model)

                if result.success:
                    console.print(
                        f"[green]✅ {role.capitalize()} ({result.model_used}) completed:[/green]"
                    )
                    console.print(_strip_wrapper_objects(result.summary[:500]))
                else:
                    console.print(
                        f"[red]❌ {role} failed: {_strip_wrapper_objects(result.summary)}[/red]"
                    )
                continue
            elif command.startswith("/pip "):
                package = (
                    command.split(" ", 1)[1].strip() if len(command.split(" ", 1)) > 1 else None
                )
                if not package:
                    console.print("[red]Usage: /pip install <package>[/red]")
                    continue
                console.print(f"[dim]📦 Installing {package} via pip...[/dim]")
                from .agent.tools_pydantic import pip_install_tool

                class MockCtx:
                    pass

                result = await pip_install_tool(MockCtx(), package)
                console.print(result)
                continue
            elif command.startswith("/npm "):
                package = (
                    command.split(" ", 1)[1].strip() if len(command.split(" ", 1)) > 1 else None
                )
                if not package:
                    console.print("[red]Usage: /npm install <package>[/red]")
                    continue
                console.print(f"[dim]📦 Installing {package} via npm...[/dim]")
                from .agent.tools_pydantic import npm_install_tool

                class MockCtx:
                    pass

                result = await npm_install_tool(MockCtx(), package)
                console.print(result)
                continue
            elif command.startswith("/cargo "):
                package = (
                    command.split(" ", 1)[1].strip() if len(command.split(" ", 1)) > 1 else None
                )
                if not package:
                    console.print("[red]Usage: /cargo install <package>[/red]")
                    continue
                console.print(f"[dim]📦 Installing {package} via cargo...[/dim]")
                from .agent.tools_pydantic import cargo_install_tool

                class MockCtx:
                    pass

                result = await cargo_install_tool(MockCtx(), package)
                console.print(result)
                continue
            elif command.startswith("/brew "):
                package = (
                    command.split(" ", 1)[1].strip() if len(command.split(" ", 1)) > 1 else None
                )
                if not package:
                    console.print("[red]Usage: /brew install <package>[/red]")
                    continue
                console.print(f"[dim]📦 Installing {package} via brew...[/dim]")
                from .agent.tools_pydantic import brew_install_tool

                class MockCtx:
                    pass

                result = await brew_install_tool(MockCtx(), package)
                console.print(result)
                continue
            elif command.startswith("/go "):
                package = (
                    command.split(" ", 1)[1].strip() if len(command.split(" ", 1)) > 1 else None
                )
                if not package:
                    console.print("[red]Usage: /go install <package>[/red]")
                    continue
                console.print(f"[dim]📦 Installing {package} via go...[/dim]")
                from .agent.tools_pydantic import go_install_tool

                class MockCtx:
                    pass

                result = await go_install_tool(MockCtx(), package)
                console.print(result)
                continue
            # === X Bot Social Commands ===
            elif command == "/x-mode":
                """Toggle X Bot Expert mode with skill injection."""
                session_state["agent_role"] = "x_bot_expert"
                ferrox_agent.agent_role = "x_bot_expert"
                ferrox_agent.skill_manager.activate_skill("x_bot")
                console.print("[cyan]🐦 Switched to X Bot Expert mode.[/cyan]")
                console.print("[dim]X SKILL loaded. All restrictions active.[/dim]")
                continue
            elif command == "/social":
                """Show social bot status."""
                from .social_config import load_social_state
                from .social_daemon import get_daemon_status

                status = get_daemon_status()
                state = load_social_state()

                from .x_browser_login import has_saved_x_session

                browser_session = has_saved_x_session()

                console.print("\n[bold cyan]🐦 X Bot Status[/bold cyan]")
                console.print("───────────────────────────────────────────────")
                console.print(f"Daemon Running: {'Yes' if status['running'] else 'No'}")
                console.print(f"Session Valid: {'Yes' if status['session_valid'] else 'No'}")
                console.print(
                    f"Browser Session: {'Saved (use /x-login to refresh)' if browser_session else 'None (run /x-login)'}")
                console.print(f"Posts Today: {status['posts_today']}")
                console.print(f"Consecutive Failures: {status['consecutive_failures']}")
                if status["started_at"]:
                    console.print(f"Started: {status['started_at']}")
                console.print("───────────────────────────────────────────────")
                console.print("\n[dim]Commands:[/dim]")
                console.print("  /x-login         - Browser login (recommended - no password stored)")
                console.print("  /social login    - Manual username/password login")
                console.print("  /social start    - Start background daemon")
                console.print("  /social stop     - Stop daemon")
                console.print("  /social panic    - Emergency stop & logout")
                console.print("  /social undo     - Delete last tweet")
                console.print("───────────────────────────────────────────────\n")
                continue
            elif command == "/social login":
                """Manual username/password login to X."""
                console.print("[cyan]🐦 X Bot Login (manual)[/cyan]")
                console.print(
                    "[yellow]Note: Credentials are stored in config. "
                    "Consider '/x-login' for password-free browser login.[/yellow]"
                )
                username = console.input("Username (without @): ")
                password = console.input("Password: ", password=True)
                email = console.input("Email (for verification): ")

                from .social_config import SocialConfig

                social_cfg = SocialConfig()
                social_cfg.credentials.username = username
                social_cfg.credentials.password = password
                social_cfg.credentials.email = email

                # Attach to main config
                if hasattr(config, "social"):
                    config.social = social_cfg
                save_config(config)

                console.print(
                    "[green]✅ Credentials saved. Run /social start to begin.[/green]"
                )
                continue
            elif command == "/x-login":
                """Real-browser X login via local server — no automation, no password stored."""
                from .x_browser_login import has_saved_x_session
                from .x_local_server_login import x_login_via_local_server

                if has_saved_x_session():
                    overwrite = console.input(
                        "A saved X session already exists. Overwrite? [y/N]: "
                    )
                    if overwrite.lower().strip() not in ("y", "yes"):
                        console.print("[dim]Kept existing session. Run /social start to use it.[/dim]")
                        continue

                console.print("[cyan]🐦 X Login via Real Browser[/cyan]")
                console.print(
                    "[dim]A local server will start. Open the URL in your REAL browser,\n"
                    "log in to X, then paste the cookies back into the form.[/dim]"
                )

                result = await x_login_via_local_server(timeout_seconds=300)
                console.print(result)
                continue
            elif command == "/social start":
                """Validate X session, show account info, start daemon, switch to SOCIAL mode."""
                import threading

                from .agent.tools_social import validate_x_session
                from .social_daemon import start_daemon

                # ── Step 1: Validate session ──
                console.print("[cyan]🐦 Validating X session...[/cyan]")
                user_info = validate_x_session()

                if not user_info:
                    console.print(
                        "[red]❌ X session invalid or expired.[/red]\n"
                        "[dim]Please log in again:[/dim]\n"
                        "  • /x-login     — browser login (recommended)\n"
                        "  • /social login — manual username/password"
                    )
                    continue

                # ── Step 2: Display account info ──
                is_placeholder = user_info["name"].startswith("(")
                if is_placeholder:
                    console.print("\n[bold cyan]🐦 X Session Cookies Valid[/bold cyan]")
                    console.print("───────────────────────────────────────────────")
                    console.print("  [dim]Cookies loaded — twikit/X API compatibility may affect live data retrieval.[/dim]")
                else:
                    console.print("\n[bold cyan]🐦 X Account Connected[/bold cyan]")
                    console.print("───────────────────────────────────────────────")
                    console.print(f"  Name:     [bold]{user_info['name']}[/bold]")
                    console.print(f"  @ handle: [bold]@{user_info['screen_name']}[/bold]")
                    console.print(
                        f"  Followers: {user_info['followers_count']:,}  │  "
                        f"Following: {user_info['following_count']:,}"
                    )
                    console.print(f"  Tweets:    {user_info['statuses_count']:,}")
                    if user_info.get("verified"):
                        console.print("  [yellow]✓ Verified[/yellow]")
                console.print("───────────────────────────────────────────────\n")

                # ── Step 3: Switch to SOCIAL mode ──
                mode_manager.set_mode("SOCIAL")
                console.print(
                    f"[bold bright_blue]🐦 SOCIAL MODE ACTIVE[/bold bright_blue]  "
                    f"[{mode_manager.get_mode_description()}]"
                )
                console.print(
                    "[dim]The agent now knows about your X account and social tools.\n"
                    "Just ask naturally: 'post a tweet about AI', 'check my mentions',\n"
                    "'reply to my last tweet', 'what's trending', etc.[/dim]\n"
                )

                # ── Step 4: Start background daemon ──
                def run_daemon():
                    start_daemon()

                daemon_thread = threading.Thread(target=run_daemon, daemon=True)
                daemon_thread.start()

                console.print("[green]✅ X Bot daemon started in background.[/green]")
                console.print("[dim]Use /social to check status, /social stop to stop.[/dim]")
                continue
            elif command == "/social stop":
                """Stop social bot daemon and return to NORMAL mode."""
                from .social_daemon import stop_daemon

                if stop_daemon():
                    console.print("[green]✅ X Bot daemon stopped.[/green]")
                else:
                    console.print("[yellow]Daemon was not running.[/yellow]")

                # Exit SOCIAL mode back to NORMAL
                if mode_manager.current_mode.name == "SOCIAL":
                    mode_manager.set_mode("NORMAL")
                    console.print("[dim]Returned to NORMAL mode.[/dim]")
                continue
            elif command == "/social panic":
                """Emergency stop and logout."""
                from .social_config import load_social_state, save_social_state
                from .social_daemon import stop_daemon

                console.print("[red]🚨 PANIC MODE - Stopping everything![/red]")

                stop_daemon()

                state = load_social_state()
                state.daemon_running = False
                state.session_valid = False
                state.consecutive_failures = 0
                save_social_state(state)

                # Also clear browser-login cookies
                from .x_browser_login import clear_x_session

                clear_x_session()

                # Exit SOCIAL mode
                if mode_manager.current_mode.name == "SOCIAL":
                    mode_manager.set_mode("NORMAL")

                console.print("[red]✅ Panic complete. Bot stopped, all sessions cleared.[/red]")
                continue
            elif command == "/social undo":
                """Delete last tweet."""
                from .agent.tools_social import delete_tweet_tool
                from .social_config import load_social_state

                state = load_social_state()
                if not state.recent_tweets:
                    console.print("[yellow]No recent tweets to delete.[/yellow]")
                    continue

                last_tweet = state.recent_tweets[-1]
                tweet_id = last_tweet.get("id")

                console.print(f"[cyan]Deleting tweet {tweet_id}...[/cyan]")

                class MockCtx:
                    pass

                result = await delete_tweet_tool(MockCtx(), tweet_id)
                console.print(result)
                continue
            else:
                console.print(f"[red]Unknown command: {command}[/red]")
                continue

        # 3. Send to AI via Tool Loop
        try:
            # Pre-check for Ollama connectivity
            provider = config.get_active_provider()
            if provider and (provider.type == "ollama" or "11434" in provider.base_url):
                import httpx

                try:
                    # Strip /v1 for the status check
                    check_url = (
                        provider.base_url.split("/v1")[0]
                        if provider.base_url
                        else "http://localhost:11434"
                    )
                    with httpx.Client(timeout=1.0) as client:
                        client.get(check_url)
                except (httpx.ConnectError, httpx.TimeoutException):
                    console.print("\n[bold red]❌ Ollama is not running![/bold red]")
                    console.print("\n[bold cyan]How to get it working now:[/bold cyan]")
                    console.print("  1. Open a new terminal and run [yellow]ollama serve[/yellow].")
                    console.print(
                        f"  2. Pull the model if you haven't: [yellow]ollama pull {provider.default_model or 'llama3.2'}[/yellow]."
                    )
                    console.print("  3. Run Ferrox again.\n")
                    continue

            # ── Print user message in Devin style ──
            from .ui.output import (
                _unescape_newlines,
                format_elapsed,
                format_separator,
                format_user_message,
                reset_step_counter,
            )

            format_user_message(user_input)
            format_separator()
            history_manager.add("user", user_input)

            # Reset agent step counter for this turn
            reset_step_counter()

            # ── Run agent with persistent input bar ──
            think_start = asyncio.get_event_loop().time()

            ferrox_agent._log_thought(f"Processing user input: {user_input[:50]}...")

            from .api import send_message_with_tool_loop
            from .async_ui import run_agent_with_input_bar

            full_response = ""
            btw_injections: list = []

            # Use pydantic-ai agent for structured tool handling
            provider = config.get_active_provider()
            model_id = f"{provider.type}:{provider.default_model}" if provider else "openai:gpt-4o"

            # Convert history to pydantic-ai message format
            history_msgs = [
                {"role": m["role"], "content": m["content"]} for m in history_manager.get_all()
            ]

            try:
                try:
                    ferrox_agent._log_thought(f"Running agent with model: {model_id}")
                    # run_agent_with_input_bar keeps the input bar visible at the
                    # bottom while the agent works.  The user can type
                    # /btw <msg> to inject context or Ctrl+C to cancel.
                    agent_result, btw_injections = await run_agent_with_input_bar(
                        ferrox_agent.run(
                            user_prompt=user_input,
                            model_id=model_id,
                            history=history_msgs,
                            mode=mode_manager.current_mode,
                        ),
                        busy_session,
                    )
                    full_response = (
                        str(agent_result) if agent_result else "Agent completed without output."
                    )
                    ferrox_agent._log_thought("Agent completed successfully")

                except AuthenticationError as e:
                    ferrox_agent._log_thought(f"Auth error: {e.message}")
                    full_response = (
                        "Authentication failed. Please check your API key configuration."
                    )

                except RateLimitError as e:
                    ferrox_agent._log_thought(f"Rate limit: {e.message}")
                    await asyncio.sleep(5)
                    full_response = "Rate limit hit. Please try again later."

                except TimeoutError as e:
                    ferrox_agent._log_thought(f"Timeout: {e.message}")
                    full_response = "Request timed out. Please try again."

                except NetworkError as e:
                    ferrox_agent._log_thought(f"Network error: {e.message}")
                    full_response = "Network error occurred. Please check your connection."

                except ProviderError as e:
                    ferrox_agent._log_thought(f"Provider error: {e.message}, trying fallback")
                    try:
                        for chunk in send_message_with_tool_loop(config, history_manager.get_all()):
                            if full_response == "":
                                console.print(" " * 20, end="\r")
                            console.print(chunk, end="")
                            full_response += chunk
                    except Exception:
                        full_response = (
                            f"Both primary provider and fallback failed. Original: {e.message}"
                        )

                except ToolExecutionError as e:
                    ferrox_agent._log_thought(f"Tool error: {e.message}")
                    full_response = f"Tool execution error: {e.message}"

                except FerroxError as e:
                    ferrox_agent._log_thought(f"Ferrox error: {e.message}")
                    full_response = f"An error occurred: {e.message}"

                except Exception as agent_err:
                    ferrox_agent._log_thought(
                        f"Unexpected error: {type(agent_err).__name__}: {agent_err}"
                    )
                    try:
                        for chunk in send_message_with_tool_loop(config, history_manager.get_all()):
                            if full_response == "":
                                console.print(" " * 20, end="\r")
                            console.print(chunk, end="")
                            full_response += chunk
                    except Exception:
                        full_response = "Both agent and API failed. Please check logs."
            finally:
                elapsed = asyncio.get_event_loop().time() - think_start
                format_elapsed(elapsed, session_state.get("tokens_used", 0))

            # ── Inject /btw context so the agent sees it on the next turn ──
            for btw in btw_injections:
                history_manager.add("user", f"[Context injected mid-response]: {btw}")
                console.print(f'[dim]📌 Context saved for next turn: "{btw[:60]}"[/dim]')

            # Strip any pydantic-ai wrapper objects and unescape newlines
            full_response = _strip_wrapper_objects(full_response)
            full_response = _unescape_newlines(full_response)

            # ── Print assistant response in Devin style ──
            if full_response:
                # Show full model name, e.g. "qwen2.5:7b" not just "7b"
                model_label = model_id.split(":", 1)[1] if ":" in model_id else model_id
                sep = "─" * 50
                console.file.write(f"\n{sep}\n")
                console.file.write(f"{model_label}  {full_response.strip()}\n")
                console.file.write(f"{sep}\n\n")
                console.file.flush()
            history_manager.add("assistant", full_response)

        except Exception as e:
            console.print(" " * 20, end="\r")
            console.print(f"\n[red]❌ Critical Error:[/red] {str(e)}")
            logger.error(f"Chat loop error: {e}")


@click.group()
@click.version_option(version="1.1.0")
def cli():
    """Ferrox - Cross-platform AI CLI Tool"""
    pass


@cli.command()
def validate():
    """Validate all configured providers"""
    config = check_config()
    if config is None:
        display_error("No configuration found.")
        sys.exit(1)

    console.print("[cyan]Validating providers...[/cyan]\n")

    for provider in config.providers:
        console.print(f"Checking {provider.name} ({provider.base_url})...")

        import asyncio

        success, models, error = asyncio.run(validate_provider(provider))

        if success:
            provider.models = models
            provider.is_validated = True
            provider.last_validated = datetime.now()
            if not provider.default_model and models:
                provider.default_model = models[0]
            display_success(f"OK - {len(models)} models")
        else:
            provider.is_validated = False
            display_error(f"Failed: {error}")

    save_config(config)
    console.print("\n[green]Validation complete.[/green]")


@cli.command()
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
@click.option("--no-animation", is_flag=True, help="Skip logo animation on startup")
def start(verbose, no_animation):
    """Start interactive chat session"""
    logger = get_logger(verbose)

    config = check_config()

    # --- AUTO-DISCOVERY LOGIC ---
    if config is None:
        console.print("[cyan]No configuration found. Checking for local Ollama...[/cyan]")
        import httpx

        try:
            # Check if Ollama is running
            resp = httpx.get("http://localhost:11434/api/tags", timeout=2)
            if resp.status_code == 200:
                console.print("[green]✅ Found running Ollama instance![/green]")
                from .config import get_default_config

                config = get_default_config()
                save_config(config)
                console.print("[green]Created default Ollama configuration.[/green]")
            else:
                raise Exception("Ollama not responding")
        except Exception:
            console.print("[yellow]Ollama not detected or unreachable.[/yellow]")
            response = console.input("Configure manually? [Y/n]: ")
            if response.strip().lower() in ("", "y", "yes"):
                open_config_editor()
                config = check_config()
                if config is None:
                    display_error("Configuration required.")
                    sys.exit(1)
            else:
                sys.exit(1)
    # --- END AUTO-DISCOVERY ---

    # Health Check
    provider = config.get_active_provider()
    if provider:
        console.print(f"[dim]Checking health of {provider.name}...[/dim]")
        import asyncio

        success, _, _ = asyncio.run(validate_provider(provider))
        if not success:
            display_warning(
                f"Active provider {provider.name} is unreachable. Check your settings or service status."
            )
        else:
            display_success(f"Provider {provider.name} is healthy.")

    # Show active provider info
    if provider and provider.default_model:
        console.print(f"[dim]Active: {provider.name} ({provider.default_model})[/dim]\n")

    asyncio.run(start_chat_loop(config, no_animation=no_animation))


@cli.command()
def config():
    """Open config file in editor"""
    open_config_editor()


@cli.command()
def models():
    """List available models"""
    config = check_config()
    if config is None:
        display_error("No valid configuration. Run /cfg to set up.")
        sys.exit(1)

    list_models(config)


@cli.command()
def chat():
    """Start interactive chat (alias for start)"""
    start()


def main():
    """Main entry point"""
    if len(sys.argv) == 1:
        start()
    else:
        cli()


if __name__ == "__main__":
    main()
