# 🦊 FerroxCLI - Real-Time Agent Visualization & Enhancement Plan

## 📋 Executive Summary

This plan outlines comprehensive improvements to FerroxCLI's functionality with focus on **real-time visualization** of agent activities, supporting **multiple concurrent agents**, and enhanced user experience for monitoring AI agent behavior.

## 🎯 Primary Goals

1. **Real-Time Agent Activity Visualization** - Live streaming of agent thoughts, tool calls, and results
2. **Multi-Agent Dashboard** - Support for visualizing 4+ concurrent agents with split-screen layouts
3. **Enhanced Monitoring** - Progress bars, token usage, timing metrics, and performance tracking
4. **Improved Coordination** - Visual task queues, agent pools, and inter-agent communication
5. **Modern UI/UX** - Color-coded agents, collapsible sections, search/filter, export capabilities

---

## 🏗️ Architecture Overview

### Current State Analysis

**Strengths:**
- Solid pydantic-ai integration with OpenTelemetry tracing
- Existing trace viewer (Ctrl+O) but static/post-hoc only
- Multi-agent support via subagents system
- Devin-style UI foundation with Rich library

**Limitations:**
- Trace viewer is not real-time (requires manual trigger)
- No multi-agent visualization when running concurrent agents
- Limited progress indication for long-running tasks
- No centralized dashboard for agent coordination
- Missing real-time metrics and performance tracking

### Proposed Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    FERROX DASHBOARD LAYER                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Agent Panel 1│  │ Agent Panel 2│  │ Agent Panel 3│  ...  │
│  │  (Researcher)│  │   (Coder)    │  │  (Reviewer)  │       │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│  ┌──────────────────────────────────────────────────────┐  │
│  │           Central Command & Metrics Panel              │  │
│  │  Task Queue | Progress | Token Usage | Performance   │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  REAL-TIME EVENT BUS                         │
│  (asyncio.Queue + pub/sub for agent events)                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    AGENT ORCHESTRATION LAYER                 │
│  FerroxAgent | Subagents | AgentLoop | FallbackEngine      │
└─────────────────────────────────────────────────────────────┘
```

---

## 📦 Required Dependencies

### New Packages to Install

```bash
# Real-time UI framework
pip install textual>=0.50.0  # Already in deps, will use extensively

# Async coordination
pip install aiofiles>=23.0.0  # Async file operations
pip install asyncio-throttle>=1.0.0  # Rate limiting

# Enhanced visualization
pip install rich>=13.0.0  # Already in deps, upgrade if needed
pip install rich-panel>=1.0.0  # Enhanced panel components

# Metrics & monitoring
pip install psutil>=5.9.0  # System resource monitoring
pip install prometheus-client>=0.19.0  # Already in deps

# Data structures for multi-agent
pip install sortedcontainers>=2.4.0  # Efficient sorted data structures
```

### Dependency Updates in pyproject.toml

```toml
dependencies = [
    # ... existing deps ...
    "textual>=0.50.0",
    "aiofiles>=23.0.0",
    "asyncio-throttle>=1.0.0",
    "psutil>=5.9.0",
    "sortedcontainers>=2.4.0",
]
```

---

## 🎨 Phase 1: Real-Time Event System

### 1.1 Agent Event Bus

**File:** `ferrox/agent/event_bus.py`

```python
"""Real-time event bus for agent activities."""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Any, Callable
import json

class EventType(Enum):
    THOUGHT = "thought"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    ERROR = "error"
    STATUS_CHANGE = "status_change"
    PROGRESS = "progress"
    METRIC = "metric"

@dataclass
class AgentEvent:
    event_type: EventType
    agent_id: str
    agent_role: str  # "main", "researcher", "coder", "reviewer"
    timestamp: datetime
    data: dict
    metadata: dict = None

