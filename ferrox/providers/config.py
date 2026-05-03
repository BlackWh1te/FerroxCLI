from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ProviderConfig(BaseModel):
    id: str
    name: str
    type: Literal["openai", "anthropic", "google", "ollama", "lm-studio", "vllm", "custom"]
    base_url: str
    api_key: Optional[str] = None
    models: List[str] = []
    default_model: Optional[str] = None
    last_used: Optional[datetime] = None
    is_validated: bool = False
    last_validated: Optional[datetime] = None


class SubagentConfig(BaseModel):
    """Configuration for subagent default models"""

    researcher: str = Field(default="ollama:llama3.2", description="Model for researcher subagent")
    coder: str = Field(default="ollama:qwen2.5-coder:7b", description="Model for coder subagent")
    reviewer: str = Field(default="ollama:llama3.2", description="Model for reviewer subagent")
