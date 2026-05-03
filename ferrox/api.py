"""API module for interacting with LLM providers"""

import json
import time
from collections.abc import Generator
from datetime import datetime
from typing import List, Optional

import httpx

from .config import FerroxConfig, ProviderConfig, get_model_cache, save_model_cache
from .exceptions import (
    APIError,
    AuthenticationError,
    ModelNotFoundError,
    NetworkError,
    ProviderError,
    RateLimitError,
    TimeoutError,
)
from .logger_new import logger
from .tools import execute_tool, get_available_tools


async def validate_provider(provider: ProviderConfig) -> tuple[bool, List[str], Optional[str]]:
    """Validate provider reachability and update models"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{provider.base_url}/models")
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("id") for m in data.get("data", []) if m.get("id")]
                provider.models = models
                if not provider.default_model and models:
                    provider.default_model = models[0]
                logger.info(f"Validated provider {provider.name}: {len(models)} models found")
                return True, models, None
            else:
                msg = f"Failed to validate provider {provider.name}: {resp.status_code}"
                logger.error(msg)
                return False, [], msg
    except Exception as e:
        msg = f"Error validating provider {provider.name}: {e}"
        logger.error(msg)
        return False, [], msg


def validate_and_update_provider(
    provider: ProviderConfig, config: FerroxConfig, save: bool = True
) -> ProviderConfig:
    """Validate provider and update its model list"""
    success, models, error = validate_provider(provider)

    provider.is_validated = success
    provider.last_validated = datetime.now()

    if success and models:
        provider.models = models
        if not provider.default_model:
            provider.default_model = models[0]

    if save:
        from .config import save_config

        save_config(config)

    return provider


def fetch_models(config: FerroxConfig, force_refresh: bool = False) -> list[ModelInfo]:
    """Fetch available models from the configured provider"""
    provider = config.get_active_provider()
    if not provider:
        return []

    cache = get_model_cache()
    cache_key = provider.base_url
    cache_duration = 3600

    if not force_refresh and cache_key in cache:
        cached_data = cache[cache_key]
        if time.time() - cached_data.get("timestamp", 0) < cache_duration:
            return [ModelInfo(**m) for m in cached_data.get("models", [])]

    url = f"{provider.base_url}/models"
    headers = {"Authorization": f"Bearer {provider.api_key}", "Content-Type": "application/json"}

    try:
        with httpx.Client(timeout=config.timeout) as client:
            response = client.get(url, headers=headers)

            if response.status_code != 200:
                raise APIError(f"Failed to fetch models: {response.text}", response.status_code)

            data = response.json()
            models = []

            if "data" in data:
                for m in data["data"]:
                    models.append(
                        ModelInfo(
                            id=m.get("id", ""),
                            name=m.get("id", ""),
                            description=m.get("description", ""),
                        )
                    )
            elif "models" in data:
                for m in data["models"]:
                    if isinstance(m, dict):
                        models.append(
                            ModelInfo(
                                id=m.get("id", m.get("name", "")),
                                name=m.get("name", m.get("id", "")),
                                description=m.get("description", ""),
                            )
                        )
                    else:
                        models.append(ModelInfo(id=str(m)))

            cache[cache_key] = {
                "models": [
                    {"id": m.id, "name": m.name, "description": m.description} for m in models
                ],
                "timestamp": time.time(),
            }
            save_model_cache(cache)

            return models

    except httpx.ConnectError as e:
        raise APIError(f"Connection error: {e}")
    except httpx.TimeoutException:
        raise APIError("Request timed out")
    except Exception as e:
        raise APIError(f"Error fetching models: {str(e)}")


def send_message(
    config: FerroxConfig, messages: list[dict], model: Optional[str] = None, stream: bool = True
) -> Generator[str, None, None]:
    """Send a chat message and yield response chunks"""
    provider = config.get_active_provider()
    if not provider:
        raise APIError("No active provider configured.")

    if model is None:
        model = provider.default_model

    if model is None:
        raise APIError("No model specified. Use /model to select one.")

    url = f"{provider.base_url}/chat/completions"
    headers = {"Authorization": f"Bearer {provider.api_key}", "Content-Type": "application/json"}

    payload = {
        "model": model,
        "messages": messages,
        "stream": stream,
        "max_tokens": config.max_tokens,
        "temperature": config.temperature,
    }

    try:
        with httpx.Client(timeout=config.timeout) as client:
            if stream:
                with client.stream("POST", url, json=payload, headers=headers) as response:
                    if response.status_code != 200:
                        error_body = response.text
                        raise APIError(f"API error: {error_body}", response.status_code)

                    for line in response.iter_lines():
                        if line:
                            if isinstance(line, bytes):
                                line = line.decode("utf-8")
                            if line.startswith("data: "):
                                data = line[6:]
                                if data == "[DONE]":
                                    break
                                try:
                                    import json

                                    chunk = json.loads(data)
                                    if "choices" in chunk and len(chunk["choices"]) > 0:
                                        delta = chunk["choices"][0].get("delta", {})
                                        content = delta.get("content", "")
                                        if content:
                                            yield content
                                except Exception:
                                    continue
            else:
                response = client.post(url, json=payload, headers=headers)
                if response.status_code != 200:
                    raise APIError(f"API error: {response.text}", response.status_code)

                data = response.json()
                if "choices" in data and len(data["choices"]) > 0:
                    yield data["choices"][0].get("message", {}).get("content", "")

    except httpx.ConnectError as e:
        raise NetworkError(f"Connection failed: {e}", {"url": url})
    except httpx.TimeoutException:
        raise TimeoutError("Request timed out", {"url": url, "timeout": config.timeout})
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code
        if status_code == 401:
            raise AuthenticationError("Authentication failed. Check your API key.", {"url": url})
        elif status_code == 403:
            raise AuthenticationError("Access forbidden. Check API key permissions.", {"url": url})
        elif status_code == 429:
            raise RateLimitError("Rate limit exceeded. Try again later.", {"url": url})
        elif status_code == 404:
            raise ModelNotFoundError(f"Model '{model}' not found", {"model": model})
        else:
            raise ProviderError(
                f"API error ({status_code}): {e.response.text}", {"status_code": status_code}
            )
    except Exception as e:
        raise APIError(f"Error sending message: {str(e)}")


class APIError(Exception):
    """Base class for API related errors"""

    def __init__(self, message, status_code=None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class ModelInfo:
    """Represents an LLM model"""

    def __init__(self, id: str, name: str = "", description: str = ""):
        self.id = id
        self.name = name or id
        self.description = description


class ToolCall:
    """Represents a tool call from the LLM"""

    def __init__(self, id: str, name: str, arguments: dict):
        self.id = id
        self.name = name
        self.arguments = arguments

    @classmethod
    def from_dict(cls, data: dict):
        """Create ToolCall from API response dictionary"""
        import json

        call_id = data.get("id", "")
        function = data.get("function", {})
        name = function.get("name", "")
        args_str = function.get("arguments", "{}")
        try:
            if isinstance(args_str, str):
                args = json.loads(args_str)
            else:
                args = args_str
        except json.JSONDecodeError:
            args = {}
        return cls(id=call_id, name=name, arguments=args)

    def to_dict(self):
        """Convert ToolCall back to dictionary format"""
        import json

        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.name, "arguments": json.dumps(self.arguments)},
        }


def send_message_with_tools(
    messages: List[dict],
    model: str,
    base_url: str,
    api_key: Optional[str] = None,
    tools_enabled: bool = True,
) -> tuple[str, List[ToolCall]]:
    """
    Send a chat message with tool support.
    """
    url = f"{base_url}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key or ''}", "Content-Type": "application/json"}

    payload = {"model": model, "messages": messages, "max_tokens": 4096, "temperature": 0.7}

    if tools_enabled:
        payload["tools"] = get_available_tools()
        payload["tool_choice"] = "auto"

    try:
        with httpx.Client(timeout=30) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()

            data = response.json()
            message = data.get("choices", [{}])[0].get("message", {})

            content = message.get("content", "")
            tool_calls = []

            if message.get("tool_calls"):
                for tc in message["tool_calls"]:
                    tool_calls.append(ToolCall.from_dict(tc))

            return content, tool_calls

    except Exception as e:
        logger.error(f"Error sending message to {model}: {e}")
        raise e


def execute_tool_calls(tool_calls: List[ToolCall]) -> List[dict]:
    """Execute tool calls and return tool results"""
    results = []
    for tc in tool_calls:
        result = execute_tool(tc.name, tc.arguments)
        results.append({"tool_call_id": tc.id, "name": tc.name, "content": result})
    return results


def parse_tool_from_text(text: str) -> Optional[ToolCall]:
    """Parse tool call from text response (fallback for models that don't use tool_calls)"""
    import re

    # Look for JSON-like tool calls in the response
    patterns = [
        r'\{["\']name["\']:\s*["\'](\w+)["\'],\s*["\']parameters["\']:\s*(\{[^}]+\})',
        r'"(\w+)"\s*:\s*\{[^}]*"parameters"[^}]*\}',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                tool_name = match.group(1)
                params_str = match.group(2) if match.lastindex >= 2 else "{}"

                # Clean up the parameters
                params_str = params_str.replace("'", '"')
                params = json.loads(params_str)

                return ToolCall(id=f"call_{tool_name}", name=tool_name, arguments=params)
            except (json.JSONDecodeError, AttributeError, ValueError):
                pass

    return None


SYSTEM_PROMPT = """You are Ferrox, an AI assistant. You have access to tools for file operations, but ONLY use them when the user explicitly asks for one of these actions:
- List files, show directory contents, what's in this folder
- Read a TEXT file (code, config, markdown, etc) - DO NOT try to read images, PDFs, or binary files
- Write to a file, create file, save content
- Run a command, execute something

IMPORTANT: You cannot read image files. If asked to view an image, explain that you can only read text files and ask the user to describe the image or provide text information about it.

For normal conversation (greetings, questions, general help), respond as a helpful assistant WITHOUT using tools. Do not list files or read files unless explicitly asked."""


def detect_tool_from_message(user_message: str) -> Optional[tuple]:
    """Detect if user message requires a tool based on keywords"""

    msg = user_message.lower()
    original = user_message

    # List/ls/directory
    if "list the" in msg or "list " in msg or "ls " in msg or "show files" in msg:
        return ("list_directory", {"path": "."})

    # Read file - simple pattern matching
    # Look for file extensions in the message
    import re

    file_pattern = (
        r"\b([a-zA-Z0-9_\-\.]+\.(?:py|toml|json|md|txt|sh|yml|yaml|html|css|js|ts|tsx|jsx))\b"
    )
    matches = re.findall(file_pattern, original)
    if matches:
        return ("read_file", {"file_path": matches[0]})

    # Also check for common filenames without extension
    common_files = ["readme", "config", "setup", "requirements"]
    for cf in common_files:
        if cf in msg:
            return ("read_file", {"file_path": cf})

    # Create/write file
    if "create " in msg or "write " in msg or "make " in msg:
        return ("write_file", {"file_path": "new_file.txt", "content": "New file content"})

    # Run command
    if "run " in msg or "execute " in msg or "run command" in msg:
        for prefix in ["run ", "execute "]:
            if prefix in msg:
                idx = msg.find(prefix)
                cmd = original[idx + len(prefix) :].strip()
                if cmd:
                    return ("run_command", {"command": cmd})

    return None


def send_message_with_tool_loop(
    config: FerroxConfig, messages: List[dict], model: Optional[str] = None, max_tool_calls: int = 5
) -> Generator[str, None, None]:
    """Send message with automatic tool execution loop."""
    provider = config.get_active_provider()
    if not provider:
        raise APIError("No active provider. Use /cfg to configure a provider.")

    # Use model from argument, then provider's default, then first available
    if model is None:
        model = provider.default_model
    if model is None and provider.models:
        model = provider.models[0]

    if model is None:
        raise APIError("No model specified. Use /model to select one.")

    if not any(m.get("role") == "system" for m in messages):
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages

    user_msg = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")

    tool_info = detect_tool_from_message(user_msg)
    if tool_info:
        from .ui.tool_logger import log_tool_execution

        tool_name, tool_args = tool_info
        result = execute_tool(tool_name, tool_args)
        log_tool_execution(tool_name, result)
        tool_call_id = f"auto_{tool_name}"
        messages.append(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": tool_call_id,
                        "type": "function",
                        "function": {"name": tool_name, "arguments": json.dumps(tool_args)},
                    }
                ],
            }
        )
        messages.append(
            {"role": "tool", "tool_call_id": tool_call_id, "name": tool_name, "content": result}
        )

    url = f"{provider.base_url}/chat/completions"
    headers = {"Authorization": f"Bearer {provider.api_key}", "Content-Type": "application/json"}

    for _ in range(max_tool_calls):
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
            "tools": get_available_tools(),
            "tool_choice": "auto",
        }

        try:
            with httpx.Client(timeout=config.timeout) as client:
                response = client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                message = data.get("choices", [{}])[0].get("message", {})

                content = message.get("content", "")
                tool_calls = []
                if message.get("tool_calls"):
                    tool_calls = [ToolCall.from_dict(tc) for tc in message["tool_calls"]]

                if not tool_calls and content.strip().startswith("{"):
                    parsed = parse_tool_from_text(content)
                    if parsed:
                        tool_calls = [parsed]
                        content = ""

                if tool_calls:
                    from .terminal import display_tool_output

                    for tc in tool_calls:
                        result = execute_tool(tc.name, tc.arguments)
                        display_tool_output(tc.name, result)

                    messages.append(
                        {
                            "role": "assistant",
                            "content": content,
                            "tool_calls": [
                                {
                                    "id": tc.id,
                                    "type": "function",
                                    "function": {
                                        "name": tc.name,
                                        "arguments": json.dumps(tc.arguments),
                                    },
                                }
                                for tc in tool_calls
                            ],
                        }
                    )
                    for tc in tool_calls:
                        result = execute_tool(tc.name, tc.arguments)
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "name": tc.name,
                                "content": result,
                            }
                        )
                    continue

                if content:
                    yield content
                break
        except httpx.HTTPError as e:
            raise APIError(f"API error: {str(e)}")
        except httpx.TimeoutException:
            raise APIError("Request timed out")
        except Exception as e:
            error_msg = str(e)
            if (
                "image" in error_msg.lower()
                or "vision" in error_msg.lower()
                or "image.png" in error_msg
            ):
                raise APIError(
                    "This model doesn't support image input. Please describe what you need instead."
                )
            raise APIError(f"Error: {error_msg}")
