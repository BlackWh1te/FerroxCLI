"""Configuration module for Ferrox CLI with multi-provider support"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Literal
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


from .providers.config import ProviderConfig, SubagentConfig
from .social_config import SocialConfig


class FerroxConfig(BaseModel):
    """Ferrox configuration with multi-provider support"""

    version: str = Field(default="1.2.0", description="Config version")
    providers: List[ProviderConfig] = Field(default_factory=list, description="List of providers")
    active_provider_id: Optional[str] = Field(default=None, description="Currently active provider")
    timeout: int = Field(default=30, description="Request timeout in seconds")
    max_tokens: int = Field(default=4096, description="Maximum tokens to generate")
    temperature: float = Field(default=0.7, description="Sampling temperature")
    subagent_defaults: Optional[SubagentConfig] = Field(
        default_factory=lambda: SubagentConfig(), description="Default models for subagents"
    )
    social: Optional[SocialConfig] = Field(
        default=None, description="X Bot social media configuration"
    )

    @field_validator("timeout")
    @classmethod
    def validate_timeout(cls, v: int) -> int:
        if v < 1 or v > 300:
            raise ValueError("timeout must be between 1 and 300 seconds")
        return v

    @field_validator("temperature")
    @classmethod
    def validate_temperature(cls, v: float) -> float:
        if v < 0 or v > 2:
            raise ValueError("temperature must be between 0 and 2")
        return v

    def get_active_provider(self) -> Optional[ProviderConfig]:
        """Get the currently active provider"""
        if not self.active_provider_id:
            return self.providers[0] if self.providers else None
        for p in self.providers:
            if p.id == self.active_provider_id:
                return p
        return self.providers[0] if self.providers else None

    def add_provider(self, provider: ProviderConfig) -> None:
        """Add a new provider and ensure it has a default model if possible"""
        if not provider.id:
            provider.id = f"provider_{len(self.providers) + 1}"
        if not provider.default_model and provider.models:
            provider.default_model = provider.models[0]
        self.providers.append(provider)
        if not self.active_provider_id:
            self.active_provider_id = provider.id

    def remove_provider(self, provider_id: str) -> bool:
        """Remove a provider by ID"""
        for i, p in enumerate(self.providers):
            if p.id == provider_id:
                self.providers.pop(i)
                if self.active_provider_id == provider_id:
                    self.active_provider_id = self.providers[0].id if self.providers else None
                return True
        return False


CONFIG_DIR = Path.home() / ".ferrox"
CONFIG_FILE = CONFIG_DIR / "config.json"
MODEL_CACHE_FILE = CONFIG_DIR / "model_cache.json"
DEBUG_LOG_FILE = CONFIG_DIR / "debug.log"


def ensure_config_dir() -> None:
    """Ensure the config directory exists"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def get_default_config() -> FerroxConfig:
    """Return a default configuration with Ollama as first provider and environment variable support"""
    return FerroxConfig(
        providers=[
            ProviderConfig(
                id="ollama-local",
                name="Ollama Local",
                type="ollama",
                base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
                api_key=os.getenv("OLLAMA_API_KEY", "ollama"),
                models=[],
                default_model=None,
            )
        ],
        active_provider_id="ollama-local",
        timeout=int(os.getenv("FERROX_TIMEOUT", "60")),
        max_tokens=int(os.getenv("FERROX_MAX_TOKENS", "4096")),
        temperature=float(os.getenv("FERROX_TEMPERATURE", "0.7")),
    )


def load_config() -> Optional[FerroxConfig]:
    """Load configuration from file"""
    from .exceptions import ConfigurationError, ValidationError

    if not CONFIG_FILE.exists():
        return None

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Handle old config format migration
        if "provider_name" in data and not data.get("providers"):
            old_provider = ProviderConfig(
                id="default",
                name=data.get("provider_name", "Custom"),
                type="custom",
                base_url=data.get("base_url", ""),
                api_key=data.get("api_key", ""),
                default_model=data.get("default_model"),
            )
            data["providers"] = [old_provider.model_dump()]
            data["active_provider_id"] = "default"
            data.pop("provider_name", None)
            data.pop("base_url", None)
            data.pop("api_key", None)
            data.pop("default_model", None)

        return FerroxConfig(**data)

    except json.JSONDecodeError as e:
        raise ConfigurationError(f"Invalid JSON in config file: {e}", {"file": str(CONFIG_FILE)})
    except ValidationError as e:
        raise ConfigurationError(f"Config validation failed: {e.message}", {"details": e.details})
    except PermissionError as e:
        raise ConfigurationError(
            f"Permission denied reading config: {e}", {"file": str(CONFIG_FILE)}
        )
    except Exception as e:
        raise ConfigurationError(f"Error loading config: {e}", {"file": str(CONFIG_FILE)})


def save_config(config: FerroxConfig) -> None:
    """Save configuration to file"""
    ensure_config_dir()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config.model_dump(), f, indent=2, default=str)


def validate_config(config: FerroxConfig) -> tuple[bool, Optional[str]]:
    """Validate configuration completeness"""
    provider = config.get_active_provider()
    if not provider:
        return False, "No providers configured"

    if not provider.base_url:
        return False, "Provider base_url is required"

    return True, None


def get_model_cache() -> dict:
    """Get cached model list"""
    if not MODEL_CACHE_FILE.exists():
        return {}

    try:
        with open(MODEL_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_model_cache(data: dict) -> None:
    """Save model list cache"""
    ensure_config_dir()
    with open(MODEL_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get_editor() -> str:
    """Get the user's preferred editor"""
    return (
        os.environ.get("EDITOR")
        or os.environ.get("VISUAL")
        or ("code" if os.name == "nt" else ("vim" if which("vim") else "nano"))
    )


def which(cmd: str) -> bool:
    """Check if command exists in PATH"""
    import shutil

    return shutil.which(cmd) is not None
