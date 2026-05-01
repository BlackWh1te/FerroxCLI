"""Main CLI module for Ferrox"""

import sys
import os
import subprocess
from pathlib import Path
from typing import Optional
from datetime import datetime

import click

from .config import (
    load_config,
    save_config,
    validate_config,
    get_default_config,
    CONFIG_FILE,
    ensure_config_dir,
    FerroxConfig,
    ProviderConfig,
)
from .modes import Mode, ModeManager
from .permissions import PermissionEngine, PermissionAction
from .api import fetch_models, send_message, send_message_with_tool_loop, APIError, validate_provider, validate_and_update_provider
from .logger import get_logger, log_mode_change, log_request, log_fallback
from .ui import (
    console,
    display_welcome,
    display_error,
    display_success,
    display_system,
    display_mode_change,
    display_models,
    display_warning,
    get_user_input,
    create_devin_style_input_layout,
    get_devin_style
)
from prompt_toolkit.application import Application
from .console_logger import UIHandler
from .fallback import FallbackEngine # Import FallbackEngine
from .indicators import StatusIndicator, status_bar
from .agent.loop import AgentLoop
from .agent.orchestrator import FerroxAgent
from .exceptions import (
    FerroxError,
    ConfigurationError,
    ProviderError,
    AuthenticationError,
    RateLimitError,
    ToolExecutionError,
    NetworkError,
    TimeoutError
)
from .utils.indexer import build_project_index, find_symbol_usage


SESSION_STATE_FILE = Path.home() / ".ferrox" / "session_state.json"


class ChatSession:
    """Chat session manager with mode support"""

    def __init__(self, config: FerroxConfig, mode_manager: ModeManager, permission_engine: PermissionEngine):
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

    def check_file_access(self, filepath: str, action: PermissionAction = PermissionAction.READ) -> bool:
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

    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL") or (
        "notepad" if os.name == "nt" else ("code" if _command_exists("code") else "vim")
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
            ["where" if os.name == "nt" else "which", cmd],
            capture_output=True,
            check=False
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

        display_models(models)

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
from .async_ui import create_prompt_session, get_user_input
from .config import load_config, save_config, validate_config, FerroxConfig
from .fallback import FallbackEngine
from .logger_new import logger
from rich.console import Console

console = Console()

