"""Real-time event bus for agent activities."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Any, Callable, Dict, List
import json


class EventType(Enum):
    """Types of agent events."""
    THOUGHT = "thought"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    ERROR = "error"
    STATUS_CHANGE = "status_change"
    PROGRESS = "progress"
    METRIC = "metric"
    AGENT_SPAWNED = "agent_spawned"
    AGENT_TERMINATED = "agent_terminated"


@dataclass
class AgentEvent:
    """Represents an event from an agent."""
    event_type: EventType
    agent_id: str
    agent_role: str  # "main", "researcher", "coder", "reviewer", "planner", "worker"
    timestamp: datetime
    data: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary for serialization."""
        return {
            "event_type": self.event_type.value,
            "agent_id": self.agent_id,
            "agent_role": self.agent_role,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentEvent":
        """Create event from dictionary."""
        return cls(
            event_type=EventType(data["event_type"]),
            agent_id=data["agent_id"],
            agent_role=data["agent_role"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            data=data["data"],
            metadata=data.get("metadata", {})
        )


class AgentEventBus:
    """Pub/sub event bus for real-time agent monitoring."""

    def __init__(self, max_history: int = 1000):
        self._subscribers: Dict[EventType, List[Callable]] = {}
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._event_history: List[AgentEvent] = []
        self._max_history = max_history
        self._running = False
        self._agent_registry: Dict[str, Dict[str, Any]] = {}  # Track active agents

    def subscribe(self, event_type: EventType, callback: Callable):
        """
        Subscribe to specific event types.

        Args:
            event_type: The type of event to subscribe to
            callback: Function to call when event occurs (can be sync or async)
        """
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: EventType, callback: Callable):
        """
        Unsubscribe from specific event types.

        Args:
            event_type: The type of event to unsubscribe from
            callback: The callback function to remove
        """
        if event_type in self._subscribers:
            self._subscribers[event_type] = [
                cb for cb in self._subscribers[event_type] if cb != callback
            ]

    async def publish(self, event: AgentEvent):
        """
        Publish event to all subscribers.

        Args:
            event: The event to publish
        """
        await self._event_queue.put(event)

    async def start(self):
        """Start event processing loop."""
        if self._running:
            return

        self._running = True
        asyncio.create_task(self._process_events())

    async def _process_events(self):
        """Process events from queue and notify subscribers."""
        while self._running:
            try:
                event = await self._event_queue.get()

                # Add to history
                self._event_history.append(event)
                if len(self._event_history) > self._max_history:
                    self._event_history.pop(0)

                # Update agent registry
                self._update_agent_registry(event)

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

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error processing event: {e}")

    def _update_agent_registry(self, event: AgentEvent):
        """Update agent registry based on events."""
        agent_id = event.agent_id

        if event.event_type == EventType.AGENT_SPAWNED:
            self._agent_registry[agent_id] = {
                "role": event.agent_role,
                "spawned_at": event.timestamp,
                "last_activity": event.timestamp,
                "status": "active"
            }
        elif event.event_type == EventType.AGENT_TERMINATED:
            if agent_id in self._agent_registry:
                self._agent_registry[agent_id]["status"] = "terminated"
                self._agent_registry[agent_id]["terminated_at"] = event.timestamp
        else:
            # Update last activity for any other event
            if agent_id in self._agent_registry:
                self._agent_registry[agent_id]["last_activity"] = event.timestamp

    def get_recent_events(
        self,
        agent_id: Optional[str] = None,
        event_type: Optional[EventType] = None,
        limit: int = 50
    ) -> List[AgentEvent]:
        """
        Get recent events, optionally filtered.

        Args:
            agent_id: Filter by specific agent ID
            event_type: Filter by event type
            limit: Maximum number of events to return

        Returns:
            List of matching events
        """
        events = self._event_history

        if agent_id:
            events = [e for e in events if e.agent_id == agent_id]

        if event_type:
            events = [e for e in events if e.event_type == event_type]

        return events[-limit:]

    def get_active_agents(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all active agents."""
        return {
            agent_id: info
            for agent_id, info in self._agent_registry.items()
            if info.get("status") == "active"
        }

    def get_agent_info(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific agent."""
        return self._agent_registry.get(agent_id)

    def clear_history(self):
        """Clear event history."""
        self._event_history.clear()

    def get_event_count(self, agent_id: Optional[str] = None) -> Dict[EventType, int]:
        """
        Get count of events by type, optionally filtered by agent.

        Args:
            agent_id: Filter by specific agent ID

        Returns:
            Dictionary mapping event types to counts
        """
        events = self._event_history
        if agent_id:
            events = [e for e in events if e.agent_id == agent_id]

        counts = {event_type: 0 for event_type in EventType}
        for event in events:
            counts[event.event_type] += 1

        return counts

    async def stop(self):
        """Stop event processing."""
        self._running = False

    def export_history(self, filepath: str):
        """
        Export event history to JSON file.

        Args:
            filepath: Path to export file
        """
        events_data = [event.to_dict() for event in self._event_history]
        with open(filepath, 'w') as f:
            json.dump(events_data, f, indent=2)


# Global event bus instance
event_bus = AgentEventBus()
