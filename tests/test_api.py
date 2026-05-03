"""Tests for ferrox.api module"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
import httpx
from ferrox.api import fetch_models, send_message, APIError, validate_provider
from ferrox.config import ProviderConfig, get_default_config


@pytest.fixture
def mock_provider():
    """Create a mock provider for testing"""
    return ProviderConfig(
        id="test-provider",
        name="Test Provider",
        type="openai",
        base_url="https://api.openai.com/v1",
        api_key="test-key",
        models=["gpt-4", "gpt-3.5-turbo"],
        default_model="gpt-4"
    )


@pytest.fixture
def mock_config(mock_provider):
    """Create a mock config with test provider"""
    from ferrox.config import FerroxConfig
    config = FerroxConfig(
        providers=[mock_provider],
        active_provider_id="test-provider"
    )
    return config


class TestFetchModels:
    """Test fetch_models function"""
    
    @patch('ferrox.api.httpx.AsyncClient')
    async def test_fetch_models_success(self, mock_client, mock_config):
        """Test successful model fetching"""
        # Mock the response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"id": "gpt-4", "object": "model"},
                {"id": "gpt-3.5-turbo", "object": "model"}
            ]
        }
        
        mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
        
        models = await fetch_models(mock_config)
        
        assert len(models) == 2
        assert models[0].id == "gpt-4"
        assert models[1].id == "gpt-3.5-turbo"
    
    @patch('ferrox.api.httpx.AsyncClient')
    async def test_fetch_models_api_error(self, mock_client, mock_config):
        """Test API error handling"""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        
        mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
        
        with pytest.raises(APIError) as exc_info:
            await fetch_models(mock_config)
        
        assert "401" in str(exc_info.value)
    
    @patch('ferrox.api.httpx.AsyncClient')
    async def test_fetch_models_network_error(self, mock_client, mock_config):
        """Test network error handling"""
        mock_client.return_value.__aenter__.return_value.get.side_effect = httpx.RequestError("Network error")
        
        with pytest.raises(APIError) as exc_info:
            await fetch_models(mock_config)
        
        assert "Network error" in str(exc_info.value)


class TestSendMessage:
    """Test send_message function"""
    
    @patch('ferrox.api.httpx.AsyncClient')
    async def test_send_message_success(self, mock_client, mock_config):
        """Test successful message sending"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": "Test response"
                }
            }]
        }
        
        mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
        
        messages = [{"role": "user", "content": "Test message"}]
        response = await send_message(mock_config, messages)
        
        assert response == "Test response"
    
    @patch('ferrox.api.httpx.AsyncClient')
    async def test_send_message_with_system_prompt(self, mock_client, mock_config):
        """Test message sending with system prompt"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": "Response with system prompt"
                }
            }]
        }
        
        mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
        
        messages = [
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": "Test message"}
        ]
        response = await send_message(mock_config, messages)
        
        assert response == "Response with system prompt"
    
    @patch('ferrox.api.httpx.AsyncClient')
    async def test_send_message_rate_limit(self, mock_client, mock_config):
        """Test rate limit error handling"""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.text = "Rate limit exceeded"
        
        mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
        
        messages = [{"role": "user", "content": "Test message"}]
        
        with pytest.raises(APIError) as exc_info:
            await send_message(mock_config, messages)
        
        assert "429" in str(exc_info.value)


class TestValidateProvider:
    """Test provider validation"""
    
    def test_validate_provider_valid(self, mock_provider):
        """Test validation of valid provider"""
        is_valid, error = validate_provider(mock_provider)
        assert is_valid is True
        assert error is None
    
    def test_validate_provider_missing_base_url(self):
        """Test validation fails with missing base_url"""
        provider = ProviderConfig(
            id="test",
            name="Test",
            type="openai",
            base_url="",
            api_key="test-key"
        )
        
        is_valid, error = validate_provider(provider)
        assert is_valid is False
        assert error is not None
    
    def test_validate_provider_missing_api_key(self):
        """Test validation fails with missing api_key"""
        provider = ProviderConfig(
            id="test",
            name="Test", 
            type="openai",
            base_url="https://api.openai.com/v1",
            api_key=""
        )
        
        is_valid, error = validate_provider(provider)
        assert is_valid is False
        assert error is not None