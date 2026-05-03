# 🦊 FerroxCLI Real-Time Monitoring Guide

## 🎯 Overview

FerroxCLI now includes powerful real-time monitoring capabilities for multi-agent visualization, system metrics, and event tracking. This guide explains how to use these new features to monitor your AI agents in real-time.

## 🚀 Quick Start

### Enable Real-Time Monitoring

```bash
# Enable the real-time dashboard
export FERROX_DASHBOARD=true

# Enable the multi-agent pool
export FERROX_AGENT_POOL=true

# Start Ferrox
ferrox
```

### Windows (PowerShell)
```powershell
$env:FERROX_DASHBOARD="true"
$env:FERROX_AGENT_POOL="true"
ferrox
```

### Windows (CMD)
```cmd
set FERROX_DASHBOARD=true
set FERROX_AGENT_POOL=true
ferrox
```

## 🖥️ Real-Time Dashboard

The real-time dashboard provides a visual interface to monitor multiple agents simultaneously.

### Features

- **Agent Panels**: Individual panels for each agent showing:
  - Agent role and ID
  - Real-time thoughts and reasoning
  - Tool calls and results
  - Status indicators (thinking, executing, idle, error)

- **System Metrics Panel**: Live system monitoring including:
  - CPU usage
  - Memory usage
  - Disk usage
  - Uptime
  - Active agent count
  - Task completion statistics
  - Token usage
  - Average response times

### Starting the Dashboard

```bash
# Method 1: Environment variable (recommended)
export FERROX_DASHBOARD=true
ferrox

# Method 2: Check dashboard status from within Ferrox
/dashboard
```

### Dashboard Navigation

- **Ctrl+C**: Exit dashboard view
- **Tab**: Navigate between panels
- **Scroll**: View agent logs

## 🤖 Multi-Agent Pool

The agent pool manages multiple concurrent agents for parallel task execution.

### Features

- **Concurrent Execution**: Run up to 4 agents simultaneously
- **Task Queue**: Priority-based task scheduling
- **Load Balancing**: Automatic task distribution
- **Status Tracking**: Real-time task monitoring

### Enabling Agent Pool

```bash
export FERROX_AGENT_POOL=true
ferrox
```

### Monitoring Agent Pool

```bash
# From within Ferrox, use:
/agents
```

This displays:
- Total agents in pool
- Available agents
- Active tasks
- Queued tasks
- Completed tasks
- Active task details with assignment status

## 📊 System Metrics

Monitor system resources and agent performance in real-time.

### Viewing Metrics

```bash
# From within Ferrox, use:
/metrics
```

### Metrics Displayed

**Agent Metrics:**
- Active agents count
- Tasks completed
- Tasks failed
- Total tokens used
- Error count

**System Metrics:**
- CPU usage percentage
- Memory usage percentage
- Disk usage percentage
- System uptime

## 📋 Event Tracking

View real-time events from all agents in the system.

### Viewing Events

```bash
# From within Ferrox, use:
/events
```

### Event Types

- **THOUGHT**: Agent reasoning and planning
- **TOOL_CALL**: Tool invocation with arguments
- **TOOL_RESULT**: Tool execution results
- **ERROR**: Error occurrences
- **STATUS_CHANGE**: Agent status updates
- **PROGRESS**: Task progress updates
- **METRIC**: System and performance metrics
- **AGENT_SPAWNED**: New agent creation
- **AGENT_TERMINATED**: Agent shutdown

## 🎛️ New Commands

### `/dashboard`
Check dashboard status and availability.

```
/dashboard
```

### `/agents`
Display agent pool status and active tasks.

```
/agents
```

Output:
```
🤖 Agent Pool Status
───────────────────────────────────────────────
● Total Agents: 4
● Available Agents: 3
● Active Tasks: 1
● Queued Tasks: 0
● Completed Tasks: 15
───────────────────────────────────────────────
```

### `/metrics`
Display comprehensive system and agent metrics.

```
/metrics
```

Output:
```
📊 System Metrics
───────────────────────────────────────────────
● Active Agents: 4
● Tasks Completed: 42
● Tasks Failed: 3
● Tokens Used: 125,890
● Errors: 7
───────────────────────────────────────────────
● CPU Usage: 45.2%
● Memory Usage: 62.8%
● Disk Usage: 78.1%
● Uptime: 3600s
───────────────────────────────────────────────
```

### `/events`
Show recent agent events.

```
/events
```

Output:
```
📋 Recent Events
───────────────────────────────────────────────
[14:32:15] main (main): thought
[14:32:16] main (main): tool_call
[14:32:17] main (main): tool_result
[14:32:18] worker-0 (worker): status_change
───────────────────────────────────────────────
```

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `FERROX_DASHBOARD` | Enable real-time dashboard | `false` |
| `FERROX_AGENT_POOL` | Enable multi-agent pool | `false` |

### Config File Updates

Add to your `config.json`:

```json
{
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
  }
}
```

## 🎨 Agent Roles and Icons

| Role | Icon | Description |
|------|------|-------------|
| main | 🦊 | Primary agent for user interactions |
| researcher | 🔍 | Research and documentation tasks |
| coder | 💻 | Code implementation tasks |
| reviewer | 👁️ | Code review and analysis |
| planner | 📋 | Task planning and coordination |
| worker | ⚙️ | General purpose worker agents |

## 📈 Use Cases

### 1. Monitor Single Agent Activity

```bash
# Start Ferrox with basic monitoring
export FERROX_DASHBOARD=true
ferrox

# Ask agent to perform a task
> Implement a REST API endpoint

# Watch real-time thoughts and tool calls in dashboard
# Press Ctrl+C to exit dashboard view
```

