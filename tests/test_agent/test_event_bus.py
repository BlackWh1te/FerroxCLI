"""Tests for ferrox.agent.event_bus module"""

import asyncio
import json
import os
import tempfile
from datetime import datetime

import pytest

from ferrox.agent.event_bus import (
    AgentEvent,
    AgentEventBus,
    EventType,
    event_bus,
)


@pytest.fixture
def sample_event():
    """Create a sample agent event for testing"""
    return AgentEvent(
        event_type=EventType.THOUGHT,
        agent_id="test-agent",
        agent_role="coder",
        timestamp=datetime(2025, 1, 1, 12, 0, 0),
        data={"content": "Thinking about code"},
        metadata={"session": "abc"},
    )


@pytest.fixture
def fresh_bus():
    """Return a fresh AgentEventBus instance"""
    return AgentEventBus()


class TestAgentEvent:
    """Test AgentEvent dataclass"""

    def test_event_creation(self, sample_event):
        """Test that AgentEvent initializes correctly"""
        assert sample_event.event_type == EventType.THOUGHT
        assert sample_event.agent_id == "test-agent"
        assert sample_event.agent_role == "coder"
        assert sample_event.data == {"content": "Thinking about code"}
        assert sample_event.metadata == {"session": "abc"}

    def test_to_dict(self, sample_event):
        """Test serialization to dict"""
        d = sample_event.to_dict()
        assert d["event_type"] == "thought"
        assert d["agent_id"] == "test-agent"
        assert d["agent_role"] == "coder"
        assert d["data"] == {"content": "Thinking about code"}
        assert d["metadata"] == {"session": "abc"}
        assert "timestamp" in d

    def test_from_dict(self):
        """Test deserialization from dict"""
        d = {
            "event_type": "tool_call",
            "agent_id": "agent-1",
            "agent_role": "worker",
            "timestamp": "2025-06-15T10:30:00",
            "data": {"tool_name": "grep"},
            "metadata": {},
        }
        event = AgentEvent.from_dict(d)
        assert event.event_type == EventType.TOOL_CALL
        assert event.agent_id == "agent-1"
        assert event.data == {"tool_name": "grep"}

    def test_roundtrip(self, sample_event):
        """Test dict -> event -> dict roundtrip preserves data"""
        d1 = sample_event.to_dict()
        event2 = AgentEvent.from_dict(d1)
        d2 = event2.to_dict()
        assert d1 == d2


class TestAgentEventBusSubscribe:
    """Test subscription management"""

    def test_subscribe(self, fresh_bus):
        """Test subscribing to an event type"""
        calls = []

        def handler(event):
            calls.append(event)

        fresh_bus.subscribe(EventType.THOUGHT, handler)
        assert handler in fresh_bus._subscribers[EventType.THOUGHT]

    def test_unsubscribe(self, fresh_bus):
        """Test unsubscribing from an event type"""
        calls = []

        def handler(event):
            calls.append(event)

        fresh_bus.subscribe(EventType.THOUGHT, handler)
        fresh_bus.unsubscribe(EventType.THOUGHT, handler)
        assert handler not in fresh_bus._subscribers[EventType.THOUGHT]

    def test_unsubscribe_nonexistent(self, fresh_bus):
        """Test unsubscribing when not subscribed is a no-op"""

        def handler(event):
            pass

        # Should not raise
        fresh_bus.unsubscribe(EventType.ERROR, handler)


class TestAgentEventBusPublishSync:
    """Test synchronous publish wrapper"""

    def test_publish_sync_no_loop(self, fresh_bus, sample_event):
        """publish_sync records event directly when no loop is running"""
        fresh_bus.publish_sync(sample_event)
        assert sample_event in fresh_bus._event_history
        assert fresh_bus.get_active_agents()["test-agent"]["role"] == "coder"

    @pytest.mark.asyncio
    async def test_publish_sync_with_loop(self, fresh_bus, sample_event):
        """publish_sync queues event when a loop is running"""
        await fresh_bus.start()
        # Let the processor start
        await asyncio.sleep(0.01)
        fresh_bus.publish_sync(sample_event)
        # Give the loop a tick to process
        await asyncio.sleep(0.05)
        assert sample_event in fresh_bus._event_history
        await fresh_bus.stop()

    def test_publish_sync_updates_registry(self, fresh_bus):
        """publish_sync updates agent registry for spawned/terminated events"""
        spawn = AgentEvent(
            event_type=EventType.AGENT_SPAWNED,
            agent_id="a1",
            agent_role="reviewer",
            timestamp=datetime.now(),
            data={},
        )
        fresh_bus.publish_sync(spawn)
        assert "a1" in fresh_bus.get_active_agents()

        term = AgentEvent(
            event_type=EventType.AGENT_TERMINATED,
            agent_id="a1",
            agent_role="reviewer",
            timestamp=datetime.now(),
            data={},
        )
        fresh_bus.publish_sync(term)
        assert "a1" not in fresh_bus.get_active_agents()


