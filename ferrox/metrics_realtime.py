"""Real-time metrics collection and reporting."""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import psutil

from .agent.event_bus import AgentEvent, EventType, event_bus


@dataclass
class AgentMetrics:
    """Metrics for a single agent."""
    agent_id: str
    agent_role: str
    tasks_completed: int = 0
    tasks_failed: int = 0
    total_tokens_used: int = 0
    total_response_time: float = 0.0
    avg_response_time: float = 0.0
    last_activity: Optional[datetime] = None
    tool_calls_count: int = 0
    thoughts_count: int = 0
    errors_count: int = 0

    def update_response_time(self, response_time: float):
        """Update average response time."""
        self.total_response_time += response_time
        count = self.tasks_completed + self.tasks_failed
        if count > 0:
            self.avg_response_time = self.total_response_time / count


@dataclass
class SystemMetrics:
    """System-level metrics."""
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_used_mb: float = 0.0
    memory_total_mb: float = 0.0
    disk_usage_percent: float = 0.0
    disk_used_gb: float = 0.0
    disk_total_gb: float = 0.0
    network_sent_mb: float = 0.0
    network_recv_mb: float = 0.0
    process_count: int = 0
    uptime_seconds: float = 0.0


class RealTimeMetrics:
    """Real-time metrics collector for agent monitoring."""

    def __init__(self, collection_interval: float = 5.0):
        self.agent_metrics: dict[str, AgentMetrics] = {}
        self.system_metrics = SystemMetrics()
        self.collection_interval = collection_interval
        self.running = False
        self.start_time = datetime.now()
        self._last_network_stats = None

    async def start(self):
        """Start metrics collection."""
        if self.running:
            return

        self.running = True
        self.start_time = datetime.now()

        # Subscribe to events
        event_bus.subscribe(EventType.TOOL_RESULT, self._on_tool_result)
        event_bus.subscribe(EventType.STATUS_CHANGE, self._on_status_change)
        event_bus.subscribe(EventType.ERROR, self._on_error)
        event_bus.subscribe(EventType.AGENT_SPAWNED, self._on_agent_spawned)
        event_bus.subscribe(EventType.AGENT_TERMINATED, self._on_agent_terminated)

        # Start system metrics collection
        asyncio.create_task(self._collect_system_metrics())

        # Publish initial metrics
        asyncio.create_task(self._publish_metrics())

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

        metrics.tool_calls_count += 1
        metrics.last_activity = datetime.now()

        # Update token usage if available
        tokens = event.data.get('tokens_used', 0)
        if tokens:
            metrics.total_tokens_used += tokens

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
        event.data.get('status')

        if agent_id not in self.agent_metrics:
            self.agent_metrics[agent_id] = AgentMetrics(
                agent_id=agent_id,
                agent_role=event.agent_role
            )

        self.agent_metrics[agent_id].last_activity = datetime.now()

        # Track response time if available
        response_time = event.data.get('response_time')
        if response_time:
            self.agent_metrics[agent_id].update_response_time(response_time)

    async def _on_error(self, event: AgentEvent):
        """Track errors."""
        agent_id = event.agent_id

        if agent_id not in self.agent_metrics:
            self.agent_metrics[agent_id] = AgentMetrics(
                agent_id=agent_id,
                agent_role=event.agent_role
            )

        self.agent_metrics[agent_id].errors_count += 1
        self.agent_metrics[agent_id].last_activity = datetime.now()

    async def _on_agent_spawned(self, event: AgentEvent):
        """Track agent spawning."""
        agent_id = event.agent_id

        if agent_id not in self.agent_metrics:
            self.agent_metrics[agent_id] = AgentMetrics(
                agent_id=agent_id,
                agent_role=event.agent_role
            )

        self.agent_metrics[agent_id].last_activity = datetime.now()

    async def _on_agent_terminated(self, event: AgentEvent):
        """Track agent termination."""
        agent_id = event.agent_id

        if agent_id in self.agent_metrics:
            self.agent_metrics[agent_id].last_activity = datetime.now()

    async def _collect_system_metrics(self):
        """Collect system metrics periodically."""
        while self.running:
            try:
                # CPU metrics
                self.system_metrics.cpu_percent = psutil.cpu_percent(interval=0.1)

                # Memory metrics
                mem = psutil.virtual_memory()
                self.system_metrics.memory_percent = mem.percent
                self.system_metrics.memory_used_mb = mem.used / (1024 * 1024)
                self.system_metrics.memory_total_mb = mem.total / (1024 * 1024)

                # Disk metrics
                disk = psutil.disk_usage('/')
                self.system_metrics.disk_usage_percent = disk.percent
                self.system_metrics.disk_used_gb = disk.used / (1024 * 1024 * 1024)
                self.system_metrics.disk_total_gb = disk.total / (1024 * 1024 * 1024)

                # Network metrics
                net_io = psutil.net_io_counters()
                if self._last_network_stats:
                    self.system_metrics.network_sent_mb = (net_io.bytes_sent - self._last_network_stats.bytes_sent) / (1024 * 1024)
                    self.system_metrics.network_recv_mb = (net_io.bytes_recv - self._last_network_stats.bytes_recv) / (1024 * 1024)
                self._last_network_stats = net_io

                # Process count
                self.system_metrics.process_count = len(psutil.pids())

                # Uptime
                self.system_metrics.uptime_seconds = (datetime.now() - self.start_time).total_seconds()

                # Publish system metrics
                await event_bus.publish(AgentEvent(
                    event_type=EventType.METRIC,
                    agent_id="system",
                    agent_role="system",
                    timestamp=datetime.now(),
                    data={
                        "cpu_percent": self.system_metrics.cpu_percent,
                        "memory_percent": self.system_metrics.memory_percent,
                        "disk_usage_percent": self.system_metrics.disk_usage_percent,
                        "uptime_seconds": self.system_metrics.uptime_seconds
                    }
                ))

            except Exception as e:
                print(f"Error collecting system metrics: {e}")

            await asyncio.sleep(self.collection_interval)

    async def _publish_metrics(self):
        """Publish current metrics periodically."""
        while self.running:
            # Publish aggregate metrics
            total_tasks = sum(m.tasks_completed for m in self.agent_metrics.values())
            total_tokens = sum(m.total_tokens_used for m in self.agent_metrics.values())
            avg_response_time = 0.0

            if self.agent_metrics:
                avg_response_time = sum(m.avg_response_time for m in self.agent_metrics.values()) / len(self.agent_metrics)

            await event_bus.publish(AgentEvent(
                event_type=EventType.METRIC,
                agent_id="aggregate",
                agent_role="aggregate",
                timestamp=datetime.now(),
                data={
                    "total_tasks_completed": total_tasks,
                    "total_tokens_used": total_tokens,
                    "avg_response_time": avg_response_time,
                    "active_agents": len(self.agent_metrics)
                }
            ))

            await asyncio.sleep(self.collection_interval)

    def get_agent_metrics(self, agent_id: str) -> Optional[AgentMetrics]:
        """Get metrics for a specific agent."""
        return self.agent_metrics.get(agent_id)

    def get_all_metrics(self) -> dict[str, AgentMetrics]:
        """Get metrics for all agents."""
        return self.agent_metrics

    def get_system_metrics(self) -> SystemMetrics:
        """Get current system metrics."""
        return self.system_metrics

    def get_summary(self) -> dict[str, any]:
        """Get a summary of all metrics."""
        total_tasks = sum(m.tasks_completed for m in self.agent_metrics.values())
        total_failed = sum(m.tasks_failed for m in self.agent_metrics.values())
        total_tokens = sum(m.total_tokens_used for m in self.agent_metrics.values())
        total_errors = sum(m.errors_count for m in self.agent_metrics.values())

        return {
            "agents": {
                "total": len(self.agent_metrics),
                "active": len([m for m in self.agent_metrics.values() if m.last_activity and (datetime.now() - m.last_activity).total_seconds() < 60]),
                "tasks_completed": total_tasks,
                "tasks_failed": total_failed,
                "tokens_used": total_tokens,
                "errors": total_errors
            },
            "system": {
                "cpu_percent": self.system_metrics.cpu_percent,
                "memory_percent": self.system_metrics.memory_percent,
                "disk_usage_percent": self.system_metrics.disk_usage_percent,
                "uptime_seconds": self.system_metrics.uptime_seconds
            }
        }

    async def stop(self):
        """Stop metrics collection."""
        self.running = False


# Global metrics instance
realtime_metrics = RealTimeMetrics()
