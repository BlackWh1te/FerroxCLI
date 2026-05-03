"""Agent pool management for concurrent agent execution."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from .event_bus import AgentEvent, EventType, event_bus
from .orchestrator import FerroxAgent


@dataclass
class AgentTask:
    """Represents a task to be executed by an agent."""
    task_id: str
    description: str
    agent_role: str
    priority: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    assigned_to: Optional[str] = None
    status: str = "pending"  # pending, running, completed, failed
    result: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert task to dictionary."""
        return {
            "task_id": self.task_id,
            "description": self.description,
            "agent_role": self.agent_role,
            "priority": self.priority,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "assigned_to": self.assigned_to,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class AgentPool:
    """Manages a pool of agents for concurrent task execution."""

    def __init__(self, config, max_concurrent: int = 4):
        self.config = config
        self.max_concurrent = max_concurrent
        self.agents: Dict[str, FerroxAgent] = {}
        self.task_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self.active_tasks: Dict[str, AgentTask] = {}
        self.completed_tasks: List[AgentTask] = []
        self.running = False
        self._task_counter = 0

    async def start(self):
        """Start the agent pool."""
        if self.running:
            return

        self.running = True

        # Initialize agents
        for i in range(self.max_concurrent):
            agent_id = f"worker-{i}"
            agent = FerroxAgent(self.config, agent_id, "worker")
            self.agents[agent_id] = agent

            # Publish agent spawned event
            await event_bus.publish(AgentEvent(
                event_type=EventType.AGENT_SPAWNED,
                agent_id=agent_id,
                agent_role="worker",
                timestamp=datetime.now(),
                data={"agent_id": agent_id}
            ))

        # Start task processor
        asyncio.create_task(self._process_tasks())

    async def submit_task(
        self,
        description: str,
        agent_role: str = "worker",
        priority: int = 0
    ) -> str:
        """
        Submit a task to the pool.

        Args:
            description: Task description
            agent_role: Type of agent needed for the task
            priority: Task priority (lower = higher priority)

        Returns:
            Task ID
        """
        self._task_counter += 1
        task_id = f"{agent_role}-{self._task_counter}"

        task = AgentTask(
            task_id=task_id,
            description=description,
            agent_role=agent_role,
            priority=priority
        )

        # Add to priority queue (negative priority for max-heap behavior)
        await self.task_queue.put((-priority, self._task_counter, task))

        # Publish task submission event
        await event_bus.publish(AgentEvent(
            event_type=EventType.STATUS_CHANGE,
            agent_id="pool",
            agent_role="pool",
            timestamp=datetime.now(),
            data={"task_id": task_id, "status": "queued"}
        ))

        return task_id

    async def _process_tasks(self):
        """Process tasks from the queue."""
        while self.running:
            try:
                # Get next task (with timeout to allow checking running status)
                try:
                    priority, counter, task = await asyncio.wait_for(
                        self.task_queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                # Find available agent
                available_agent = self._get_available_agent()
                if not available_agent:
                    # No agents available, re-queue
                    await self.task_queue.put((priority, counter, task))
                    await asyncio.sleep(0.1)
                    continue

                # Assign task to agent
                task.assigned_to = available_agent.agent_id
                task.status = "running"
                task.started_at = datetime.now()
                self.active_tasks[task.task_id] = task

                # Publish task assignment event
                await event_bus.publish(AgentEvent(
                    event_type=EventType.STATUS_CHANGE,
                    agent_id=available_agent.agent_id,
                    agent_role=available_agent.agent_role,
                    timestamp=datetime.now(),
                    data={"task_id": task.task_id, "status": "started"}
                ))

                # Execute task
                asyncio.create_task(self._execute_task(task, available_agent))

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error processing task: {e}")

    def _get_available_agent(self) -> Optional[FerroxAgent]:
        """Get an available agent from the pool."""
        for agent_id, agent in self.agents.items():
            # Check if agent is not currently assigned to a running task
            is_busy = any(
                task.assigned_to == agent_id and task.status == "running"
                for task in self.active_tasks.values()
            )
            if not is_busy:
                return agent
        return None

    async def _execute_task(self, task: AgentTask, agent: FerroxAgent):
        """Execute a task with an agent."""
        try:
            # This is a simplified execution - in real implementation,
            # you would call agent.run() with proper parameters
            start_time = datetime.now()

            # Simulate task execution (replace with actual agent call)
            await asyncio.sleep(2)  # Simulate work

            # Calculate response time
            response_time = (datetime.now() - start_time).total_seconds()

            # Update task
            task.status = "completed"
            task.completed_at = datetime.now()
            task.result = "Task completed successfully"

            # Publish completion event with response time
            await event_bus.publish(AgentEvent(
                event_type=EventType.STATUS_CHANGE,
                agent_id=agent.agent_id,
                agent_role=agent.agent_role,
                timestamp=datetime.now(),
                data={
                    "task_id": task.task_id,
                    "status": "completed",
                    "response_time": response_time
                }
            ))

        except Exception as e:
            task.status = "failed"
            task.completed_at = datetime.now()
            task.error = str(e)

            await event_bus.publish(AgentEvent(
                event_type=EventType.ERROR,
                agent_id=agent.agent_id,
                agent_role=agent.agent_role,
                timestamp=datetime.now(),
                data={"task_id": task.task_id, "error": str(e)}
            ))

        finally:
            # Move to completed tasks
            if task.task_id in self.active_tasks:
                del self.active_tasks[task.task_id]
                self.completed_tasks.append(task)

                # Keep only last 100 completed tasks
                if len(self.completed_tasks) > 100:
                    self.completed_tasks.pop(0)

    def get_task_status(self, task_id: str) -> Optional[AgentTask]:
        """Get the status of a specific task."""
        # Check active tasks
        if task_id in self.active_tasks:
            return self.active_tasks[task_id]

        # Check completed tasks
        for task in self.completed_tasks:
            if task.task_id == task_id:
                return task

        return None

    def get_all_tasks(self) -> List[AgentTask]:
        """Get all active and recent tasks."""
        return list(self.active_tasks.values()) + self.completed_tasks

    def get_active_tasks(self) -> List[AgentTask]:
        """Get currently active tasks."""
        return list(self.active_tasks.values())

    def get_completed_tasks(self, limit: int = 10) -> List[AgentTask]:
        """Get recent completed tasks."""
        return self.completed_tasks[-limit:]

    def get_pool_status(self) -> dict:
        """Get overall pool status."""
        available_agents = sum(
            1 for agent_id in self.agents.keys()
            if not any(
                task.assigned_to == agent_id and task.status == "running"
                for task in self.active_tasks.values()
            )
        )

        return {
            "total_agents": len(self.agents),
            "available_agents": available_agents,
            "active_tasks": len(self.active_tasks),
            "queued_tasks": self.task_queue.qsize(),
            "completed_tasks": len(self.completed_tasks),
            "max_concurrent": self.max_concurrent
        }

    async def stop(self):
        """Stop the agent pool."""
        self.running = False

        # Terminate all agents
        for agent_id, agent in self.agents.items():
            await event_bus.publish(AgentEvent(
                event_type=EventType.AGENT_TERMINATED,
                agent_id=agent_id,
                agent_role=agent.agent_role,
                timestamp=datetime.now(),
                data={"agent_id": agent_id}
            ))


# Global agent pool instance
agent_pool = None


async def initialize_agent_pool(config, max_concurrent: int = 4):
    """Initialize the global agent pool."""
    global agent_pool
    agent_pool = AgentPool(config, max_concurrent)
    await agent_pool.start()
    return agent_pool
