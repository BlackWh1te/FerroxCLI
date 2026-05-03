import httpx
from typing import List
from datetime import datetime
from .config import ProviderConfig
from ..logger_new import logger

DEFAULT_MODELS = {
    "openai": ["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
    "anthropic": [
        "claude-3-5-sonnet-20240620",
        "claude-3-opus-20240229",
        "claude-3-haiku-20240307",
    ],
    "google": ["gemini-1.5-pro-latest", "gemini-1.5-flash-latest"],
    "ollama": ["llama3.2:latest", "qwen2.5:7b", "mistral:latest"],
    "lm-studio": ["local-model"],
    "vllm": ["meta-llama/Llama-3.1-8B-Instruct"],
    "custom": ["custom-model"],
}


async def fetch_models_from_provider(provider: ProviderConfig) -> List[str]:
    """Dynamically fetches available models from the provider's API."""
    try:
        headers = {"Content-Type": "application/json"}
        if provider.api_key:
            headers["Authorization"] = f"Bearer {provider.api_key}"

        url = f"{provider.base_url.rstrip('/')}/models"

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)

            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    return [m.get("id", m) if isinstance(m, dict) else m for m in data]
                elif isinstance(data, dict) and "data" in data:
                    return [m["id"] for m in data["data"]]
                return DEFAULT_MODELS.get(provider.type, ["unknown-model"])
            else:
                logger.warning(
                    f"Failed to fetch models from {provider.name}: {response.status_code}"
                )
                return DEFAULT_MODELS.get(provider.type, ["unknown-model"])

    except Exception as e:
        logger.error(f"Error fetching models for {provider.name}: {str(e)}")
        return DEFAULT_MODELS.get(provider.type, ["unknown-model"])


async def validate_and_update_provider(provider: ProviderConfig) -> bool:
    """Validates a provider by fetching its models."""
    logger.info(f"Validating provider: {provider.name} ({provider.base_url})")

    models = await fetch_models_from_provider(provider)

    if models:
        provider.models = models
        provider.is_validated = True
        provider.last_validated = datetime.utcnow()
        if not provider.default_model or provider.default_model not in models:
            provider.default_model = models[0]
        return True
    return False