async def start_chat_loop(config: FerroxConfig):
    """
    Main async chat loop using prompt_toolkit.
    """
    from .ui.header import render_header
    render_header()
    
    session_state = {
        "tokens_used": 0,
        "tokens_limit": 200_000,
        "current_model": config.get_active_provider().default_model if config.get_active_provider() else "none"
    }
    
    # Create application with layout
    layout = create_devin_style_input_layout(config, session_state)
    app = Application(
        layout=layout,
        style=get_devin_style(),
        full_screen=False,
    )
    from .utils.memory import count_tokens, summarize_history

    from .utils.history import HistoryManager
    history_manager = HistoryManager()
    fallback_engine = FallbackEngine(config)
    agent_loop = AgentLoop(fallback_engine, None)
    
    # Initialize pydantic-ai agent
    ferrox_agent = FerroxAgent(config)
    session_state["project_index"] = None
    TOKEN_LIMIT = 32000

    console.print("[green]✅ Ferrox Ready. Type /help for commands.[/green]")

    while True:
        # 1. Get Input Async
        user_input = await get_user_input(session=None)
        
        # Get history from manager
        chat_history = history_manager.get_all()

        # Memory Management
        current_tokens = count_tokens(chat_history)
        if current_tokens > TOKEN_LIMIT:
            console.print("[dim]🧠 Compressing memory...[/dim]")
            summary = summarize_history(chat_history, fallback_engine, config.get_active_provider().default_model or "gpt-4o")
            # Logic to reset history_manager if needed
            # ...

        # Inject Index/Search context
        if session_state.get('project_index'):
            files = "\n".join(list(session_state['project_index'].keys())[:50])
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
                    cwd=os.getcwd()
                )
                if result.get('success'):
                    console.print(f"[green]✅ Issue resolved in {result['attempts']} attempt(s).[/green]")
                else:
                    console.print(f"[red]❌ Could not resolve: {result.get('error')}[/red]")
                continue
            elif command == "/index":
                console.print("[dim]🗺️ Indexing project symbols...[/dim]")
                index = await build_project_index(os.getcwd())
                session_state['project_index'] = index
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
            else:
                console.print(f"[red]Unknown command: {command}[/red]")
                continue

        # 3. Send to AI via Tool Loop
        try:
            history_manager.add("user", user_input)
            
            console.print("[dim]⠋ Thinking...[/dim]", end="\r")
            
            # Log thought: starting to process user input
            ferrox_agent._log_thought(f"Processing user input: {user_input[:50]}...")
            
            from .api import send_message_with_tool_loop
            
            # send_message_with_tool_loop is a generator
            full_response = ""
            
            # Use pydantic-ai agent for structured tool handling
            provider = config.get_active_provider()
            model_id = f"{provider.type}:{provider.default_model}" if provider else "openai:gpt-4o"
            
            # Convert history to pydantic-ai message format
            history_msgs = [{"role": m["role"], "content": m["content"]} for m in history_manager.get_all()]
            
            try:
                ferrox_agent._log_thought(f"Running agent with model: {model_id}")
                agent_result = await ferrox_agent.run(user_input, model_id, history_msgs)
                full_response = str(agent_result) if agent_result else "Agent completed without output."
                ferrox_agent._log_thought(f"Agent completed successfully")
                
            except AuthenticationError as e:
                ferrox_agent._log_thought(f"Auth error: {e.message}")
                console.print(f"[yellow]⚠️ Authentication failed:[/yellow] {e.message}")
                console.print("[dim]Check your API key in /cfg[/dim]")
                full_response = "Authentication failed. Please check your API key configuration."
                
            except RateLimitError as e:
                ferrox_agent._log_thought(f"Rate limit: {e.message}")
                console.print(f"[yellow]⚠️ Rate limit exceeded:[/yellow] {e.message}")
                console.print("[dim]Waiting 5 seconds before retry...[/dim]")
                await asyncio.sleep(5)
                full_response = "Rate limit hit. Please try again later."
                
            except TimeoutError as e:
                ferrox_agent._log_thought(f"Timeout: {e.message}")
                console.print(f"[yellow]⚠️ Request timed out:[/yellow] {e.message}")
                full_response = "Request timed out. Please try again."
                
            except NetworkError as e:
                ferrox_agent._log_thought(f"Network error: {e.message}")
                console.print(f"[red]🌐 Network error:[/red] {e.message}")
                console.print("[dim]Check your internet connection[/dim]")
                full_response = "Network error occurred. Please check your connection."
                
            except ProviderError as e:
                ferrox_agent._log_thought(f"Provider error: {e.message}, trying fallback")
                console.print(f"[yellow]⚠️ Provider error:[/yellow] {e.message}")
                console.print("[dim]Attempting fallback...[/dim]")
                try:
                    for chunk in send_message_with_tool_loop(config, history_manager.get_all()):
                        if full_response == "":
                            console.print(" " * 20, end="\r")
                        console.print(chunk, end="")
                        full_response += chunk
                except Exception as fallback_err:
                    full_response = f"Both primary provider and fallback failed. Original: {e.message}"
                    
            except ToolExecutionError as e:
                ferrox_agent._log_thought(f"Tool error: {e.message}")
                console.print(f"[red]🔧 Tool execution failed:[/red] {e.message}")
                full_response = f"Tool execution error: {e.message}"
                
            except FerroxError as e:
                ferrox_agent._log_thought(f"Ferrox error: {e.message}")
                console.print(f"[red]❌ Error:[/red] {e.message}")
                full_response = f"An error occurred: {e.message}"
                
            except Exception as agent_err:
                ferrox_agent._log_thought(f"Unexpected error: {type(agent_err).__name__}: {agent_err}")
                console.print(f"[red]❌ Unexpected error:[/red] {type(agent_err).__name__}: {agent_err}")
                console.print("[dim]Attempting fallback to API...[/dim]")
                try:
                    for chunk in send_message_with_tool_loop(config, history_manager.get_all()):
                        if full_response == "":
                            console.print(" " * 20, end="\r")
                        console.print(chunk, end="")
                        full_response += chunk
                except Exception:
                    full_response = "Both agent and API failed. Please check logs."
            
            console.print(" " * 20, end="\r")
            console.print(full_response)
            history_manager.add("assistant", full_response)
                
        except Exception as e:
            console.print(" " * 20, end="\r")
            console.print(f"\n[red]❌ Critical Error:[/red] {str(e)}")
            logger.error(f"Chat loop error: {e}")

def main():
    """Main entry point"""
    config = load_config()
    if config is None:
        console.print("[red]No configuration found. Run /cfg or ferrox config.[/red]")
        sys.exit(1)
        
    try:
        asyncio.run(start_chat_loop(config))
    except KeyboardInterrupt:
        console.print("\n👋 Goodbye!")


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
@click.option('--verbose', '-v', is_flag=True, help='Enable debug logging')
def start(verbose):
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
        except:
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

    # Validate active provider
    provider = config.get_active_provider()
    if provider:
        if not provider.is_validated or not provider.models:
            console.print(f"[dim]Validating provider {provider.name}...[/dim]")
            provider = validate_and_update_provider(provider, config)
            if provider.is_validated:
                display_success(f"Provider validated. {len(provider.models)} models available.")
            else:
                display_warning(f"Provider validation failed. Some features may not work.")

@cli.command()
@click.option('--verbose', '-v', is_flag=True, help='Enable debug logging')
def start(verbose):
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
        except:
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
            display_warning(f"Active provider {provider.name} is unreachable. Check your settings or service status.")
        else:
            display_success(f"Provider {provider.name} is healthy.")

    # Show active provider info
    if provider and provider.default_model:
        console.print(f"[dim]Active: {provider.name} ({provider.default_model})[/dim]\n")

    asyncio.run(start_chat_loop(config))


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