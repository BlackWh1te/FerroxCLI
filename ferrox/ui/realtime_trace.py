"""Real-time trace viewer using Textual framework."""

import asyncio

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Log,
    ProgressBar,
    Static,
)

from ..agent.event_bus import AgentEvent, EventType, event_bus
from ..metrics_realtime import realtime_metrics


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
        self.max_events = 100

    def compose(self) -> ComposeResult:
        yield Static(f"🤖 {self.agent_role.upper()} [{self.agent_id}]", id="agent-header")
        yield Log(id="agent-log", max_lines=50)
        yield ProgressBar(id="agent-progress", show_eta=False)

    def on_mount(self) -> None:
        """Subscribe to agent events."""
        self._update_header()
        event_bus.subscribe(EventType.THOUGHT, self._on_thought)
        event_bus.subscribe(EventType.TOOL_CALL, self._on_tool_call)
        event_bus.subscribe(EventType.TOOL_RESULT, self._on_tool_result)
        event_bus.subscribe(EventType.ERROR, self._on_error)

    def _update_header(self):
        """Update the header with current status."""
        header = self.query_one("#agent-header", Static)
        icon = self._get_agent_icon()
        header.update(f"{icon} {self.agent_role.upper()} [{self.agent_id}] - {self.status}")

    def _get_agent_icon(self) -> str:
        """Get icon for agent role."""
        icons = {
            "main": "🦊",
            "researcher": "🔍",
            "coder": "💻",
            "reviewer": "👁️",
            "planner": "📋",
            "worker": "⚙️"
        }
        return icons.get(self.agent_role, "🤖")

    async def _on_thought(self, event: AgentEvent):
        """Handle thought events for this agent."""
        if event.agent_id != self.agent_id:
            return

        log = self.query_one("#agent-log", Log)
        timestamp = event.timestamp.strftime("%H:%M:%S")
        content = event.data.get('content', '')[:100]
        log.write_line(f"[{timestamp}] 🧠 {content}")

        # Update status
        self.status = "thinking"
        self._update_header()

    async def _on_tool_call(self, event: AgentEvent):
        """Handle tool call events for this agent."""
        if event.agent_id != self.agent_id:
            return

        log = self.query_one("#agent-log", Log)
        timestamp = event.timestamp.strftime("%H:%M:%S")
        tool_name = event.data.get('tool_name', 'unknown')
        args = event.data.get('args', {})
        args_str = str(args)[:50] if args else ""
        log.write_line(f"[{timestamp}] 🛠️ {tool_name}({args_str})")

        # Update status
        self.status = "executing"
        self._update_header()

    async def _on_tool_result(self, event: AgentEvent):
        """Handle tool result events for this agent."""
        if event.agent_id != self.agent_id:
            return

        log = self.query_one("#agent-log", Log)
        timestamp = event.timestamp.strftime("%H:%M:%S")
        success = event.data.get('success', True)
        icon = "✅" if success else "❌"
        content = event.data.get('content', '')[:100]
        log.write_line(f"[{timestamp}] {icon} {content}")

        # Update status
        self.status = "idle"
        self._update_header()

    async def _on_error(self, event: AgentEvent):
        """Handle error events for this agent."""
        if event.agent_id != self.agent_id:
            return

        log = self.query_one("#agent-log", Log)
        timestamp = event.timestamp.strftime("%H:%M:%S")
        error = event.data.get('error', 'Unknown error')
        log.write_line(f"[{timestamp}] ❌ ERROR: {error}")

        # Update status
        self.status = "error"
        self._update_header()


class MetricsPanel(Vertical):
    """Central metrics and command panel."""

    def compose(self) -> ComposeResult:
        yield Static("📊 SYSTEM METRICS", id="metrics-header")
        yield DataTable(id="metrics-table")
        yield Static("", id="agent-summary")

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

        # Start update loop
        self._update_interval = 1.0
        self._update_task = asyncio.create_task(self._update_loop())

    async def _update_loop(self):
        """Periodically update metrics."""
        while True:
            self._update_display()
            await asyncio.sleep(self._update_interval)

    def _update_display(self):
        """Update the metrics display."""
        # Update metrics table
        table = self.query_one("#metrics-table", DataTable)
        table.clear()

        # Get system metrics
        sys_metrics = realtime_metrics.get_system_metrics()
        table.add_row("CPU Usage", f"{sys_metrics.cpu_percent:.1f}%")
        table.add_row("Memory Usage", f"{sys_metrics.memory_percent:.1f}%")
        table.add_row("Disk Usage", f"{sys_metrics.disk_usage_percent:.1f}%")
        table.add_row("Uptime", f"{sys_metrics.uptime_seconds:.0f}s")

        # Get agent metrics
        all_metrics = realtime_metrics.get_all_metrics()
        total_tasks = sum(m.tasks_completed for m in all_metrics.values())
        total_tokens = sum(m.total_tokens_used for m in all_metrics.values())
        avg_response = 0.0

        if all_metrics:
            avg_response = sum(m.avg_response_time for m in all_metrics.values()) / len(all_metrics)

        table.add_row("Active Agents", str(len(all_metrics)))
        table.add_row("Tasks Completed", str(total_tasks))
        table.add_row("Tokens Used", str(total_tokens))
        table.add_row("Avg Response", f"{avg_response:.2f}s")

        # Update agent summary
        summary = self.query_one("#agent-summary", Static)
        if all_metrics:
            summary_text = f"Monitoring {len(all_metrics)} agents"
        else:
            summary_text = "No active agents"
        summary.update(summary_text)


class RealTimeTraceViewer(App):
    """Main real-time trace viewer application."""

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
        margin: 1;
    }

    MetricsPanel {
        height: 25;
        border: solid blue;
        margin: 1;
    }

    Log {
        height: 1fr;
        scrollbar: true;
    }

    DataTable {
        height: 1fr;
    }

    #metrics-header {
        background: $secondary;
        color: $text;
        padding: 0 1;
        height: 2;
    }

    #agent-summary {
        padding: 0 1;
        height: 2;
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

        # Start metrics collection
        asyncio.create_task(realtime_metrics.start())

        # Subscribe to agent spawning events
        event_bus.subscribe(EventType.AGENT_SPAWNED, self._on_agent_spawned)
        event_bus.subscribe(EventType.AGENT_TERMINATED, self._on_agent_terminated)

        # Add main agent panel by default
        self.add_agent_panel("main", "main")

    async def _on_agent_spawned(self, event: AgentEvent):
        """Handle agent spawning."""
        agent_id = event.agent_id
        agent_role = event.agent_role

        if agent_id not in self.agent_panels:
            self.add_agent_panel(agent_id, agent_role)

    async def _on_agent_terminated(self, event: AgentEvent):
        """Handle agent termination."""
        agent_id = event.agent_id

        if agent_id in self.agent_panels and agent_id != "main":
            self.remove_agent_panel(agent_id)

    def add_agent_panel(self, agent_id: str, agent_role: str):
        """Add a new agent panel to the dashboard."""
        container = self.query_one("#agents-container")
        panel = AgentPanel(agent_id, agent_role)
        container.mount(panel)
        self.agent_panels[agent_id] = panel
        self.metrics["active_agents"] = len(self.agent_panels)

    def remove_agent_panel(self, agent_id: str):
        """Remove an agent panel from the dashboard."""
        if agent_id in self.agent_panels:
            self.agent_panels[agent_id].remove()
            del self.agent_panels[agent_id]
            self.metrics["active_agents"] = len(self.agent_panels)


# Global dashboard instance
dashboard = RealTimeTraceViewer()