class TestAgentEventBusAsyncPublish:
    """Test async publish path"""

    @pytest.mark.asyncio
    async def test_publish_queues_event(self, fresh_bus, sample_event):
        """async publish puts event into queue"""
        await fresh_bus.publish(sample_event)
        # Queue should have the event
        assert not fresh_bus._event_queue.empty()

    @pytest.mark.asyncio
    async def test_process_events_notifies_subscribers(self, fresh_bus, sample_event):
        """Event processor notifies subscribers"""
        received = []

        def handler(event):
            received.append(event)

        fresh_bus.subscribe(EventType.THOUGHT, handler)
        await fresh_bus.start()
        await fresh_bus.publish(sample_event)
        await asyncio.sleep(0.05)
        assert len(received) == 1
        assert received[0].agent_id == "test-agent"
        await fresh_bus.stop()

    @pytest.mark.asyncio
    async def test_process_events_async_subscriber(self, fresh_bus, sample_event):
        """Event processor handles async subscribers"""
        received = []

        async def handler(event):
            received.append(event)

        fresh_bus.subscribe(EventType.THOUGHT, handler)
        await fresh_bus.start()
        await fresh_bus.publish(sample_event)
        await asyncio.sleep(0.05)
        assert len(received) == 1
        await fresh_bus.stop()

    @pytest.mark.asyncio
    async def test_process_events_subscriber_exception(self, fresh_bus, sample_event, capsys):
        """Subscriber exceptions are caught and printed"""

        def bad_handler(event):
            raise ValueError("boom")

        fresh_bus.subscribe(EventType.THOUGHT, bad_handler)
        await fresh_bus.start()
        await fresh_bus.publish(sample_event)
        await asyncio.sleep(0.05)
        # Bus keeps running despite exception
        assert fresh_bus._running is True
        captured = capsys.readouterr()
        assert "Error in subscriber callback" in captured.out
        await fresh_bus.stop()

    @pytest.mark.asyncio
    async def test_start_idempotent(self, fresh_bus):
        """Calling start twice is safe"""
        await fresh_bus.start()
        await fresh_bus.start()
        assert fresh_bus._running is True
        await fresh_bus.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_loop(self, fresh_bus):
        """Stop terminates the event processing loop"""
        await fresh_bus.start()
        await fresh_bus.stop()
        assert fresh_bus._running is False


