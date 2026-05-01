import asyncio
import json
import os
from datetime import datetime
from .logger_new import logger
from .config import FerroxConfig
from .api import send_message_with_tools

from .permissions import PermissionEngine

class FallbackEngine:
    def __init__(self, config: FerroxConfig):
        self.config = config
        self.providers = {p.id: p for p in config.providers}
        self.permission_engine = PermissionEngine()
    
    async def send_with_fallback(self, messages: list, active_provider_id: str) -> dict:
        """
        Tries to send message using active provider's models in order.
        Falls back to next provider if all models fail.
        """
        active_provider = self.providers.get(active_provider_id)
        if not active_provider:
            raise ValueError(f"Provider '{active_provider_id}' not found in config.")
        
        # Try each model in active provider
        for model in active_provider.models:
            try:
                logger.info(f"Trying model: {model} on provider: {active_provider.name}")
                result, _ = send_message_with_tools(
                    messages=messages,
                    model=model,
                    base_url=active_provider.base_url,
                    api_key=active_provider.api_key
                )
                active_provider.last_used = datetime.utcnow()
                self._save_config()
                return {
                    "success": True,
                    "provider": active_provider.name,
                    "model": model,
                    "content": result
                }
            except Exception as e:
                logger.warning(f"Model {model} failed: {str(e)}")
                continue 
        
        # All models failed → try next provider
        for provider in self.config.providers:
            if provider.id == active_provider_id:
                continue
            
            # CHECK PERMISSIONS BEFORE FALLBACK
            if not self.permission_engine.is_provider_allowed(provider.id):
                logger.info(f"Skipping provider {provider.name} during fallback - Permission Denied")
                continue

            logger.info(f"Fallback triggered: Trying provider: {provider.name}")
            for model in provider.models:
                try:
                    result, _ = send_message_with_tools(
                        messages=messages,
                        model=model,
                        base_url=provider.base_url,
                        api_key=provider.api_key
                    )
                    provider.last_used = datetime.utcnow()
                    self._save_config()
                    return {
                        "success": True,
                        "provider": provider.name,
                        "model": model,
                        "content": result,
                        "fallback_from": active_provider.name
                    }
                except Exception as e:
                    logger.warning(f"Provider {provider.name}, Model {model} failed: {str(e)}")
                    continue
        
        raise RuntimeError(
            f"All providers and models failed. Last attempted: {active_provider.name}/{active_provider.models[-1] if active_provider.models else 'none'}\n"
            "💡 Fix: Check provider status with `/cfg` or run `ollama serve` if using local."
        )
    
    def _save_config(self):
        from .config import save_config
        save_config(self.config)
