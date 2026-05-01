import os
# OpenTelemetry tracer for tool-level spans
from ferrox.agent.orchestrator import tracer, _current_agent
from pydantic_ai import RunContext
from ..tools import execute_read_file, execute_run_command, execute_list_directory
from ..utils.indexer import find_symbol_usage
from ..permissions import PermissionEngine, PermissionAction
from ..exceptions import PermissionDeniedError, FileAccessError, ToolExecutionError

# Shared permission engine
permissions = PermissionEngine()

async def read_file_tool(ctx: RunContext, path: str) -> str:
    """Read content from a text file."""
    with tracer.start_as_current_span("read_file_tool") as span:
        span.set_attribute("file_path", path)
        
        try:
            if not permissions.check_access(path, PermissionAction.READ):
                span.set_attribute("access", "denied")
                if _current_agent:
                    _current_agent._log_tool_call("read_file", {"path": path})
                    _current_agent._log_tool_result("read_file", "Access denied", False)
                raise PermissionDeniedError(f"Access denied to read: {path}", {"path": path})
            
            result = execute_read_file(path)
            
            if isinstance(result, dict) and not result.get("success"):
                error_msg = result.get("error", "Unknown error")
                span.set_attribute("error", error_msg)
                if _current_agent:
                    _current_agent._log_tool_call("read_file", {"path": path})
                    _current_agent._log_tool_result("read_file", error_msg, False)
                raise FileAccessError(f"Failed to read {path}: {error_msg}", {"path": path, "error": error_msg})
            
            content = result.get("content", "Error reading file") if isinstance(result, dict) else str(result)
            span.set_attribute("content_length", len(content) if isinstance(content, str) else 0)
            
            if _current_agent:
                _current_agent._log_tool_call("read_file", {"path": path})
                _current_agent._log_tool_result("read_file", f"Read {len(content) if isinstance(content, str) else 0} chars", True)
                
            return content
            
        except (PermissionDeniedError, FileAccessError):
            raise
        except Exception as e:
            span.set_attribute("error", str(e))
            if _current_agent:
                _current_agent._log_tool_call("read_file", {"path": path})
                _current_agent._log_tool_result("read_file", str(e), False)
            raise ToolExecutionError(f"Error reading file {path}: {e}", {"path": path})

async def write_file_tool(ctx: RunContext, path: str, content: str) -> str:
    """Write content to a file."""
    with tracer.start_as_current_span("write_file_tool") as span:
        span.set_attribute("file_path", path)
        span.set_attribute("content_length", len(content))
        
        try:
            if not permissions.check_access(path, PermissionAction.WRITE):
                span.set_attribute("access", "denied")
                if _current_agent:
                    _current_agent._log_tool_call("write_file", {"path": path, "content_len": len(content)})
                    _current_agent._log_tool_result("write_file", "Access denied", False)
                raise PermissionDeniedError(f"Access denied to write: {path}", {"path": path})
            
            from ..tools import execute_write_file
            result = execute_write_file(path, content)
            
            if "Error" in str(result):
                span.set_attribute("error", result)
                if _current_agent:
                    _current_agent._log_tool_call("write_file", {"path": path, "content_len": len(content)})
                    _current_agent._log_tool_result("write_file", result, False)
                raise FileAccessError(f"Failed to write {path}: {result}", {"path": path})
            
            if _current_agent:
                _current_agent._log_tool_call("write_file", {"path": path, "content_len": len(content)})
                _current_agent._log_tool_result("write_file", f"Wrote {len(content)} chars", True)
                
            return result
            
        except (PermissionDeniedError, FileAccessError):
            raise
        except Exception as e:
            span.set_attribute("error", str(e))
            if _current_agent:
                _current_agent._log_tool_call("write_file", {"path": path, "content_len": len(content)})
                _current_agent._log_tool_result("write_file", str(e), False)
            raise ToolExecutionError(f"Error writing file {path}: {e}", {"path": path})

async def run_command_tool(ctx: RunContext, command: str) -> str:
    """Execute a shell command."""
    with tracer.start_as_current_span("run_command_tool") as span:
        span.set_attribute("command", command)
        
        try:
            result = execute_run_command(command)
            
            if not result.get("success"):
                error_msg = result.get('error') or 'Command failed'
                span.set_attribute("error", error_msg)
                if _current_agent:
                    _current_agent._log_tool_call("run_command", {"command": command})
                    _current_agent._log_tool_result("run_command", error_msg, False)
                raise ToolExecutionError(f"Command failed: {error_msg}", {"command": command, "error": error_msg})
            
            span.set_attribute("stdout_len", len(result.get('stdout', "")))
            span.set_attribute("stderr_len", len(result.get('stderr', "")))
            span.set_attribute("exit_code", result.get('exit_code', 0))
            
            if _current_agent:
                _current_agent._log_tool_call("run_command", {"command": command})
                _current_agent._log_tool_result("run_command", f"Exit: {result.get('exit_code')}", True)
                
            return f"STDOUT: {result.get('stdout')}\nSTDERR: {result.get('stderr')}"
            
        except ToolExecutionError:
            raise
        except Exception as e:
            span.set_attribute("error", str(e))
            if _current_agent:
                _current_agent._log_tool_call("run_command", {"command": command})
                _current_agent._log_tool_result("run_command", str(e), False)
            raise ToolExecutionError(f"Error executing command: {e}", {"command": command})

async def list_directory_tool(ctx: RunContext, path: str = ".") -> str:
    """List files and directories in a path."""
    with tracer.start_as_current_span("list_directory_tool") as span:
        span.set_attribute("path", path)
        try:
            result = execute_list_directory(path)
            if _current_agent:
                _current_agent._log_tool_call("list_directory", {"path": path})
                _current_agent._log_tool_result("list_directory", result[:100], True)
            return result
        except Exception as e:
            if _current_agent:
                _current_agent._log_tool_call("list_directory", {"path": path})
                _current_agent._log_tool_result("list_directory", str(e), False)
            raise ToolExecutionError(f"Error listing directory: {e}", {"path": path})


async def search_code_tool(ctx: RunContext, symbol: str, path: str = ".") -> str:
    """Search for a symbol (function/class) usage in the codebase."""
    with tracer.start_as_current_span("search_code_tool") as span:
        span.set_attribute("symbol", symbol)
        span.set_attribute("path", path)
        try:
            import asyncio
            results = asyncio.run(find_symbol_usage(symbol, path))
            
            if not results:
                return f"No usages of '{symbol}' found in {path}"
            
            output = f"Found {len(results)} usages of '{symbol}':\n"
            output += "\n".join(results[:20])  # Limit to 20 results
            
            if _current_agent:
                _current_agent._log_tool_call("search_code", {"symbol": symbol, "path": path})
                _current_agent._log_tool_result("search_code", f"Found {len(results)} results", True)
                
            return output
        except Exception as e:
            if _current_agent:
                _current_agent._log_tool_call("search_code", {"symbol": symbol, "path": path})
                _current_agent._log_tool_result("search_code", str(e), False)
            raise ToolExecutionError(f"Error searching code: {e}", {"symbol": symbol})