class AgentEventBus:
    """Pub/sub event bus for real-time agent monitoring."""
    
    def __init__(self):
        self._subscribers: dict[EventType, list[Callable]] = {}
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._event_history: list[AgentEvent] = []
        self._max_history = 1000
        self._running = False
        
    def subscribe(self, event_type: EventType, callback: Callable):
        """Subscribe to specific event types."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)
        
    async def publish(self, event: AgentEvent):
        """Publish event to all subscribers."""
        await self._event_queue.put(event)
        
    async def start(self):
        """Start event processing loop."""
        self._running = True
        asyncio.create_task(self._process_events())
        
    async def _process_events(self):
        """Process events from queue and notify subscribers."""
        while self._running:
            event = await self._event_queue.get()
            
            # Add to history
            self._event_history.append(event)
            if len(self._event_history) > self._max_history:
                self._event_history.pop(0)
                
            # Notify subscribers
            subscribers = self._subscribers.get(event.event_type, [])
            for callback in subscribers:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(event)
                    else:
                        callback(event)
                except Exception as e:
                    print(f"Error in subscriber callback: {e}")
                    
    def get_recent_events(self, agent_id: str = None, limit: int = 50):
        """Get recent events, optionally filtered by agent."""
        events = self._event_history
        if agent_id:
            events = [e for e in events if e.agent_id == agent_id]
        return events[-limit:]
        
    def stop(self):
        """Stop event processing."""
        self._running = False

# Global event bus instance
event_bus = AgentEventBus()
```

### 1.2 Enhanced Agent Logging

**File:** `ferrox/agent/orchestrator.py` (modifications)

```python
# Add to existing imports
from .event_bus import event_bus, AgentEvent, EventType

class FerroxAgent:
    def __init__(self, config: FerroxConfig, agent_id: str = "main", agent_role: str = "main"):
        self.config = config
        self.agent_id = agent_id
        self.agent_role = agent_role
        self.session_logs = []
        # ... existing init code ...
        
    def _log_thought(self, content: str):
        """Log agent thought with real-time publishing."""
        self.session_logs.append({
            "type": "thought", 
            "content": content, 
            "timestamp": datetime.now()
        })
        
        # Publish to event bus
        asyncio.create_task(event_bus.publish(AgentEvent(
            event_type=EventType.THOUGHT,
            agent_id=self.agent_id,
            agent_role=self.agent_role,
            timestamp=datetime.now(),
            data={"content": content}
        )))
        
        # Real-time display
        try:
            from ..ui.output import format_agent_thought
            format_agent_thought(content)
        except Exception:
            pass
            
    def _log_tool_call(self, name: str, args: dict):
        """Log tool call with real-time publishing."""
        self.session_logs.append({
            "type": "tool_call", 
            "name": name, 
            "args": args, 
            "timestamp": datetime.now()
        })
        
        # Publish to event bus
        asyncio.create_task(event_bus.publish(AgentEvent(
            event_type=EventType.TOOL_CALL,
            agent_id=self.agent_id,
            agent_role=self.agent_role,
            timestamp=datetime.now(),
            data={"tool_name": name, "args": args}
        )))
        
        # Real-time display
        try:
            from ..ui.output import format_tool_call
            format_tool_call(name, args)
        except Exception:
            pass
```

---

## 🖥️ Phase 2: Multi-Agent Dashboard UI

### 2.1 Textual-Based Dashboard

**File:** `ferrox/ui/dashboard.py`

```python
"""Real-time multi-agent dashboard using Textual."""

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, Container
from textual.widgets import (
    Header, Footer, Static, ProgressBar, 
    Log, DataTable, Tabs, Tab, ContentSwitcher
)
from textual.reactive import reactive
from textual import events
from datetime import datetime
from ..agent.event_bus import event_bus, AgentEvent, EventType
import asyncio

class AgentPanel(Vertical):
    """Individual agent activity panel."""
    
    agent_id = reactive("")
    agent_role = reactive("")
    status = reactive("idle")
    
    def __init__(self, agent_id: str, agent_role: str, **kwargs):
        super().__init__(**kwargs)
        self.agent_id = agent_id
        self.agent_role = agent_role
        self.events = []
        
    def compose(self) -> ComposeResult:
        yield Static(f"🤖 {self.agent_role.upper()} [{self.agent_id}]", id="agent-header")
        yield Log(id="agent-log")
        yield ProgressBar(id="agent-progress")
        
    def on_mount(self) -> None:
        """Subscribe to agent events."""
        event_bus.subscribe(EventType.THOUGHT, self._on_thought)
        event_bus.subscribe(EventType.TOOL_CALL, self._on_tool_call)
        event_bus.subscribe(EventType.TOOL_RESULT, self._on_tool_result)
        
    async def _on_thought(self, event: AgentEvent):
        """Handle thought events for this agent."""
        if event.agent_id != self.agent_id:
            return
            
        log = self.query_one("#agent-log", Log)
        timestamp = event.timestamp.strftime("%H:%M:%S")
        log.write_line(f"[{timestamp}] 🧠 {event.data['content']}")
        
    async def _on_tool_call(self, event: AgentEvent):
        """Handle tool call events for this agent."""
        if event.agent_id != self.agent_id:
            return
            
        log = self.query_one("#agent-log", Log)
        timestamp = event.timestamp.strftime("%H:%M:%S")
        tool_name = event.data['tool_name']
        args = event.data.get('args', {})
        log.write_line(f"[{timestamp}] 🛠️ {tool_name}({args})")
        
    async def _on_tool_result(self, event: AgentEvent):
        """Handle tool result events for this agent."""
        if event.agent_id != self.agent_id:
            return
            
        log = self.query_one("#agent-log", Log)
        timestamp = event.timestamp.strftime("%H:%M:%S")
        success = event.data.get('success', True)
        icon = "✅" if success else "❌"
        log.write_line(f"[{timestamp}] {icon} {event.data.get('content', '')[:100]}")

class MetricsPanel(Vertical):
    """Central metrics and command panel."""
    
    def compose(self) -> ComposeResult:
        yield Static("📊 SYSTEM METRICS", id="metrics-header")
        yield DataTable(id="metrics-table")
        
    def on_mount(self) -> None:
        """Initialize metrics table."""
        table = self.query_one("#metrics-table", DataTable)
        table.add_column("Metric", width=20)
        table.add_column("Value", width=30)
        
        # Initial metrics
        table.add_row("Active Agents", "0")
        table.add_row("Total Events", "0")
        table.add_row("Tokens Used", "0")
        table.add_row("Avg Response Time", "0s")

class FerroxDashboard(App):
    """Main multi-agent dashboard application."""
    
    CSS = """
    Screen {
        layout: vertical;
    }
    
    #agent-header {
        background: $primary;
        color: $text;
        padding: 0 1;
        height: 3;
    }
    
    AgentPanel {
        height: 1fr;
        border: solid green;
    }
    
    MetricsPanel {
        height: 20;
        border: solid blue;
    }
    
    Log {
        height: 1fr;
        scrollbar: true;
    }
    """
    
    def __init__(self):
        super().__init__()
        self.agent_panels = {}
        self.metrics = {
            "active_agents": 0,
            "total_events": 0,
            "tokens_used": 0,
            "avg_response_time": 0.0
        }
        
    def compose(self) -> ComposeResult:
        yield Header()
        yield Horizontal(
            Container(id="agents-container"),
            MetricsPanel(id="metrics-panel")
        )
        yield Footer()
        
    def on_mount(self) -> None:
        """Initialize dashboard."""
        # Start event bus
        asyncio.create_task(event_bus.start())
        
        # Subscribe to all events for metrics
        event_bus.subscribe(EventType.METRIC, self._on_metric)
        
    def add_agent_panel(self, agent_id: str, agent_role: str):
        """Add a new agent panel to the dashboard."""
        container = self.query_one("#agents-container")
        panel = AgentPanel(agent_id, agent_role)
        container.mount(panel)
        self.agent_panels[agent_id] = panel
        self.metrics["active_agents"] = len(self.agent_panels)
        self._update_metrics_display()
        
    def remove_agent_panel(self, agent_id: str):
        """Remove an agent panel from the dashboard."""
        if agent_id in self.agent_panels:
            self.agent_panels[agent_id].remove()
            del self.agent_panels[agent_id]
            self.metrics["active_agents"] = len(self.agent_panels)
            self._update_metrics_display()
            
    async def _on_metric(self, event: AgentEvent):
        """Handle metric events."""
        metric_name = event.data.get('name')
        metric_value = event.data.get('value')
        
        if metric_name in self.metrics:
            self.metrics[metric_name] = metric_value
            self._update_metrics_display()
            
    def _update_metrics_display(self):
        """Update the metrics table."""
        table = self.query_one("#metrics-table", DataTable)
        table.clear()
        table.add_row("Active Agents", str(self.metrics["active_agents"]))
        table.add_row("Total Events", str(self.metrics["total_events"]))
        table.add_row("Tokens Used", str(self.metrics["tokens_used"]))
        table.add_row("Avg Response Time", f"{self.metrics['avg_response_time']:.2f}s")

# Global dashboard instance
dashboard = FerroxDashboard()
```

### 2.2 Dashboard Integration with CLI

**File:** `ferrox/cli.py` (modifications)

```python
# Add to imports
from .ui.dashboard import dashboard

async def start_chat_loop(config: FerroxConfig):
    """Main async chat loop with dashboard support."""
    
    # Check if dashboard mode is enabled
    dashboard_mode = os.getenv("FERROX_DASHBOARD", "false").lower() == "true"
    
    if dashboard_mode:
        # Start dashboard in separate thread/task
        asyncio.create_task(dashboard.run_async())
        
        # Add main agent panel
        dashboard.add_agent_panel("main", "main")
    
    # ... existing chat loop code ...
    
    # When spawning subagents, add panels
    if command == "/plan":
        # ... existing plan code ...
        dashboard.add_agent_panel("planner", "planner")
```

---

## 🔄 Phase 3: Enhanced Multi-Agent Coordination

### 3.1 Agent Pool Manager

**File:** `ferrox/agent/agent_pool.py`

```python
"""Agent pool management for concurrent agent execution."""

import asyncio
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime
from .orchestrator import FerroxAgent
from .event_bus import event_bus, AgentEvent, EventType

@dataclass
class AgentTask:
    task_id: str
    description: str
    agent_role: str
    priority: int = 0
    created_at: datetime = None
    assigned_to: str = None
    status: str = "pending"  # pending, running, completed, failed
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()

class AgentPool:
    """Manages a pool of agents for concurrent task execution."""
    
    def __init__(self, config, max_concurrent: int = 4):
        self.config = config
        self.max_concurrent = max_concurrent
        self.agents: Dict[str, FerroxAgent] = {}
        self.task_queue: asyncio.Queue = asyncio.Queue()
        self.active_tasks: Dict[str, AgentTask] = {}
        self.running = False
        
    async def start(self):
        """Start the agent pool."""
        self.running = True
        # Initialize agents
        for i in range(self.max_concurrent):
            agent_id = f"agent-{i}"
            agent = FerroxAgent(self.config, agent_id, "worker")
            self.agents[agent_id] = agent
            
        # Start task processor
        asyncio.create_task(self._process_tasks())
        
    async def submit_task(self, task: AgentTask) -> str:
        """Submit a task to the pool."""
        await self.task_queue.put(task)
        
        # Publish task submission event
        await event_bus.publish(AgentEvent(
            event_type=EventType.STATUS_CHANGE,
            agent_id="pool",
            agent_role="pool",
            timestamp=datetime.now(),
            data={"task_id": task.task_id, "status": "queued"}
        ))
        
        return task.task_id
        
    async def _process_tasks(self):
        """Process tasks from the queue."""
        while self.running:
            # Get next task
            task = await self.task_queue.get()
            
            # Find available agent
            available_agent = self._get_available_agent()
            if not available_agent:
                # No agents available, re-queue
                await asyncio.sleep(0.1)
                await self.task_queue.put(task)
                continue
                
            # Assign task to agent
            task.assigned_to = available_agent.agent_id
            task.status = "running"
            self.active_tasks[task.task_id] = task
            
            # Execute task
            asyncio.create_task(self._execute_task(task, available_agent))
            
    def _get_available_agent(self) -> Optional[FerroxAgent]:
        """Get an available agent from the pool."""
        for agent_id, agent in self.agents.items():
            # Check if agent is not busy (simple check)
            if agent_id not in [t.assigned_to for t in self.active_tasks.values()]:
                return agent
        return None
        
    async def _execute_task(self, task: AgentTask, agent: FerroxAgent):
        """Execute a task with an agent."""
        try:
            # Publish start event
            await event_bus.publish(AgentEvent(
                event_type=EventType.STATUS_CHANGE,
                agent_id=agent.agent_id,
                agent_role=agent.agent_role,
                timestamp=datetime.now(),
                data={"task_id": task.task_id, "status": "started"}
            ))
            
            # Execute the task (this would call the agent's run method)
            # result = await agent.run(task.description, ...)
            
            # For now, simulate
            await asyncio.sleep(2)
            
            # Update task status
            task.status = "completed"
            
            # Publish completion event
            await event_bus.publish(AgentEvent(
                event_type=EventType.STATUS_CHANGE,
                agent_id=agent.agent_id,
                agent_role=agent.agent_role,
                timestamp=datetime.now(),
                data={"task_id": task.task_id, "status": "completed"}
            ))
            
        except Exception as e:
            task.status = "failed"
            await event_bus.publish(AgentEvent(
                event_type=EventType.ERROR,
                agent_id=agent.agent_id,
                agent_role=agent.agent_role,
                timestamp=datetime.now(),
                data={"task_id": task.task_id, "error": str(e)}
            ))
        finally:
            # Remove from active tasks
            if task.task_id in self.active_tasks:
                del self.active_tasks[task.task_id]
                
    def get_task_status(self, task_id: str) -> Optional[AgentTask]:
        """Get the status of a specific task."""
        return self.active_tasks.get(task_id)
        
    def get_all_tasks(self) -> List[AgentTask]:
        """Get all active and recent tasks."""
        return list(self.active_tasks.values())
        
    async def stop(self):
        """Stop the agent pool."""
        self.running = False
```

### 3.2 Enhanced Subagent Coordination

**File:** `ferrox/agent/subagents.py` (enhancements)

```python
# Add to existing imports
from .event_bus import event_bus, AgentEvent, EventType
from .agent_pool import AgentPool, AgentTask

# Global agent pool
agent_pool = None

async def initialize_agent_pool(config, max_concurrent: int = 4):
    """Initialize the global agent pool."""
    global agent_pool
    agent_pool = AgentPool(config, max_concurrent)
    await agent_pool.start()

async def delegate_task_with_pool(
    ctx: RunContext, 
    role: str, 
    task_description: str, 
    model: Optional[str] = None,
    priority: int = 0
) -> SubagentResult:
    """Delegate task using the agent pool for better coordination."""
    
    if agent_pool is None:
        # Fallback to original delegate_task
        return await delegate_task(ctx, role, task_description, model)
    
    # Create task
    task = AgentTask(
        task_id=f"{role}-{datetime.now().timestamp()}",
        description=task_description,
        agent_role=role,
        priority=priority
    )
    
    # Submit to pool
    task_id = await agent_pool.submit_task(task)
    
    # Wait for completion (with timeout)
    timeout = 300  # 5 minutes
    start_time = datetime.now()
    
    while (datetime.now() - start_time).total_seconds() < timeout:
        task_status = agent_pool.get_task_status(task_id)
        if task_status and task_status.status in ["completed", "failed"]:
            break
        await asyncio.sleep(0.5)
    
    # Get final status
    final_status = agent_pool.get_task_status(task_id)
    
    if final_status and final_status.status == "completed":
        return SubagentResult(
            role=role,
            summary=f"Task completed via agent pool",
            artifacts=[],
            success=True,
            model_used=model or "pool"
        )
    else:
        return SubagentResult(
            role=role,
            summary="Task failed or timed out",
            artifacts=[],
            success=False,
            model_used=model or "pool",
            error="Task execution failed"
        )
```

---

## 📊 Phase 4: Enhanced Metrics & Monitoring

### 4.1 Real-Time Metrics Collector

**File:** `ferrox/metrics_realtime.py`

```python
"""Real-time metrics collection and reporting."""

import asyncio
import psutil
import time
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Dict, Optional
from .agent.event_bus import event_bus, AgentEvent, EventType

@dataclass
class AgentMetrics:
    agent_id: str
    agent_role: str
    tasks_completed: int = 0
    tasks_failed: int = 0
    total_tokens_used: int = 0
    total_response_time: float = 0.0
    avg_response_time: float = 0.0
    last_activity: Optional[datetime] = None
    
class RealTimeMetrics:
    """Real-time metrics collector for agent monitoring."""
    
    def __init__(self):
        self.agent_metrics: Dict[str, AgentMetrics] = {}
        self.system_metrics = {
            "cpu_percent": 0.0,
            "memory_percent": 0.0,
            "disk_usage": 0.0
        }
        self.running = False
        
    async def start(self):
        """Start metrics collection."""
        self.running = True
        
        # Subscribe to events
        event_bus.subscribe(EventType.TOOL_RESULT, self._on_tool_result)
        event_bus.subscribe(EventType.STATUS_CHANGE, self._on_status_change)
        
        # Start system metrics collection
        asyncio.create_task(self._collect_system_metrics())
        
    async def _on_tool_result(self, event: AgentEvent):
        """Track tool results for metrics."""
        agent_id = event.agent_id
        
        if agent_id not in self.agent_metrics:
            self.agent_metrics[agent_id] = AgentMetrics(
                agent_id=agent_id,
                agent_role=event.agent_role
            )
            
        metrics = self.agent_metrics[agent_id]
        
        # Update metrics based on result
        success = event.data.get('success', True)
        if success:
            metrics.tasks_completed += 1
        else:
            metrics.tasks_failed += 1
            
        metrics.last_activity = datetime.now()
        
        # Publish metric event
        await event_bus.publish(AgentEvent(
            event_type=EventType.METRIC,
            agent_id=agent_id,
            agent_role=event.agent_role,
            timestamp=datetime.now(),
            data={
                "name": "tasks_completed",
                "value": metrics.tasks_completed,
                "agent_id": agent_id
            }
        ))
        
    async def _on_status_change(self, event: AgentEvent):
        """Track status changes."""
        agent_id = event.agent_id
        status = event.data.get('status')
        
        if agent_id not in self.agent_metrics:
            self.agent_metrics[agent_id] = AgentMetrics(
                agent_id=agent_id,
                agent_role=event.agent_role
            )
            
        self.agent_metrics[agent_id].last_activity = datetime.now()
        
    async def _collect_system_metrics(self):
        """Collect system metrics periodically."""
        while self.running:
            self.system_metrics["cpu_percent"] = psutil.cpu_percent()
            self.system_metrics["memory_percent"] = psutil.virtual_memory().percent
            self.system_metrics["disk_usage"] = psutil.disk_usage('/').percent
            
            # Publish system metrics
            await event_bus.publish(AgentEvent(
                event_type=EventType.METRIC,
                agent_id="system",
                agent_role="system",
                timestamp=datetime.now(),
                data=self.system_metrics
            ))
            
            await asyncio.sleep(5)  # Update every 5 seconds
            
    def get_agent_metrics(self, agent_id: str) -> Optional[AgentMetrics]:
        """Get metrics for a specific agent."""
        return self.agent_metrics.get(agent_id)
        
    def get_all_metrics(self) -> Dict[str, AgentMetrics]:
        """Get metrics for all agents."""
        return self.agent_metrics
        
    def get_system_metrics(self) -> Dict[str, float]:
        """Get current system metrics."""
        return self.system_metrics
        
    async def stop(self):
        """Stop metrics collection."""
        self.running = False

# Global metrics instance
realtime_metrics = RealTimeMetrics()
```

### 4.2 Performance Dashboard Widget

**File:** `ferrox/ui/performance_widget.py`

```python
"""Performance monitoring widget for the dashboard."""

from textual.widgets import DataTable, ProgressBar
from textual.containers import Vertical
from textual import reactive
from ..metrics_realtime import realtime_metrics

class PerformanceWidget(Vertical):
    """Real-time performance monitoring widget."""
    
    def compose(self):
        yield DataTable(id="perf-table")
        yield ProgressBar(id="cpu-bar", show_eta=False)
        yield ProgressBar(id="memory-bar", show_eta=False)
        
    def on_mount(self):
        """Initialize performance widget."""
        self._update_interval = 1.0  # Update every second
        self._update_task = asyncio.create_task(self._update_loop())
        
    async def _update_loop(self):
        """Periodically update performance data."""
        while True:
            self._update_display()
            await asyncio.sleep(self._update_interval)
            
    def _update_display(self):
        """Update the performance display."""
        # Update system metrics
        sys_metrics = realtime_metrics.get_system_metrics()
        
        cpu_bar = self.query_one("#cpu-bar", ProgressBar)
        cpu_bar.progress = int(sys_metrics["cpu_percent"])
        
        memory_bar = self.query_one("#memory-bar", ProgressBar)
        memory_bar.progress = int(sys_metrics["memory_percent"])
        
        # Update agent metrics table
        table = self.query_one("#perf-table", DataTable)
        table.clear()
        table.add_column("Agent", width=15)
        table.add_column("Role", width=12)
        table.add_column("Completed", width=10)
        table.add_column("Failed", width=8)
        table.add_column("Last Activity", width=20)
        
        all_metrics = realtime_metrics.get_all_metrics()
        for agent_id, metrics in all_metrics.items():
            last_act = metrics.last_activity or datetime.now()
            time_since = (datetime.now() - last_act).total_seconds()
            time_str = f"{time_since:.0f}s ago" if time_since < 60 else f"{time_since/60:.0f}m ago"
            
            table.add_row(
                agent_id,
                metrics.agent_role,
                str(metrics.tasks_completed),
                str(metrics.tasks_failed),
                time_str
            )
```

---

## 🎯 Phase 5: UI/UX Enhancements

### 5.1 Enhanced Trace Viewer

**File:** `ferrox/ui/trace_viewer_enhanced.py`

```python
"""Enhanced real-time trace viewer with filtering and search."""

from textual.app import App, ComposeResult
from textual.widgets import (
    Log, Input, DataTable, Button, 
    Tabs, Tab, ContentSwitcher, FilterList
)
from textual.containers import Horizontal, Vertical
from textual import events
from ..agent.event_bus import event_bus, AgentEvent, EventType
from datetime import datetime

class EnhancedTraceViewer(App):
    """Enhanced trace viewer with real-time updates."""
    
    CSS = """
    Screen {
        layout: vertical;
    }
    
    #filter-input {
        dock: top;
    }
    
    #trace-log {
        height: 1fr;
    }
    
    #events-table {
        height: 1fr;
    }
    """
    
    def __init__(self):
        super().__init__()
        self.current_filter = ""
        self.selected_agent = "all"
        self.events = []
        
    def compose(self) -> ComposeResult:
        yield Input(placeholder="Filter events...", id="filter-input")
        yield Tabs(
            Tab("All Events", id="tab-all"),
            Tab("Thoughts", id="tab-thoughts"),
            Tab("Tool Calls", id="tab-tools"),
            Tab("Errors", id="tab-errors"),
        )
        yield ContentSwitcher(
            Log(id="trace-log"),
            DataTable(id="events-table"),
            id="content-switcher"
        )
        
    def on_mount(self) -> None:
        """Initialize trace viewer."""
        # Subscribe to all events
        for event_type in EventType:
            event_bus.subscribe(event_type, self._on_event)
            
        # Start event bus
        asyncio.create_task(event_bus.start())
        
    async def _on_event(self, event: AgentEvent):
        """Handle incoming events."""
        self.events.append(event)
        
        # Apply filter
        if self._passes_filter(event):
            self._add_event_to_display(event)
            
    def _passes_filter(self, event: AgentEvent) -> bool:
        """Check if event passes current filters."""
        # Agent filter
        if self.selected_agent != "all" and event.agent_id != self.selected_agent:
            return False
            
        # Text filter
        if self.current_filter:
            event_text = str(event.data).lower()
            if self.current_filter.lower() not in event_text:
                return False
                
        return True
        
    def _add_event_to_display(self, event: AgentEvent):
        """Add event to the appropriate display."""
        timestamp = event.timestamp.strftime("%H:%M:%S")
        
        # Add to log
        log = self.query_one("#trace-log", Log)
        log.write_line(f"[{timestamp}] {event.agent_id}: {event.event_type.value}")
        
        # Add to table
        table = self.query_one("#events-table", DataTable)
        table.add_row(
            timestamp,
            event.agent_id,
            event.agent_role,
            event.event_type.value,
            str(event.data)[:50]
        )
```

### 5.2 Color Scheme and Agent Identification

**File:** `ferrox/ui/theme.py`

```python
"""Color schemes and agent identification."""

AGENT_COLORS = {
    "main": "#00d4ff",      # Cyan
    "researcher": "#9b59b6",  # Purple
    "coder": "#2ecc71",      # Green
    "reviewer": "#e74c3c",   # Red
    "planner": "#f39c12",    # Orange
    "worker": "#3498db",     # Blue
}

AGENT_ICONS = {
    "main": "🦊",
    "researcher": "🔍",
    "coder": "💻",
    "reviewer": "👁️",
    "planner": "📋",
    "worker": "⚙️"
}

def get_agent_color(agent_role: str) -> str:
    """Get color for an agent role."""
    return AGENT_COLORS.get(agent_role, "#ffffff")
    
def get_agent_icon(agent_role: str) -> str:
    """Get icon for an agent role."""
    return AGENT_ICONS.get(agent_role, "🤖")
```

---

## 🚀 Phase 6: Integration & Testing

### 6.1 CLI Integration

**File:** `ferrox/cli.py` (final integration)

```python
# Add new imports
from .ui.dashboard import dashboard
from .agent.agent_pool import initialize_agent_pool
from .metrics_realtime import realtime_metrics

async def start_chat_loop(config: FerroxConfig):
    """Enhanced chat loop with real-time visualization."""
    
    # Check environment variables for features
    dashboard_enabled = os.getenv("FERROX_DASHBOARD", "false").lower() == "true"
    agent_pool_enabled = os.getenv("FERROX_AGENT_POOL", "true").lower() == "true"
    
    # Initialize agent pool if enabled
    if agent_pool_enabled:
        console.print("[dim]🔄 Initializing agent pool...[/dim]")
        await initialize_agent_pool(config, max_concurrent=4)
        console.print("[green]✅ Agent pool ready[/green]")
    
    # Start metrics collection
    await realtime_metrics.start()
    
    # Start dashboard if enabled
    if dashboard_enabled:
        console.print("[dim]🖥️  Starting dashboard...[/dim]")
        asyncio.create_task(dashboard.run_async())
        
        # Add main agent panel
        dashboard.add_agent_panel("main", "main")
        console.print("[green]✅ Dashboard running[/green]")
    
    # ... existing chat loop code ...
    
    # Enhanced commands for dashboard
    elif command == "/dashboard":
        if dashboard_enabled:
            console.print("[green]Dashboard already running[/green]")
        else:
            console.print("[yellow]Enable dashboard by setting FERROX_DASHBOARD=true[/yellow]")
        continue
        
    elif command == "/agents":
        from .agent.agent_pool import agent_pool
        if agent_pool:
            tasks = agent_pool.get_all_tasks()
            console.print(f"[cyan]Active Tasks: {len(tasks)}[/cyan]")
            for task in tasks:
                status_color = "green" if task.status == "completed" else "yellow"
                console.print(f"  [{status_color}]{task.task_id}[/] - {task.status}")
        else:
            console.print("[dim]Agent pool not enabled[/dim]")
        continue
```

### 6.2 Configuration Updates

**File:** `config.example.json`

```json
{
  "active_provider_id": "openai",
  "providers": {
    "openai": {
      "type": "openai",
      "base_url": "",
      "api_key": "your-api-key",
      "default_model": "gpt-4o"
    }
  },
  "dashboard": {
    "enabled": true,
    "refresh_rate": 1.0,
    "max_history": 1000
  },
  "agent_pool": {
    "enabled": true,
    "max_concurrent": 4,
    "task_timeout": 300
  },
  "metrics": {
    "enabled": true,
    "collection_interval": 5.0,
    "retention_hours": 24
  },
  "subagent_defaults": {
    "researcher": "openai:gpt-4o",
    "coder": "openai:gpt-4o",
    "reviewer": "openai:gpt-4o"
  }
}
```

---

## 📝 Implementation Priority

### Phase 1 (Week 1): Foundation
1. ✅ Install required dependencies
2. ✅ Implement event bus system
3. ✅ Enhance agent logging with event publishing
4. ✅ Test event bus functionality

### Phase 2 (Week 2): Dashboard UI
1. ✅ Implement Textual-based dashboard
2. ✅ Create agent panel components
3. ✅ Add metrics panel
4. ✅ Integrate with existing CLI

### Phase 3 (Week 3): Multi-Agent Coordination
1. ✅ Implement agent pool manager
2. ✅ Enhance subagent coordination
3. ✅ Add task queue visualization
4. ✅ Test concurrent agent execution

### Phase 4 (Week 4): Metrics & Monitoring
1. ✅ Implement real-time metrics collector
2. ✅ Add system resource monitoring
3. ✅ Create performance widgets
4. ✅ Add cost estimation

### Phase 5 (Week 5): UI/UX Polish
1. ✅ Enhance trace viewer
2. ✅ Add color schemes and icons
3. ✅ Implement filtering and search
4. ✅ Add export capabilities

### Phase 6 (Week 6): Integration & Testing
1. ✅ Full CLI integration
2. ✅ Configuration management
3. ✅ End-to-end testing
4. ✅ Documentation updates

---

## 🎯 Success Metrics

### Functional Requirements
- [ ] Real-time display of agent thoughts and tool calls
- [ ] Support for 4+ concurrent agents with individual panels
- [ ] Central metrics dashboard with system monitoring
- [ ] Task queue visualization with status tracking
- [ ] Search/filter functionality for event logs
- [ ] Export capabilities for agent traces

### Performance Requirements
- [ ] Event latency < 100ms from agent to dashboard
- [ ] Dashboard refresh rate ≥ 1 FPS
- [ ] Support for 1000+ events in history without lag
- [ ] Memory usage < 500MB for dashboard with 4 agents

### User Experience Requirements
- [ ] Intuitive multi-agent layout
- [ ] Clear visual distinction between agents
- [ ] Responsive UI during high agent activity
- [ ] Easy navigation and filtering of events

---

## 🔮 Future Enhancements

### Short-term (Post-Implementation)
1. **Web-based dashboard** - Browser-accessible dashboard
2. **Agent comparison** - Side-by-side performance comparison
3. **Custom layouts** - User-configurable dashboard layouts
4. **Alert system** - Notifications for important events

### Long-term
1. **ML-based optimization** - Learn optimal agent allocation
2. **Distributed agents** - Support for agents across multiple machines
3. **Collaborative mode** - Multiple users viewing same dashboard
4. **Historical analysis** - Trend analysis and reporting

---

## 📚 Documentation Requirements

1. **User Guide**
   - Dashboard quick start
   - Multi-agent coordination guide
   - Metrics interpretation
   - Troubleshooting

2. **Developer Guide**
   - Event bus API
   - Dashboard extension points
   - Custom agent integration
   - Metrics collection

3. **API Reference**
   - Event types and schemas
   - Dashboard widget API
   - Agent pool interface
   - Metrics API

---

## 🧪 Testing Strategy

### Unit Tests
- Event bus functionality
- Agent pool task scheduling
- Metrics collection accuracy
- Dashboard component rendering

### Integration Tests
- Multi-agent coordination
- Real-time event propagation
- Dashboard CLI integration
- Configuration loading

### Performance Tests
- Event throughput under load
- Dashboard responsiveness with many agents
- Memory usage over time
- System resource impact

### User Acceptance Tests
- Dashboard usability
- Multi-agent visibility
- Metrics accuracy
- Error handling

---

## 🎉 Conclusion

This comprehensive plan will transform FerroxCLI into a powerful multi-agent system with real-time visualization capabilities. The phased approach ensures manageable implementation while delivering incremental value. The focus on real-time feedback, multi-agent coordination, and enhanced monitoring will provide users with unprecedented visibility into AI agent behavior and performance.

The architecture is designed to be extensible, allowing for future enhancements like web-based dashboards, distributed agents, and ML-based optimization. With proper execution of this plan, FerroxCLI will become a leading tool for AI agent development and monitoring.
