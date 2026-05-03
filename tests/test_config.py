"""Tests for ferrox.config module"""
import pytest
from ferrox.config import FerroxConfig, get_default_config, validate_config


def test_default_config_creation():
    """Test that default config can be created"""
    config = get_default_config()
    assert isinstance(config, FerroxConfig)
    assert len(config.providers) > 0


def test_config_validation():
    """Test config validation"""
    config = get_default_config()
    is_valid, error = validate_config(config)
    assert is_valid is True
    assert error is None


def test_config_validation_invalid():
    """Test config validation with invalid config"""
    config = FerroxConfig(providers=[])
    is_valid, error = validate_config(config)
    assert is_valid is False
    assert error is not None


def test_config_get_active_provider():
    """Test getting active provider"""
    config = get_default_config()
    provider = config.get_active_provider()
    assert provider is not None
    assert provider.id is not None


def test_config_add_provider():
    """Test adding a new provider"""
    config = FerroxConfig(providers=[])
    from ferrox.providers.config import ProviderConfig
    
    new_provider = ProviderConfig(
        id="test-provider",
        name="Test Provider",
        type="custom",
        base_url="http://test.com",
        api_key="test-key"
    )
    
    config.add_provider(new_provider)
    assert len(config.providers) == 1
    assert config.providers[0].id == "test-provider"


def test_config_remove_provider():
    """Test removing a provider"""
    config = get_default_config()
    initial_count = len(config.providers)
    
    if initial_count > 0:
        provider_id = config.providers[0].id
        config.remove_provider(provider_id)
        assert len(config.providers) == initial_count - 1