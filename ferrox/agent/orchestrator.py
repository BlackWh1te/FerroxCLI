from pydantic_ai import Agent
from datetime import datetime
from ..exceptions import AgentError, ProviderError, NetworkError, TimeoutError, ModelNotFoundError

# OpenTelemetry tracing imports
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter

# Initialize tracer (console output for debugging)
trace.set_tracer_provider(TracerProvider())
tracer = trace.get_tracer(__name__)
span_processor = SimpleSpanProcessor(ConsoleSpanExporter())
trace.get_tracer_provider().add_span_processor(span_processor)

_current_agent = None

from .tools_pydantic import read_file_tool, write_file_tool, run_command_tool, list_directory_tool, search_code_tool
from ..config import FerroxConfig

class FerroxAgent:
    def __init__(self, config: FerroxConfig):
        global _current_agent
        self.config = config
        self.session_logs = []
        _current_agent = self
        self._agent = Agent(
            model='openai:gpt-4o', # Placeholder, will be dynamic
            system_prompt="You are Ferrox, a resilient engineering agent. Always check file access and use tools carefully."
        )
        self._agent.tool(read_file_tool)
        self._agent.tool(write_file_tool)
        self._agent.tool(run_command_tool)
        self._agent.tool(list_directory_tool)
        self._agent.tool(search_code_tool)

    async def run(self, user_prompt: str, model_id: str, history: list):
        # Start a tracing span for the agent execution
        with tracer.start_as_current_span("ferrox_agent_run") as span:
            # Record basic attributes
            span.set_attribute("model_id", model_id)
            span.set_attribute("prompt_length", len(user_prompt))
            
            try:
                # Dynamically set model based on config
                self._agent.model = model_id 
                
                result = await self._agent.run(
                    user_prompt,
                    message_history=history
                )
                return result
                
            except ModelNotFoundError as e:
                span.set_attribute("error", f"Model not found: {e}")
                self._log_thought(f"Error: Model {model_id} not found")
                raise ProviderError(f"Model '{model_id}' not found. Available models may have changed.", {"model": model_id})
                
            except InvalidRequestError as e:
                span.set_attribute("error", f"Invalid request: {e}")
                self._log_thought(f"Error: Invalid request - {e}")
                raise AgentError(f"Invalid request: {e}", {"details": str(e)})
                
            except TimeoutError as e:
                span.set_attribute("error", f"Timeout: {e}")
                self._log_thought(f"Error: Request timeout")
                raise TimeoutError("Agent request timed out", {"model": model_id})
                
            except Exception as e:
                error_type = type(e).__name__
                error_msg = str(e)
                span.set_attribute("error", f"{error_type}: {error_msg}")
                self._log_thought(f"Error: {error_type} - {error_msg}")
                
                # Re-raise as appropriate exception
                if "authentication" in error_msg.lower() or "api key" in error_msg.lower():
                    raise ProviderError(f"Authentication failed: {error_msg}", {"model": model_id})
                elif "rate limit" in error_msg.lower():
                    raise ProviderError(f"Rate limit exceeded: {error_msg}", {"model": model_id})
                elif "network" in error_msg.lower() or "connection" in error_msg.lower():
                    raise NetworkError(f"Network error: {error_msg}", {"model": model_id})
                else:
                    raise AgentError(f"Agent execution failed: {error_msg}", {"model": model_id})

    def _log(self, entry: dict):
        self.session_logs.append(entry)

    def _log_thought(self, content: str):
        self._log({"type": "thought", "content": content, "timestamp": datetime.now()})

    def _log_tool_call(self, name: str, args: dict):
        self._log({"type": "tool_call", "name": name, "args": args, "timestamp": datetime.now()})

    def _log_tool_result(self, name: str, result: str, success: bool):
        self._log({"type": "tool_result", "name": name, "content": result, "success": success, "timestamp": datetime.now()})

def get_current_session_logs():
    return _current_agent.session_logs if _current_agent else []
