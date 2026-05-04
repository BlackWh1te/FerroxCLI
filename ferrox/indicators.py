"""Status indicators for Ferrox CLI - thinking, running, fetching"""

import contextlib
from typing import Optional

from rich.console import Console
from rich.status import Status

console = Console()


class SimpleStatus:
    """Simple status display without spinner animation"""

    @staticmethod
    def show_thinking():
        console.print("[dim]... thinking[/dim]", end=" ", flush=True)

    @staticmethod
    def show_running(tool_name: str):
        console.print(f"\n[green]>>[/green] Running: {tool_name}")

    @staticmethod
    def show_fetching(url: str):
        console.print(f"\n[blue]--[/blue] Fetching: {url}")

    @staticmethod
    def clear():
        pass


class StatusIndicator:
    """Status indicator with spinner using Rich status"""

    def __init__(self, state: str = "thinking", prefix: str = ""):
        self.state = state
        self.prefix = prefix
        self.running = False
        self.status: Optional[Status] = None
        self.message = ""

    def start(self, message: str = ""):
        self.message = message
        self.running = True

        spinner = {"thinking": "dots", "running": "arrow3", "fetching": "dots2"}

        try:
            self.status = console.status(
                f"[cyan]{message}[/cyan]", spinner=spinner.get(self.state, "dots")
            )
            self.status.start()
        except Exception:
            console.print(f"[cyan]...[/cyan] {message}")

    def stop(self):
        self.running = False
        if self.status:
            with contextlib.suppress(Exception):
                self.status.stop()
            self.status = None

    def update_message(self, message: str):
        self.message = message
        if self.status:
            with contextlib.suppress(Exception):
                self.status.update(f"[cyan]{message}[/cyan]")


def get_spinner(state: str = "thinking", prefix: str = "") -> StatusIndicator:
    return StatusIndicator(state, prefix)


status_bar = SimpleStatus()
