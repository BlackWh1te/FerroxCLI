"""Tests for ferrox.agent.orchestrator module"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from ferrox.agent.orchestrator import FerroxAgent, AgentDeps, get_current_session_logs
from ferrox.config import get_default_config
from ferrox.modes import Mode


@pytest.fixture
def sample_config():
    """Create a sample configuration for testing"""
    return get_default_config()


@pytest.fixture
def sample_agent(sample_config):
    """Create a sample agent for testing"""
    return FerroxAgent(sample_config)


@pytest.fixture
def sample_deps():
    """Create sample dependencies for testing"""
    return AgentDeps(mode=Mode.NORMAL, config=get_default_config())


class TestFerroxAgentInit:
    """Test FerroxAgent initialization"""
    
    def test_agent_initialization(self, sample_config):
        """Test that agent initializes correctly"""
        agent = FerroxAgent(sample_config)
        assert agent.config == sample_config
        assert agent.session_logs == []
        assert agent._agent is not None
    
    def test_agent_model_selection(self, sample_config):
        """Test that agent selects correct model"""
        agent = FerroxAgent(sample_config)
        # The agent should have a model set
        assert agent._agent.model is not None


class TestAgentDeps:
    """Test AgentDeps dataclass"""
    
    def test_agent_deps_creation(self):
        """Test AgentDeps creation"""
        deps = AgentDeps(mode=Mode.NORMAL, config=get_default_config())
        assert deps.mode == Mode.NORMAL
        assert deps.config is not None
    
    def test_agent_deps_with_plan_mode(self):
        """Test AgentDeps with Plan mode"""
        deps = AgentDeps(mode=Mode.PLAN, config=get_default_config())
        assert deps.mode == Mode.PLAN


class TestAgentLogging:
    """Test agent logging functionality"""
    
    def test_log_thought(self, sample_agent):
        """Test thought logging"""
        sample_agent._log_thought("Test thought")
        assert len(sample_agent.session_logs) == 1
        assert sample_agent.session_logs[0]["type"] == "thought"
        assert sample_agent.session_logs[0]["content"] == "Test thought"
    
    def test_log_tool_call(self, sample_agent):
        """Test tool call logging"""
        sample_agent._log_tool_call("test_tool", {"arg1": "value1"})
        tool_logs = [log for log in sample_agent.session_logs if log["type"] == "tool_call"]
        assert len(tool_logs) == 1
        assert tool_logs[0]["name"] == "test_tool"
    
    def test_log_tool_result(self, sample_agent):
        """Test tool result logging"""
        sample_agent._log_tool_result("test_tool", "result", True)
        result_logs = [log for log in sample_agent.session_logs if log["type"] == "tool_result"]
        assert len(result_logs) == 1
        assert result_logs[0]["success"] is True


class TestGetModelFromConfig:
    """Test model selection from configuration"""
    
    def test_get_model_ollama_provider(self, sample_config):
        """Test model selection for Ollama provider"""
        agent = FerroxAgent(sample_config)
        model = agent._get_model_from_config()
        assert model is not None
    
    def test_get_model_custom_provider(self, sample_config):
        """Test model selection for custom provider"""
        # Modify config to use custom provider
        from ferrox.providers.config import ProviderConfig
        sample_config.providers[0] = ProviderConfig(
            id="custom",
            name="Custom",
            type="custom",
            base_url="http://localhost:8000/v1",
            api_key="test-key"
        )
        
        agent = FerroxAgent(sample_config)
        model = agent._get_model_from_config()
        assert model is not None


class TestConvertHistory:
    """Test history conversion for pydantic-ai"""
    
    def test_convert_user_message(self, sample_agent):
        """Test converting user message"""
        history = [{"role": "user", "content": "Test message"}]
        converted = sample_agent._convert_history(history)
        assert len(converted) == 1
        assert converted[0].parts[0].content == "Test message"
    
    def test_convert_assistant_message(self, sample_agent):
        """Test converting assistant message"""
        history = [{"role": "assistant", "content": "Test response"}]
        converted = sample_agent._convert_history(history)
        assert len(converted) == 1
        assert converted[0].parts[0].content == "Test response"
    
    def test_convert_system_message(self, sample_agent):
        """Test converting system message"""
        history = [{"role": "system", "content": "You are helpful"}]
        converted = sample_agent._convert_history(history)
        assert len(converted) == 1
        assert converted[0].parts[0].content == "You are helpful"
    
    def test_convert_mixed_history(self, sample_agent):
        """Test converting mixed message types"""
        history = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"}
        ]
        converted = sample_agent._convert_history(history)
        assert len(converted) == 3


class TestWebSearchDetection:
    """Test web search detection in prompts"""
    
    def test_detects_explicit_search(self, sample_agent):
        """Test detection of explicit search requests"""
        needs_search, query = sample_agent._needs_web_search("search for python tutorials")
        assert needs_search is True
        assert "python tutorials" in query.lower()
    
    def test_detects_question_starters(self, sample_agent):
        """Test detection of question-based queries"""
        needs_search, query = sample_agent._needs_web_search("what is the latest version of python")
        assert needs_search is True
        assert "latest version" in query.lower()
    
    def test_ignores_code_requests(self, sample_agent):
        """Test that code requests don't trigger search"""
        needs_search, query = sample_agent._needs_web_search("write a function to sort a list")
        assert needs_search is False
    
    def test_ignores_local_operations(self, sample_agent):
        """Test that local operations don't trigger search"""
        needs_search, query = sample_agent._needs_web_search("list files in current directory")
        assert needs_search is False


class TestGetCurrentSessionLogs:
    """Test getting current session logs"""

    def test_get_empty_logs(self):
        """Test getting logs when no agent exists"""
        logs = get_current_session_logs()
        assert logs == []

    def test_get_populated_logs(self, sample_agent):
        """Test getting logs from active agent"""
        sample_agent._log_thought("Test thought")
        sample_agent._log_tool_call("test_tool", {})
        logs = get_current_session_logs()
        assert len(logs) == 3