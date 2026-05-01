from typing import List, Optional, Literal
from datetime import datetime
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
