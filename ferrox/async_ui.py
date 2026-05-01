import asyncio
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from rich.console import Console

console = Console()

async def get_user_input(session: PromptSession) -> str:
    """
    Asynchronously gets user input using prompt_toolkit.
    """
    try:
        text = await session.prompt_async(
            "> ",
            auto_suggest=AutoSuggestFromHistory(),
            enable_history_search=True,
        )
        return text.strip()
    except EOFError:
        return "/exit"
    except KeyboardInterrupt:
        return "/exit"

def create_prompt_session():
    """
    Creates a PromptSession with history and completions.
    """
    history_file = os.path.expanduser("~/.ferrox/history.txt")
    commands = ["/cfg", "/model", "/plan", "/bypass", "/normal", "/clear", "/exit", "/status"]
    
    return PromptSession(
        history=FileHistory(history_file),
        completer=WordCompleter(commands, ignore_case=True),
    )
