# UI Integration Guide

This guide shows how to integrate the complementary UI components into FerroxCLI.

## Overview of New Components

These components complement the existing real-time trace viewer and dashboard:

### 1. Progress Indicators
Visual spinners and progress bars for long-running operations (unique component).

### 2. Notification System
Toast notifications and notification center for events and job completion (unique component).

## Coordination with Existing Work

These components are designed to work alongside:
- **Real-time trace viewer** (`ferrox/ui/realtime_trace.py`) - Textual-based real-time monitoring
- **Event bus system** (`ferrox/agent/event_bus.py`) - Pub/sub for agent events
- **Real-time metrics** (`ferrox/metrics_realtime.py`) - Performance monitoring

## Integration Examples

### Progress Indicators

```python
from ferrox.ui import (
    create_spinner,
    create_progress_bar,
    show_progress,
    progress_context,
    with_progress,
)

# Create a spinner for indeterminate operations
spinner = create_spinner("task_1", "Loading configuration...")
spinner.update_message("Parsing JSON...")
spinner.complete()
show_progress()

# Create a progress bar for determinate operations
progress = create_progress_bar("task_2", "Processing files", total=100)
progress.increment(10, current_item="file1.txt")
progress.increment(10, current_item="file2.txt")
progress.update(50)
progress.complete()
show_progress()

# Use as a context manager
with progress_context("task_3", "Downloading data", total=1000) as progress:
    for i in range(1000):
        # Do work
        progress.increment(1)

# Use as a decorator
@with_progress("task_4", "Processing batch", total=100)
def process_batch(_progress):
    for i in range(100):
        _progress.increment(1)
        # Do work

process_batch()
```

### Notification System

```python
from ferrox.ui import (
    notify_success,
    notify_error,
    notify_warning,
    notify_info,
    notify_job_complete,
    notify_job_failed,
    show_notifications,
    get_unread_count,
)

# Add notifications
notify_success("Build Complete", "Project built successfully")
notify_error("Build Failed", "Compilation error in src/main.py")
notify_warning("Low Memory", "Memory usage at 85%")
notify_info("Update Available", "New version 2.0.0 available")

# Job-specific notifications
notify_job_complete("job_123", "Tests passed")
notify_job_failed("job_456", "Timeout after 30s")

# Show all notifications
show_notifications()

# Check unread count
unread = get_unread_count()
print(f"You have {unread} unread notifications")
```

## Integrating into CLI

### Adding Progress to Long Operations

Wrap long operations with progress indicators:

```python
elif command == "/index":
    from ferrox.ui import create_progress_bar, show_progress

    progress = create_progress_bar("index", "Indexing project", total=100)
    try:
        # Update progress during indexing
        for i, file in enumerate(files):
            progress.increment(1, current_item=file)
            # Index file
    finally:
        progress.complete()
        show_progress()
```

### Adding Notifications for Background Jobs

```python
from ferrox.ui import notify_job_complete, notify_job_failed

async def run_background_job(job_id: str, task: str):
    try:
        result = await execute_task(task)
        notify_job_complete(job_id, str(result))
    except Exception as e:
        notify_job_failed(job_id, str(e))
```

### Integrating with Event Bus

Connect progress and notifications to the existing event bus:

```python
from ferrox.agent.event_bus import event_bus, EventType
from ferrox.ui import notify_info, create_progress_bar

# Subscribe to agent events for notifications
def on_agent_error(event):
    notify_info("Agent Error", f"{event.agent_id}: {event.data.get('error')}")

event_bus.subscribe(EventType.ERROR, on_agent_error)

# Use progress for long-running agent tasks
async def execute_with_progress(task_id, task):
    progress = create_progress_bar(task_id, "Executing task", total=100)
    try:
        # Subscribe to progress events from event bus
        def on_progress(event):
            if event.agent_id == task_id:
                progress.update(event.data.get('progress', 0))

        event_bus.subscribe(EventType.PROGRESS, on_progress)
        # Execute task
        result = await task
        progress.complete()
        return result
    finally:
        event_bus.unsubscribe(EventType.PROGRESS, on_progress)
```

## Keyboard Shortcuts Integration

Add notification shortcut to `ferrox/async_ui.py`:

```python
@kb.add("c-n")
def _(event):
    """Ctrl+N: Show notifications."""
    from ferrox.ui import show_notifications
    show_notifications()
```

## Status Bar Enhancement

Update the status bar in `ferrox/async_ui.py` to show unread notifications:

```python
def get_status_footer_text(mode_manager, config, session_state: Dict[str, Any]) -> Any:
    # ... existing code ...

    # Add notification count
    from ferrox.ui import get_unread_count
    unread_count = get_unread_count()
    if unread_count > 0:
        result.append(("class:status-key", " notifications "))
        result.append(("class:status-value", f" {unread_count} "))
        result.append(("class:status-separator", " ┃ "))

    return result
```

## Testing the Components

Create a test script to verify the unique components work:

```python
# test_ui_components.py
from ferrox.ui import (
    create_spinner,
    create_progress_bar,
    notify_success,
    show_notifications,
)

# Test progress
spinner = create_spinner("test", "Test spinner")
spinner.update_message("Processing...")
spinner.complete()

# Test progress bar
progress = create_progress_bar("test2", "Processing files", total=10)
for i in range(10):
    progress.increment(1, current_item=f"file{i}.txt")
progress.complete()

# Test notifications
notify_success("Test", "This is a test notification")
notify_info("Info", "Information message")
notify_warning("Warning", "Warning message")
notify_error("Error", "Error message")

show_notifications()

print("All UI components tested successfully!")
```

## Next Steps

1. Integrate progress indicators into long-running CLI operations
2. Add notifications for background job completion
3. Connect notifications to the event bus for real-time alerts
4. Add Ctrl+N keyboard shortcut for notifications
5. Enhance status bar with notification count
6. Add components to the help system
7. Test integration with existing real-time trace viewer