class TestAgentEventBusQueries:
    """Test query/history methods"""

    def test_get_recent_events(self, fresh_bus):
        """get_recent_events returns events in order"""
        for i in range(5):
            fresh_bus.publish_sync(
                AgentEvent(
                    event_type=EventType.THOUGHT,
                    agent_id="a1",
                    agent_role="main",
                    timestamp=datetime.now(),
                    data={"content": f"msg{i}"},
                )
            )
        events = fresh_bus.get_recent_events(limit=3)
        assert len(events) == 3
        assert events[0].data["content"] == "msg2"
        assert events[2].data["content"] == "msg4"

    def test_get_recent_events_filtered_by_agent(self, fresh_bus):
        """get_recent_events can filter by agent_id"""
        fresh_bus.publish_sync(
            AgentEvent(
                event_type=EventType.THOUGHT,
                agent_id="a1",
                agent_role="main",
                timestamp=datetime.now(),
                data={},
            )
        )
        fresh_bus.publish_sync(
            AgentEvent(
                event_type=EventType.THOUGHT,
                agent_id="a2",
                agent_role="main",
                timestamp=datetime.now(),
                data={},
            )
        )
        events = fresh_bus.get_recent_events(agent_id="a2")
        assert len(events) == 1
        assert events[0].agent_id == "a2"

    def test_get_recent_events_filtered_by_type(self, fresh_bus):
        """get_recent_events can filter by event_type"""
        fresh_bus.publish_sync(
            AgentEvent(
                event_type=EventType.THOUGHT,
                agent_id="a1",
                agent_role="main",
                timestamp=datetime.now(),
                data={},
            )
        )
        fresh_bus.publish_sync(
            AgentEvent(
                event_type=EventType.TOOL_CALL,
                agent_id="a1",
                agent_role="main",
                timestamp=datetime.now(),
                data={},
            )
        )
        events = fresh_bus.get_recent_events(event_type=EventType.TOOL_CALL)
        assert len(events) == 1
        assert events[0].event_type == EventType.TOOL_CALL

    def test_get_active_agents(self, fresh_bus):
        """get_active_agents returns only active agents"""
        fresh_bus.publish_sync(
            AgentEvent(
                event_type=EventType.AGENT_SPAWNED,
                agent_id="x1",
                agent_role="coder",
                timestamp=datetime.now(),
                data={},
            )
        )
        fresh_bus.publish_sync(
            AgentEvent(
                event_type=EventType.AGENT_TERMINATED,
                agent_id="x1",
                agent_role="coder",
                timestamp=datetime.now(),
                data={},
            )
        )
        assert fresh_bus.get_active_agents() == {}

    def test_get_agent_info(self, fresh_bus):
        """get_agent_info returns specific agent data"""
        fresh_bus.publish_sync(
            AgentEvent(
                event_type=EventType.AGENT_SPAWNED,
                agent_id="z1",
                agent_role="reviewer",
                timestamp=datetime.now(),
                data={},
            )
        )
        info = fresh_bus.get_agent_info("z1")
        assert info is not None
        assert info["role"] == "reviewer"
        assert info["status"] == "active"
        assert fresh_bus.get_agent_info("nonexistent") is None

    def test_get_event_count(self, fresh_bus):
        """get_event_count returns correct counts"""
        fresh_bus.publish_sync(
            AgentEvent(
                event_type=EventType.THOUGHT,
                agent_id="c1",
                agent_role="main",
                timestamp=datetime.now(),
                data={},
            )
        )
        fresh_bus.publish_sync(
            AgentEvent(
                event_type=EventType.THOUGHT,
                agent_id="c1",
                agent_role="main",
                timestamp=datetime.now(),
                data={},
            )
        )
        fresh_bus.publish_sync(
            AgentEvent(
                event_type=EventType.TOOL_CALL,
                agent_id="c1",
                agent_role="main",
                timestamp=datetime.now(),
                data={},
            )
        )
        counts = fresh_bus.get_event_count(agent_id="c1")
        assert counts[EventType.THOUGHT] == 2
        assert counts[EventType.TOOL_CALL] == 1
        assert counts[EventType.ERROR] == 0

    def test_clear_history(self, fresh_bus, sample_event):
        """clear_history empties the event list"""
        fresh_bus.publish_sync(sample_event)
        assert len(fresh_bus._event_history) == 1
        fresh_bus.clear_history()
        assert len(fresh_bus._event_history) == 0

    def test_max_history_truncation(self, fresh_bus):
        """Event history is truncated at max_history"""
        bus = AgentEventBus(max_history=3)
        for i in range(5):
            bus.publish_sync(
                AgentEvent(
                    event_type=EventType.METRIC,
                    agent_id="m1",
                    agent_role="main",
                    timestamp=datetime.now(),
                    data={"n": i},
                )
            )
        assert len(bus._event_history) == 3
        assert bus._event_history[0].data["n"] == 2
        assert bus._event_history[2].data["n"] == 4


class TestAgentEventBusExport:
    """Test export functionality"""

    def test_export_history(self, fresh_bus, sample_event):
        """export_history writes valid JSON"""
        fresh_bus.publish_sync(sample_event)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = f.name
        try:
            fresh_bus.export_history(path)
            with open(path) as f:
                data = json.load(f)
            assert len(data) == 1
            assert data[0]["agent_id"] == "test-agent"
        finally:
            os.unlink(path)


class TestGlobalEventBus:
    """Test the module-level global event_bus instance"""

    def test_global_instance_exists(self):
        """Module exposes a global AgentEventBus"""
        assert isinstance(event_bus, AgentEventBus)
