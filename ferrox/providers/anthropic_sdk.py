"""Anthropic SDK integration for Ferrox"""

import os
from anthropic import AsyncAnthropic
from typing import Optional, List


class AnthropicSDKProvider:
    """Anthropic SDK provider for Ferrox with official Anthropic client"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.client = AsyncAnthropic(api_key=self.api_key)

    async def message(
        self,
        messages: List[dict],
        model: str = "claude-3-sonnet-20240229",
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> str:
        """
        Send message request to Anthropic

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model name to use
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature

        Returns:
            Response content as string
        """
        try:
            # Convert messages to Anthropic format
            # Anthropic expects messages in format: [{"role": "user", "content": "..."}]
            # The last message should be from user

            # Extract system message if present
            system_message = None
            anthropic_messages = []

            for msg in messages:
                if msg.get("role") == "system":
                    system_message = msg.get("content")
                else:
                    anthropic_messages.append(
                        {"role": msg.get("role"), "content": msg.get("content")}
                    )

            response = await self.client.messages.create(
                model=model,
                messages=anthropic_messages,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_message,
            )

            # Extract text from response
            return response.content[0].text
        except Exception as e:
            raise Exception(f"Anthropic API error: {e}")

    async def list_models(self) -> List[str]:
        """List available models from Anthropic"""
        # Anthropic doesn't have a models endpoint, return known models
        return [
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307",
            "claude-2.1",
            "claude-2.0",
            "claude-instant-1.2",
        ]
