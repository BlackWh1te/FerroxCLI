"""Tests for fallback engine"""

from unittest.mock import MagicMock, patch

import pytest

from ferrox.config import FerroxConfig, ProviderConfig
from ferrox.fallback import FallbackEngine


@pytest.fixture
def mock_config():
    """Create a mock config with two providers"""
    config = MagicMock(spec=FerroxConfig)
    provider1 = MagicMock(spec=ProviderConfig)
    provider1.id = "openai"
    provider1.name = "OpenAI"
    provider1.base_url = "https://api.openai.com/v1"
    provider1.api_key = "sk-test"
    provider1.models = ["gpt-4o", "gpt-4o-mini"]
    provider1.last_used = None

    provider2 = MagicMock(spec=ProviderConfig)
    provider2.id = "ollama"
    provider2.name = "Ollama"
    provider2.base_url = "http://localhost:11434/v1"
    provider2.api_key = ""
    provider2.models = ["llama3.2"]
    provider2.last_used = None

    config.providers = [provider1, provider2]
    return config, provider1, provider2


class TestFallbackEngineInit:
    def test_init_populates_providers(self, mock_config):
        config, provider1, provider2 = mock_config
        engine = FallbackEngine(config)
        assert "openai" in engine.providers
        assert "ollama" in engine.providers
        assert engine.providers["openai"] == provider1

    def test_init_creates_permission_engine(self, mock_config):
        config, _, _ = mock_config
        engine = FallbackEngine(config)
        assert engine.permission_engine is not None


class TestSendWithFallback:
    @patch("ferrox.fallback.send_message_with_tools")
    @patch("ferrox.fallback.logger")
    async def test_success_first_model(self, mock_logger, mock_send, mock_config):
        config, provider1, _ = mock_config
        mock_send.return_value = ("Hello from AI", [])
        engine = FallbackEngine(config)

        result = await engine.send_with_fallback(
            messages=[{"role": "user", "content": "hi"}],
            active_provider_id="openai",
        )

        assert result["success"] is True
        assert result["provider"] == "OpenAI"
        assert result["model"] == "gpt-4o"
        assert result["content"] == "Hello from AI"
        mock_send.assert_called_once()

    @patch("ferrox.fallback.send_message_with_tools")
    @patch("ferrox.fallback.logger")
    async def test_fallback_to_second_model(self, mock_logger, mock_send, mock_config):
        config, provider1, _ = mock_config
        # First model fails, second succeeds
        mock_send.side_effect = [Exception("Rate limit"), ("Hello from AI", [])]
        engine = FallbackEngine(config)

        result = await engine.send_with_fallback(
            messages=[{"role": "user", "content": "hi"}],
            active_provider_id="openai",
        )

        assert result["success"] is True
        assert result["model"] == "gpt-4o-mini"
        assert mock_send.call_count == 2

    @patch("ferrox.fallback.send_message_with_tools")
    @patch("ferrox.fallback.logger")
    async def test_fallback_to_next_provider(self, mock_logger, mock_send, mock_config):
        config, provider1, provider2 = mock_config
        # All models in first provider fail, second provider succeeds
        mock_send.side_effect = [
            Exception("Rate limit"),
            Exception("Down"),
            ("Hello from Ollama", []),
        ]
        engine = FallbackEngine(config)

        result = await engine.send_with_fallback(
            messages=[{"role": "user", "content": "hi"}],
            active_provider_id="openai",
        )

        assert result["success"] is True
        assert result["provider"] == "Ollama"
        assert result["model"] == "llama3.2"
        assert "fallback_from" in result

    @patch("ferrox.fallback.send_message_with_tools")
    @patch("ferrox.fallback.logger")
    async def test_all_providers_fail(self, mock_logger, mock_send, mock_config):
        config, _, _ = mock_config
        mock_send.side_effect = Exception("All down")
        engine = FallbackEngine(config)

        with pytest.raises(RuntimeError, match="All providers and models failed"):
            await engine.send_with_fallback(
                messages=[{"role": "user", "content": "hi"}],
                active_provider_id="openai",
            )

    async def test_invalid_provider_id(self, mock_config):
        config, _, _ = mock_config
        engine = FallbackEngine(config)

        with pytest.raises(ValueError, match="Provider 'invalid' not found"):
            await engine.send_with_fallback(
                messages=[{"role": "user", "content": "hi"}],
                active_provider_id="invalid",
            )
