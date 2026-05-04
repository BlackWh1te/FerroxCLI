"""Visual progress indicators for long-running operations."""

from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, Optional

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.text import Text


class ProgressType(Enum):
    SPINNER = "spinner"
    BAR = "bar"
    DOTS = "dots"
    PULSE = "pulse"


class ProgressIndicator:
    """Base class for progress indicators."""

    def __init__(self, description: str, progress_type: ProgressType = ProgressType.SPINNER):
        self.description = description
        self.progress_type = progress_type
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.is_complete: bool = False
        self.is_cancelled: bool = False
        self.on_complete: Optional[Callable] = None
        self.on_cancel: Optional[Callable] = None

    def start(self) -> None:
        """Start the progress indicator."""
        self.start_time = datetime.now()

    def complete(self) -> None:
        """Mark as complete."""
        self.end_time = datetime.now()
        self.is_complete = True
        if self.on_complete:
            self.on_complete()

    def cancel(self) -> None:
        """Cancel the progress indicator."""
        self.end_time = datetime.now()
        self.is_cancelled = True
        if self.on_cancel:
            self.on_cancel()

    def get_elapsed(self) -> timedelta:
        """Get elapsed time."""
        if self.start_time:
            end = self.end_time or datetime.now()
            return end - self.start_time
        return timedelta(0)

    def get_elapsed_str(self) -> str:
        """Get elapsed time as string."""
        elapsed = self.get_elapsed()
        total_seconds = int(elapsed.total_seconds())
        if total_seconds < 60:
            return f"{total_seconds}s"
        elif total_seconds < 3600:
            minutes, seconds = divmod(total_seconds, 60)
            return f"{minutes}m {seconds}s"
        else:
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            return f"{hours}h {minutes}m"


class SpinnerProgress(ProgressIndicator):
    """Spinner progress indicator for indeterminate operations."""

    def __init__(self, description: str):
        super().__init__(description, ProgressType.SPINNER)
        self.current_message: str = ""

    def update_message(self, message: str) -> None:
        """Update the spinner message."""
        self.current_message = message

    def render(self) -> Panel:
        """Render the spinner."""
        Console()

        if self.is_complete:
            status = "✅ Complete"
            color = "green"
        elif self.is_cancelled:
            status = "❌ Cancelled"
            color = "red"
        else:
            status = "⏳ In Progress"
            color = "yellow"

        text = Text()
        text.append(f"{status}\n\n", style=f"bold {color}")
        text.append(f"{self.description}\n", style="white")
        if self.current_message:
            text.append(f"{self.current_message}\n", style="dim")
        text.append(f"Elapsed: {self.get_elapsed_str()}", style="dim")

        return Panel(text, border_style=color)


class ProgressBarProgress(ProgressIndicator):
    """Progress bar for determinate operations."""

    def __init__(self, description: str, total: int = 100):
        super().__init__(description, ProgressType.BAR)
        self.total = total
        self.completed = 0
        self.current_item: str = ""

    def update(self, completed: int, current_item: str = "") -> None:
        """Update progress."""
        self.completed = min(completed, self.total)
        self.current_item = current_item

    def increment(self, amount: int = 1, current_item: str = "") -> None:
        """Increment progress."""
        self.update(self.completed + amount, current_item)

    def get_progress_pct(self) -> float:
        """Get progress as percentage."""
        if self.total == 0:
            return 0.0
        return (self.completed / self.total) * 100

    def get_progress_str(self) -> str:
        """Get progress as string."""
        pct = self.get_progress_pct()
        bar_width = 20
        filled = int(bar_width * pct / 100)
        bar = "█" * filled + "░" * (bar_width - filled)
        return f"{bar} {pct:.1f}%"

    def render(self) -> Panel:
        """Render the progress bar."""
        Console()

        if self.is_complete:
            status = "✅ Complete"
            color = "green"
        elif self.is_cancelled:
            status = "❌ Cancelled"
            color = "red"
        else:
            status = "⏳ In Progress"
            color = "yellow"

        text = Text()
        text.append(f"{status}\n\n", style=f"bold {color}")
        text.append(f"{self.description}\n", style="white")
        text.append(f"{self.get_progress_str()}\n", style="cyan")
        text.append(f"{self.completed}/{self.total} items\n", style="dim")
        if self.current_item:
            text.append(f"Current: {self.current_item}\n", style="dim italic")
        text.append(f"Elapsed: {self.get_elapsed_str()}", style="dim")

        # Estimate remaining time
        if not self.is_complete and not self.is_cancelled and self.completed > 0:
            elapsed = self.get_elapsed().total_seconds()
            rate = self.completed / elapsed if elapsed > 0 else 0
            if rate > 0:
                remaining = (self.total - self.completed) / rate
                remaining_str = f"Est. remaining: {int(remaining)}s"
                text.append(f"\n{remaining_str}", style="dim")

        return Panel(text, border_style=color)


