"""OpenAI SDK integration for Ferrox"""

import os
from typing import List, Optional

from openai import AsyncOpenAI


class OpenAISDKProvider:
    """OpenAI SDK provider for Ferrox with official OpenAI client"""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

    async def chat_completion(
        self,
        messages: List[dict],
        model: str = "gpt-4",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """
        Send chat completion request to OpenAI

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model name to use
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            Response content as string
        """
        try:
            response = await self.client.chat.completions.create(
                model=model, messages=messages, temperature=temperature, max_tokens=max_tokens
            )
            return response.choices[0].message.content
        except Exception as e:
            raise Exception(f"OpenAI API error: {e}")

    async def list_models(self) -> List[str]:
        """List available models from OpenAI"""
        try:
            models = await self.client.models.list()
            return [model.id for model in models.data]
        except Exception as e:
            raise Exception(f"Failed to list OpenAI models: {e}")

    async def embed_text(self, text: str, model: str = "text-embedding-ada-002") -> List[float]:
        """
        Get embeddings for text

        Args:
            text: Text to embed
            model: Embedding model to use

        Returns:
            List of embedding values
        """
        try:
            response = await self.client.embeddings.create(model=model, input=text)
            return response.data[0].embedding
        except Exception as e:
            raise Exception(f"Failed to get embeddings: {e}")
