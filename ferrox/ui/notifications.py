"""Notification system for background jobs and events."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional


class NotificationType(Enum):
    SUCCESS = "success"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    JOB_COMPLETE = "job_complete"
    JOB_FAILED = "job_failed"
    AGENT_STATUS = "agent_status"


@dataclass
class Notification:
    """A notification item."""

    id: str
    title: str
    message: str
    notification_type: NotificationType
    timestamp: datetime = field(default_factory=datetime.now)
    read: bool = False
    action_label: Optional[str] = None
    action_callback: Optional[Callable] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def mark_read(self) -> None:
        """Mark notification as read."""
        self.read = True

    def execute_action(self) -> Any:
        """Execute the action callback if present."""
        if self.action_callback:
            return self.action_callback()
        return None


class NotificationManager:
    """Manager for notifications."""

    def __init__(self, max_notifications: int = 50):
        self.notifications: list[Notification] = []
        self.max_notifications = max_notifications
        self.on_new_notification: Optional[Callable] = None

    def add_notification(
        self,
        title: str,
        message: str,
        notification_type: NotificationType = NotificationType.INFO,
        action_label: Optional[str] = None,
        action_callback: Optional[Callable] = None,
        **metadata,
    ) -> Notification:
        """Add a new notification."""
        import uuid

        notification = Notification(
            id=str(uuid.uuid4())[:8],
            title=title,
            message=message,
            notification_type=notification_type,
            action_label=action_label,
            action_callback=action_callback,
            metadata=metadata,
        )

        self.notifications.insert(0, notification)

        # Trim if over limit
        if len(self.notifications) > self.max_notifications:
            self.notifications = self.notifications[: self.max_notifications]

        # Trigger callback
        if self.on_new_notification:
            self.on_new_notification(notification)

        return notification

    def add_success(self, title: str, message: str, **kwargs) -> Notification:
        """Add a success notification."""
        return self.add_notification(title, message, NotificationType.SUCCESS, **kwargs)

    def add_error(self, title: str, message: str, **kwargs) -> Notification:
        """Add an error notification."""
        return self.add_notification(title, message, NotificationType.ERROR, **kwargs)

    def add_warning(self, title: str, message: str, **kwargs) -> Notification:
        """Add a warning notification."""
        return self.add_notification(title, message, NotificationType.WARNING, **kwargs)

    def add_info(self, title: str, message: str, **kwargs) -> Notification:
        """Add an info notification."""
        return self.add_notification(title, message, NotificationType.INFO, **kwargs)

    def add_job_complete(
        self, job_id: str, result: str = "Job completed successfully"
    ) -> Notification:
        """Add a job completion notification."""
        return self.add_notification(
            title="Job Complete",
            message=f"Job {job_id}: {result}",
            notification_type=NotificationType.JOB_COMPLETE,
            metadata={"job_id": job_id},
        )

    def add_job_failed(self, job_id: str, error: str) -> Notification:
        """Add a job failure notification."""
        return self.add_notification(
            title="Job Failed",
            message=f"Job {job_id}: {error}",
            notification_type=NotificationType.JOB_FAILED,
            metadata={"job_id": job_id, "error": error},
        )

    def add_agent_status(self, agent_id: str, status: str) -> Notification:
        """Add an agent status notification."""
        return self.add_notification(
            title="Agent Status Update",
            message=f"Agent {agent_id}: {status}",
            notification_type=NotificationType.AGENT_STATUS,
            metadata={"agent_id": agent_id, "status": status},
        )

    def get_notification(self, notification_id: str) -> Optional[Notification]:
        """Get a notification by ID."""
        for notification in self.notifications:
            if notification.id == notification_id:
                return notification
        return None

    def get_unread(self) -> list[Notification]:
        """Get all unread notifications."""
        return [n for n in self.notifications if not n.read]

    def get_by_type(self, notification_type: NotificationType) -> list[Notification]:
        """Get notifications by type."""
        return [n for n in self.notifications if n.notification_type == notification_type]

    def mark_read(self, notification_id: str) -> None:
        """Mark a notification as read."""
        notification = self.get_notification(notification_id)
        if notification:
            notification.mark_read()

    def mark_all_read(self) -> None:
        """Mark all notifications as read."""
        for notification in self.notifications:
            notification.mark_read()

    def clear(self) -> None:
        """Clear all notifications."""
        self.notifications.clear()

    def clear_read(self) -> None:
        """Clear all read notifications."""
        self.notifications = [n for n in self.notifications if not n.read]

    def get_unread_count(self) -> int:
        """Get count of unread notifications."""
        return len(self.get_unread())

    def render_rich(self) -> None:
        """Render notifications using Rich."""
        from rich.console import Console
        from rich.table import Table
        from rich.text import Text

        console = Console()

        if not self.notifications:
            console.print("[dim]No notifications[/dim]")
            return

        # Summary
        unread_count = self.get_unread_count()
        console.print(f"\n📬 Notifications ({unread_count} unread)")
        console.print("=" * 80 + "\n")

        # Notification list
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("", width=2)  # Read indicator
        table.add_column("Type", width=12)
        table.add_column("Title", width=25)
        table.add_column("Message", width=35)
        table.add_column("Time", width=8)

        for notification in self.notifications[:20]:  # Show last 20
            # Type styling
            type_styles = {
                NotificationType.SUCCESS: "green",
                NotificationType.ERROR: "red bold",
                NotificationType.WARNING: "yellow",
                NotificationType.INFO: "blue",
                NotificationType.JOB_COMPLETE: "green",
                NotificationType.JOB_FAILED: "red bold",
                NotificationType.AGENT_STATUS: "cyan",
            }
            type_style = type_styles.get(notification.notification_type, "white")

            # Read indicator
            read_indicator = "●" if not notification.read else "○"
            read_style = "bold yellow" if not notification.read else "dim"

            # Time
            time_str = notification.timestamp.strftime("%H:%M")

            table.add_row(
                Text(read_indicator, style=read_style),
                Text(notification.notification_type.value, style=type_style),
                notification.title[:24],
                notification.message[:34],
                time_str,
            )

        console.print(table)

        if len(self.notifications) > 20:
            console.print(f"\n[dim]... and {len(self.notifications) - 20} more notifications[/dim]")


class ToastNotification:
    """Toast notification display."""

    def __init__(self, manager: NotificationManager):
        self.manager = manager
        self.is_running = False

    async def show_toasts(self, duration: float = 3.0) -> None:
        """Show toast notifications for unread items."""
        self.is_running = True

        while self.is_running:
            unread = self.manager.get_unread()
            if unread:
                await self._display_toast(unread[0], duration)
                self.manager.mark_read(unread[0].id)

            await asyncio.sleep(0.5)

    async def _display_toast(self, notification: Notification, duration: float) -> None:
        """Display a single toast notification."""
        from rich.console import Console
        from rich.panel import Panel

        console = Console()

        # Style based on type
        border_styles = {
            NotificationType.SUCCESS: "green",
            NotificationType.ERROR: "red",
            NotificationType.WARNING: "yellow",
            NotificationType.INFO: "blue",
            NotificationType.JOB_COMPLETE: "green",
            NotificationType.JOB_FAILED: "red",
            NotificationType.AGENT_STATUS: "cyan",
        }
        border_style = border_styles.get(notification.notification_type, "white")

        panel = Panel(
            f"{notification.message}",
            title=f"{notification.title}",
            border_style=border_style,
            padding=(0, 1),
        )

        # Save and clear current line
        console.print("\r" + " " * 80 + "\r", end="")

        # Display toast
        console.print(panel)

        # Wait for duration
        await asyncio.sleep(duration)

        # Clear toast
        console.print("\r" + " " * 80 + "\r", end="")

    def stop(self) -> None:
        """Stop showing toasts."""
        self.is_running = False


# Global notification manager
_global_notification_manager = NotificationManager()


def get_notification_manager() -> NotificationManager:
    """Get the global notification manager."""
    return _global_notification_manager


def notify_success(title: str, message: str, **kwargs) -> Notification:
    """Add a success notification."""
    return get_notification_manager().add_success(title, message, **kwargs)


def notify_error(title: str, message: str, **kwargs) -> Notification:
    """Add an error notification."""
    return get_notification_manager().add_error(title, message, **kwargs)


def notify_warning(title: str, message: str, **kwargs) -> Notification:
    """Add a warning notification."""
    return get_notification_manager().add_warning(title, message, **kwargs)


def notify_info(title: str, message: str, **kwargs) -> Notification:
    """Add an info notification."""
    return get_notification_manager().add_info(title, message, **kwargs)


def notify_job_complete(job_id: str, result: str = "Job completed successfully") -> Notification:
    """Add a job completion notification."""
    return get_notification_manager().add_job_complete(job_id, result)


def notify_job_failed(job_id: str, error: str) -> Notification:
    """Add a job failure notification."""
    return get_notification_manager().add_job_failed(job_id, error)


def show_notifications() -> None:
    """Show all notifications."""
    get_notification_manager().render_rich()


def get_unread_count() -> int:
    """Get unread notification count."""
    return get_notification_manager().get_unread_count()


# Convenience function for job monitoring
def monitor_job(
    job_id: str, coro, on_complete: Optional[Callable] = None, on_error: Optional[Callable] = None
):
    """Monitor an async job and send notifications."""

    async def wrapper():
        try:
            result = await coro
            notify_job_complete(job_id, str(result)[:100])
            if on_complete:
                on_complete(result)
            return result
        except Exception as e:
            notify_job_failed(job_id, str(e))
            if on_error:
                on_error(e)
            raise

    return wrapper()