### 2. Parallel Task Execution

```bash
# Enable multi-agent pool
export FERROX_AGENT_POOL=true
ferrox

# Monitor agent pool status
/agents

# Submit multiple tasks (future feature)
> Research authentication methods
> Implement user login
> Review security implementation

# Watch parallel execution in dashboard
```

### 3. Performance Monitoring

```bash
# Enable all monitoring features
export FERROX_DASHBOARD=true
export FERROX_AGENT_POOL=true
ferrox

# Monitor system metrics during heavy workload
/metrics

# Check event stream for bottlenecks
/events
```

### 4. Debugging Agent Behavior

```bash
# Enable dashboard for visibility
export FERROX_DASHBOARD=true
ferrox

# Run task that needs debugging
> Fix the failing test

# Watch agent thoughts in real-time
# Identify where agent goes wrong
# Check tool call results
# View error events
```

## 🔍 Troubleshooting

### Dashboard Not Starting

**Problem**: Dashboard doesn't appear when `FERROX_DASHBOARD=true`

**Solutions**:
1. Verify environment variable is set: `echo $FERROX_DASHBOARD`
2. Check Textual is installed: `pip show textual`
3. Ensure terminal supports TUI: Try in a different terminal
4. Check for conflicting terminal applications

### Agent Pool Not Working

**Problem**: `/agents` shows "Agent pool not enabled"

**Solutions**:
1. Set environment variable: `export FERROX_AGENT_POOL=true`
2. Restart Ferrox after setting variable
3. Check config file for agent pool settings

### High Memory Usage

**Problem**: Dashboard using too much memory

**Solutions**:
1. Reduce event history in config: `"max_history": 500`
2. Disable dashboard if not needed
3. Increase metrics collection interval: `"collection_interval": 10.0`

### Events Not Showing

**Problem**: `/events` shows no recent events

**Solutions**:
1. Ensure event bus is running (check startup messages)
2. Verify agents are actively running tasks
3. Check event history limit (default: 50 events)

## 🎯 Best Practices

### 1. Start Simple

Begin with dashboard only to understand single-agent behavior:
```bash
export FERROX_DASHBOARD=true
ferrox
```

### 2. Scale Gradually

Add agent pool after understanding dashboard:
```bash
export FERROX_DASHBOARD=true
export FERROX_AGENT_POOL=true
ferrox
```

### 3. Monitor Resources

Keep an eye on system metrics during intensive tasks:
```bash
/metrics
```

### 4. Use Events for Debugging

When something goes wrong, check the event stream:
```bash
/events
```

### 5. Adjust Configuration

Tune settings based on your workload:
- Reduce history for lower memory usage
- Increase collection interval for less CPU overhead
- Adjust concurrent agents based on system capacity

## 🚀 Advanced Usage

### Programmatic Event Access

```python
from ferrox.agent.event_bus import event_bus, EventType

# Subscribe to specific events
def on_thought(event):
    print(f"Agent {event.agent_id} is thinking: {event.data['content']}")

event_bus.subscribe(EventType.THOUGHT, on_thought)

# Get recent events
recent = event_bus.get_recent_events(limit=100)

# Export event history
event_bus.export_history("events.json")
```

### Custom Metrics

```python
from ferrox.metrics_realtime import realtime_metrics

# Get agent-specific metrics
agent_metrics = realtime_metrics.get_agent_metrics("main")

# Get system metrics
sys_metrics = realtime_metrics.get_system_metrics()

# Get summary
summary = realtime_metrics.get_summary()
```

### Agent Pool Control

```python
from ferrox.agent.agent_pool import agent_pool

# Submit custom task
task_id = await agent_pool.submit_task(
    description="Analyze codebase structure",
    agent_role="researcher",
    priority=1
)

# Check task status
status = agent_pool.get_task_status(task_id)

# Get pool status
pool_status = agent_pool.get_pool_status()
```

## 📚 Architecture Overview

### Event Bus

The event bus is the core of the real-time monitoring system:

```
Agent Events → Event Bus → Subscribers
                          → Dashboard
                          → Metrics Collector
                          → Log Files
```

### Components

1. **Event Bus** (`ferrox/agent/event_bus.py`)
   - Pub/sub system for agent events
   - Event history management
   - Agent registry

2. **Metrics Collector** (`ferrox/metrics_realtime.py`)
   - System resource monitoring
   - Agent performance tracking
   - Aggregate statistics

3. **Dashboard** (`ferrox/ui/realtime_trace.py`)
   - Textual-based TUI
   - Agent panels
   - Metrics display

4. **Agent Pool** (`ferrox/agent/agent_pool.py`)
   - Concurrent agent management
   - Task queue and scheduling
   - Load balancing

## 🔮 Future Enhancements

Planned features for future releases:

- Web-based dashboard interface
- Historical event analysis
- Custom dashboard layouts
- Agent performance comparison
- Alert system for anomalies
- Distributed agent support
- ML-based optimization

## 🤝 Contributing

To contribute to the monitoring system:

1. Add new event types in `event_bus.py`
2. Implement new metrics in `metrics_realtime.py`
3. Create dashboard widgets in `realtime_trace.py`
4. Update documentation

## 📖 Additional Resources

- [Main README](README.md)
- [Improvement Plan](IMPROVEMENT_PLAN.md)
- [Configuration Guide](config.example.json)

---

**Note**: Real-time monitoring features are designed to have minimal performance impact. The event bus uses async operations and the dashboard updates at configurable intervals to ensure smooth operation even during intensive agent tasks.