class ProgressManager:
    """Manager for multiple progress indicators."""

    def __init__(self):
        self.indicators: dict[str, ProgressIndicator] = {}
        self.console = Console()

    def create_spinner(self, task_id: str, description: str) -> SpinnerProgress:
        """Create a spinner progress indicator."""
        spinner = SpinnerProgress(description)
        self.indicators[task_id] = spinner
        spinner.start()
        return spinner

    def create_progress_bar(self, task_id: str, description: str, total: int) -> ProgressBarProgress:
        """Create a progress bar indicator."""
        bar = ProgressBarProgress(description, total)
        self.indicators[task_id] = bar
        bar.start()
        return bar

    def get_indicator(self, task_id: str) -> Optional[ProgressIndicator]:
        """Get a progress indicator by ID."""
        return self.indicators.get(task_id)

    def complete_task(self, task_id: str) -> None:
        """Mark a task as complete."""
        indicator = self.get_indicator(task_id)
        if indicator:
            indicator.complete()

    def cancel_task(self, task_id: str) -> None:
        """Cancel a task."""
        indicator = self.get_indicator(task_id)
        if indicator:
            indicator.cancel()

    def remove_task(self, task_id: str) -> None:
        """Remove a task."""
        if task_id in self.indicators:
            del self.indicators[task_id]

    def render_all(self) -> None:
        """Render all active progress indicators."""
        if not self.indicators:
            return

        panels = []
        for _task_id, indicator in self.indicators.items():
            if not indicator.is_complete and not indicator.is_cancelled:
                panels.append(indicator.render())

        if panels:
            self.console.print("\n")
            for panel in panels:
                self.console.print(panel)
                self.console.print()

    def render_summary(self) -> None:
        """Render a summary of all tasks."""
        if not self.indicators:
            return

        table = self.console.table
        table.add_column("Task ID", style="cyan")
        table.add_column("Description", style="white")
        table.add_column("Type", style="yellow")
        table.add_column("Status", style="green")
        table.add_column("Elapsed", style="dim")

        for task_id, indicator in self.indicators.items():
            status = "Complete" if indicator.is_complete else "Cancelled" if indicator.is_cancelled else "In Progress"
            table.add_row(
                task_id,
                indicator.description[:30],
                indicator.progress_type.value,
                status,
                indicator.get_elapsed_str(),
            )

        self.console.print(table)


class ContextProgress:
    """Context manager for progress indicators."""

    def __init__(self, manager: ProgressManager, task_id: str, description: str, total: Optional[int] = None):
        self.manager = manager
        self.task_id = task_id
        self.description = description
        self.total = total

    def __enter__(self) -> ProgressIndicator:
        """Enter context and create progress indicator."""
        if self.total is not None:
            return self.manager.create_progress_bar(self.task_id, self.description, self.total)
        else:
            return self.manager.create_spinner(self.task_id, self.description)

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context and complete/cancel task."""
        if exc_type is None:
            self.manager.complete_task(self.task_id)
        else:
            self.manager.cancel_task(self.task_id)
        self.manager.remove_task(self.task_id)


# Global progress manager
_global_progress_manager = ProgressManager()


def get_progress_manager() -> ProgressManager:
    """Get the global progress manager."""
    return _global_progress_manager


def create_spinner(task_id: str, description: str) -> SpinnerProgress:
    """Create a spinner progress indicator."""
    return get_progress_manager().create_spinner(task_id, description)


def create_progress_bar(task_id: str, description: str, total: int) -> ProgressBarProgress:
    """Create a progress bar indicator."""
    return get_progress_manager().create_progress_bar(task_id, description, total)


def show_progress() -> None:
    """Show all active progress indicators."""
    get_progress_manager().render_all()


def progress_context(task_id: str, description: str, total: Optional[int] = None) -> ContextProgress:
    """Create a context manager for progress tracking."""
    return ContextProgress(get_progress_manager(), task_id, description, total)


# Convenience decorators
def with_progress(task_id: str, description: str, total: Optional[int] = None):
    """Decorator to add progress tracking to a function."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            with progress_context(task_id, description, total) as progress:
                kwargs['_progress'] = progress
                return func(*args, **kwargs)
        return wrapper
    return decorator


async def async_with_progress(task_id: str, description: str, total: Optional[int] = None):
    """Async decorator to add progress tracking to a function."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            with progress_context(task_id, description, total) as progress:
                kwargs['_progress'] = progress
                return await func(*args, **kwargs)
        return wrapper
    return decorator


# Live progress display
class LiveProgressDisplay:
    """Live display for progress indicators."""

    def __init__(self, manager: ProgressManager, refresh_rate: float = 0.5):
        self.manager = manager
        self.refresh_rate = refresh_rate
        self.is_running = False

    def start(self) -> None:
        """Start the live display."""
        self.is_running = True
        console = Console()

        def generate_layout():
            if not self.manager.indicators:
                return Text("No active tasks", style="dim italic")

            panels = []
            for _task_id, indicator in self.manager.indicators.items():
                if not indicator.is_complete and not indicator.is_cancelled:
                    panels.append(indicator.render())

            if not panels:
                return Text("All tasks complete", style="green")

            # Stack panels vertically
            from rich.layout import Layout
            layout = Layout()
            layout.split(*[Layout(panel) for panel in panels])
            return layout

        with Live(generate_layout(), refresh_per_second=1/self.refresh_rate, console=console) as live:
            while self.is_running and any(
                not i.is_complete and not i.is_cancelled
                for i in self.manager.indicators.values()
            ):
                live.update(generate_layout())
                import time
                time.sleep(self.refresh_rate)

    def stop(self) -> None:
        """Stop the live display."""
        self.is_running = False
