import os
import asyncio
from pydantic_ai import RunContext
from ..tools import execute_read_file, execute_run_command, execute_list_directory
from ..utils.process_manager import process_manager
from ..permissions import PermissionEngine, PermissionAction
from ..modes import Mode
from ..exceptions import PermissionDeniedError, FileAccessError, ToolExecutionError

# Devin-style output formatters
try:
    from ..ui.output import (
        format_read_file_result,
        format_list_directory_result,
        format_shell_result,
        format_write_file_result,
        format_tool_call,
    )
except ImportError:
    format_read_file_result = None
    format_list_directory_result = None
    format_shell_result = None
    format_write_file_result = None
    format_tool_call = None

# Import tracer here (after other imports to avoid circular issues)
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

try:
    trace.set_tracer_provider(TracerProvider())
except:
    pass
tracer = trace.get_tracer(__name__)

# Import _current_agent with try/except to avoid circular import
try:
    from ferrox.agent.orchestrator import _current_agent
except ImportError:
    _current_agent = None

# Shared permission engine
permissions = PermissionEngine()


async def read_file_tool(ctx: RunContext, path: str) -> str:
    """Read content from a text file."""
    with tracer.start_as_current_span("read_file_tool") as span:
        span.set_attribute("file_path", path)

        try:
            # Get mode from deps if available
            mode = (
                ctx.deps.mode if hasattr(ctx, "deps") and hasattr(ctx.deps, "mode") else Mode.NORMAL
            )

            if not permissions.check_access(path, PermissionAction.READ, mode):
                span.set_attribute("access", "denied")
                error_msg = f"Error: Access denied to read: {path}"
                if _current_agent:
                    _current_agent._log_tool_call("read_file", {"path": path})
                    _current_agent._log_tool_result("read_file", error_msg, False)
                return error_msg

            if format_tool_call:
                format_tool_call("read_file", {"path": path})

            result = execute_read_file(path)

            if isinstance(result, dict) and not result.get("success"):
                error_msg = result.get("error", "Unknown error")
                span.set_attribute("error", error_msg)
                full_error = f"Error reading {path}: {error_msg}"
                if _current_agent:
                    _current_agent._log_tool_call("read_file", {"path": path})
                    _current_agent._log_tool_result("read_file", error_msg, False)
                return full_error

            content = (
                result.get("content", "Error reading file")
                if isinstance(result, dict)
                else str(result)
            )
            span.set_attribute("content_length", len(content) if isinstance(content, str) else 0)

            if format_read_file_result and isinstance(result, dict):
                format_read_file_result(result)

            if _current_agent:
                _current_agent._log_tool_call("read_file", {"path": path})
                _current_agent._log_tool_result(
                    "read_file",
                    f"Read {len(content) if isinstance(content, str) else 0} chars",
                    True,
                )

            return content

        except Exception as e:
            span.set_attribute("error", str(e))
            error_msg = f"Error: {str(e)}"
            if _current_agent:
                _current_agent._log_tool_call("read_file", {"path": path})
                _current_agent._log_tool_result("read_file", error_msg, False)
            return error_msg


async def write_file_tool(ctx: RunContext, path: str, content: str) -> str:
    """Write content to a file."""
    with tracer.start_as_current_span("write_file_tool") as span:
        span.set_attribute("file_path", path)
        span.set_attribute("content_length", len(content))

        try:
            # Get mode from deps if available
            mode = (
                ctx.deps.mode if hasattr(ctx, "deps") and hasattr(ctx.deps, "mode") else Mode.NORMAL
            )

            if not permissions.check_access(path, PermissionAction.WRITE, mode):
                span.set_attribute("access", "denied")
                error_msg = f"Error: Access denied to write: {path}"
                if _current_agent:
                    _current_agent._log_tool_call(
                        "write_file", {"path": path, "content_len": len(content)}
                    )
                    _current_agent._log_tool_result("write_file", error_msg, False)
                return error_msg

            from ..tools import execute_write_file

            if format_tool_call:
                format_tool_call("write_file", {"path": path, "content_len": len(content)})

            result = execute_write_file(path, content)

            if "Error" in str(result):
                span.set_attribute("error", result)
                if format_write_file_result:
                    format_write_file_result(path, len(content), success=False)
                if _current_agent:
                    _current_agent._log_tool_call(
                        "write_file", {"path": path, "content_len": len(content)}
                    )
                    _current_agent._log_tool_result("write_file", result, False)
                return f"Error: {result}"

            if format_write_file_result:
                format_write_file_result(path, len(content), success=True)

            if _current_agent:
                _current_agent._log_tool_call(
                    "write_file", {"path": path, "content_len": len(content)}
                )
                _current_agent._log_tool_result("write_file", f"Wrote {len(content)} chars", True)

            return result

        except Exception as e:
            span.set_attribute("error", str(e))
            error_msg = f"Error: {str(e)}"
            if _current_agent:
                _current_agent._log_tool_call(
                    "write_file", {"path": path, "content_len": len(content)}
                )
                _current_agent._log_tool_result("write_file", error_msg, False)
            return error_msg


async def run_command_tool(ctx: RunContext, command: str) -> str:
    """Execute a shell command."""
    with tracer.start_as_current_span("run_command_tool") as span:
        span.set_attribute("command", command)

        try:
            # Get mode from deps if available
            mode = (
                ctx.deps.mode if hasattr(ctx, "deps") and hasattr(ctx.deps, "mode") else Mode.NORMAL
            )

            # Note: execute_run_command doesn't currently take mode, but permissions check does
            if not permissions.check_access(
                command, PermissionAction.EXECUTE, mode, command=command
            ):
                span.set_attribute("access", "denied")
                error_msg = f"Error: Access denied to execute command: {command}"
                if _current_agent:
                    _current_agent._log_tool_call("run_command", {"command": command})
                    _current_agent._log_tool_result("run_command", error_msg, False)
                return error_msg

            if format_tool_call:
                format_tool_call("run_command", {"command": command})

            result = execute_run_command(command)

            if not result.get("success"):
                error_msg = result.get("error") or "Command failed"
                stdout = result.get("stdout", "")
                stderr = result.get("stderr", "")
                exit_code = result.get("exit_code", -1)

                span.set_attribute("error", error_msg)
                if format_shell_result:
                    format_shell_result(result)
                if _current_agent:
                    _current_agent._log_tool_call("run_command", {"command": command})
                    _current_agent._log_tool_result("run_command", error_msg, False)

                return f"Error: {error_msg}\nExit Code: {exit_code}\nSTDOUT: {stdout}\nSTDERR: {stderr}"

            span.set_attribute("stdout_len", len(result.get("stdout", "")))
            span.set_attribute("stderr_len", len(result.get("stderr", "")))
            span.set_attribute("exit_code", result.get("exit_code", 0))

            if format_shell_result:
                format_shell_result(result)

            if _current_agent:
                _current_agent._log_tool_call("run_command", {"command": command})
                _current_agent._log_tool_result(
                    "run_command", f"Exit: {result.get('exit_code')}", True
                )

            return f"STDOUT: {result.get('stdout')}\nSTDERR: {result.get('stderr')}"

        except Exception as e:
            span.set_attribute("error", str(e))
            error_msg = f"Error: {str(e)}"
            if _current_agent:
                _current_agent._log_tool_call("run_command", {"command": command})
                _current_agent._log_tool_result("run_command", error_msg, False)
            return error_msg


async def list_directory_tool(ctx: RunContext, path: str = ".") -> str:
    """List files and directories in a path."""
    with tracer.start_as_current_span("list_directory_tool") as span:
        span.set_attribute("path", path)
        try:
            # Get mode from deps if available
            mode = (
                ctx.deps.mode if hasattr(ctx, "deps") and hasattr(ctx.deps, "mode") else Mode.NORMAL
            )

            if not permissions.check_access(path, PermissionAction.READ, mode):
                span.set_attribute("access", "denied")
                error_msg = f"Error: Access denied to list directory: {path}"
                if _current_agent:
                    _current_agent._log_tool_call("list_directory", {"path": path})
                    _current_agent._log_tool_result("list_directory", error_msg, False)
                return error_msg

            if format_tool_call:
                format_tool_call("list_directory", {"path": path})

            result = execute_list_directory(path)

            if format_list_directory_result:
                format_list_directory_result(result)

            if _current_agent:
                _current_agent._log_tool_call("list_directory", {"path": path})
                _current_agent._log_tool_result("list_directory", result[:100], True)
            return result
        except Exception as e:
            error_msg = f"Error listing directory: {str(e)}"
            if _current_agent:
                _current_agent._log_tool_call("list_directory", {"path": path})
                _current_agent._log_tool_result("list_directory", error_msg, False)
            return error_msg


async def search_code_tool(ctx: RunContext, symbol: str, path: str = ".") -> str:
    """Search for a symbol (function/class) usage in the codebase."""
    with tracer.start_as_current_span("search_code_tool") as span:
        span.set_attribute("symbol", symbol)
        span.set_attribute("path", path)
        try:
            results = await find_symbol_usage(symbol, path)

            if not results:
                return f"No usages of '{symbol}' found in {path}"

            output = f"Found {len(results)} usages of '{symbol}':\n"
            output += "\n".join(results[:20])  # Limit to 20 results

            if _current_agent:
                _current_agent._log_tool_call("search_code", {"symbol": symbol, "path": path})
                _current_agent._log_tool_result(
                    "search_code", f"Found {len(results)} results", True
                )

            return output
        except Exception as e:
            if _current_agent:
                _current_agent._log_tool_call("search_code", {"symbol": symbol, "path": path})
                _current_agent._log_tool_result("search_code", str(e), False)
            raise ToolExecutionError(f"Error searching code: {e}", {"symbol": symbol})


async def run_background_tool(ctx: RunContext, command: str, cwd: str = ".") -> str:
    """Run a command in the background (non-blocking)."""
    with tracer.start_as_current_span("run_background_tool") as span:
        span.set_attribute("command", command)
        span.set_attribute("cwd", cwd)

        try:
            job = await process_manager.start_job(command, cwd)

            if _current_agent:
                _current_agent._log_tool_call("run_background", {"command": command, "cwd": cwd})
                _current_agent._log_tool_result("run_background", f"Started job {job.pid}", True)

            return f"✅ Started background job [PID: {job.pid}]\nCommand: {command}\nLog file: {job.log_file}\n\nUse /jobs to monitor or kill this job."

        except Exception as e:
            if _current_agent:
                _current_agent._log_tool_call("run_background", {"command": command})
                _current_agent._log_tool_result("run_background", str(e), False)
            raise ToolExecutionError(f"Error starting background job: {e}", {"command": command})


async def list_jobs_tool(ctx: RunContext) -> str:
    """List all background jobs."""
    with tracer.start_as_current_span("list_jobs_tool") as span:
        try:
            jobs = await process_manager.list_jobs()

            if not jobs:
                return "No background jobs running."

            output = "📋 Background Jobs:\n" + "=" * 60 + "\n"
            for job in jobs:
                status_emoji = "🟢" if job["status"] == "running" else "🔴"
                output += f"{status_emoji} PID: {job['pid']}\n"
                output += (
                    f"   Command: {job['command'][:60]}...\n"
                    if len(job["command"]) > 60
                    else f"   Command: {job['command']}\n"
                )
                output += f"   Status: {job['status']}\n"
                output += f"   Log: {job['log_file']}\n"
                output += "-" * 40 + "\n"

            if _current_agent:
                _current_agent._log_tool_call("list_jobs", {})
                _current_agent._log_tool_result("list_jobs", f"{len(jobs)} jobs", True)

            return output

        except Exception as e:
            if _current_agent:
                _current_agent._log_tool_call("list_jobs", {})
                _current_agent._log_tool_result("list_jobs", str(e), False)
            raise ToolExecutionError(f"Error listing jobs: {e}")


async def kill_job_tool(ctx: RunContext, pid: int) -> str:
    """Kill a background job by PID."""
    with tracer.start_as_current_span("kill_job_tool") as span:
        span.set_attribute("pid", pid)

        try:
            result = await process_manager.kill_job(pid)

            if _current_agent:
                _current_agent._log_tool_call("kill_job", {"pid": pid})
                _current_agent._log_tool_result(
                    "kill_job", str(result), result.get("success", False)
                )

            if result["success"]:
                return f"✅ {result['message']}"
            else:
                return f"❌ {result.get('error', 'Unknown error')}"

        except Exception as e:
            if _current_agent:
                _current_agent._log_tool_call("kill_job", {"pid": pid})
                _current_agent._log_tool_result("kill_job", str(e), False)
            raise ToolExecutionError(f"Error killing job: {e}", {"pid": pid})


async def get_job_logs_tool(ctx: RunContext, pid: int, lines: int = 50) -> str:
    """Get logs from a background job."""
    with tracer.start_as_current_span("get_job_logs_tool") as span:
        span.set_attribute("pid", pid)
        span.set_attribute("lines", lines)

        try:
            logs = await process_manager.get_job_logs(pid, lines)

            if _current_agent:
                _current_agent._log_tool_call("get_job_logs", {"pid": pid})
                _current_agent._log_tool_result("get_job_logs", "Retrieved logs", True)

            return f"📄 Logs for Job {pid} (last {lines} lines):\n" + "=" * 40 + "\n" + logs

        except Exception as e:
            if _current_agent:
                _current_agent._log_tool_call("get_job_logs", {"pid": pid})
                _current_agent._log_tool_result("get_job_logs", str(e), False)
            raise ToolExecutionError(f"Error getting job logs: {e}", {"pid": pid})


# === Package Manager Tools ===


async def pip_install_tool(
    ctx: RunContext, package: str, version: str = None, flags: str = ""
) -> str:
    """Install a Python package using pip."""
    with tracer.start_as_current_span("pip_install_tool") as span:
        span.set_attribute("package", package)

        try:
            version_str = f"=={version}" if version else ""
            flags_str = f" {flags}" if flags else ""
            cmd = f"pip install {package}{version_str}{flags_str}"

            result = await asyncio.create_subprocess_shell(
                cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                if _current_agent:
                    _current_agent._log_tool_call(
                        "pip_install", {"package": package, "version": version}
                    )
                    _current_agent._log_tool_result("pip_install", "Installed successfully", True)
                return f"✅ Installed {package}{version_str} successfully"
            else:
                error = stderr.decode() if stderr else "Unknown error"
                if _current_agent:
                    _current_agent._log_tool_call("pip_install", {"package": package})
                    _current_agent._log_tool_result("pip_install", error, False)
                return f"❌ Failed to install {package}: {error}"

        except Exception as e:
            if _current_agent:
                _current_agent._log_tool_call("pip_install", {"package": package})
                _current_agent._log_tool_result("pip_install", str(e), False)
            raise ToolExecutionError(f"Error installing pip package: {e}", {"package": package})


async def npm_install_tool(ctx: RunContext, package: str, flags: str = "-D") -> str:
    """Install an npm package."""
    with tracer.start_as_current_span("npm_install_tool") as span:
        span.set_attribute("package", package)
        span.set_attribute("flags", flags)

        try:
            flags_str = f" {flags}" if flags else ""
            cmd = f"npm install{flags_str} {package}"

            result = await asyncio.create_subprocess_shell(
                cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                if _current_agent:
                    _current_agent._log_tool_call(
                        "npm_install", {"package": package, "flags": flags}
                    )
                    _current_agent._log_tool_result("npm_install", "Installed successfully", True)
                return f"✅ Installed {package} via npm"
            else:
                error = stderr.decode() if stderr else "Unknown error"
                if _current_agent:
                    _current_agent._log_tool_call("npm_install", {"package": package})
                    _current_agent._log_tool_result("npm_install", error, False)
                return f"❌ Failed to install {package}: {error}"

        except Exception as e:
            if _current_agent:
                _current_agent._log_tool_call("npm_install", {"package": package})
                _current_agent._log_tool_result("npm_install", str(e), False)
            raise ToolExecutionError(f"Error installing npm package: {e}", {"package": package})


async def cargo_install_tool(ctx: RunContext, package: str, flags: str = "") -> str:
    """Install a Rust crate using cargo."""
    with tracer.start_as_current_span("cargo_install_tool") as span:
        span.set_attribute("package", package)

        try:
            flags_str = f" {flags}" if flags else ""
            cmd = f"cargo install{flags_str} {package}"

            result = await asyncio.create_subprocess_shell(
                cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                if _current_agent:
                    _current_agent._log_tool_call("cargo_install", {"package": package})
                    _current_agent._log_tool_result("cargo_install", "Installed successfully", True)
                return f"✅ Installed {package} via cargo"
            else:
                error = stderr.decode() if stderr else "Unknown error"
                if _current_agent:
                    _current_agent._log_tool_call("cargo_install", {"package": package})
                    _current_agent._log_tool_result("cargo_install", error, False)
                return f"❌ Failed to install {package}: {error}"

        except Exception as e:
            if _current_agent:
                _current_agent._log_tool_call("cargo_install", {"package": package})
                _current_agent._log_tool_result("cargo_install", str(e), False)
            raise ToolExecutionError(f"Error installing cargo package: {e}", {"package": package})


async def brew_install_tool(ctx: RunContext, package: str, flags: str = "") -> str:
    """Install a package using Homebrew."""
    with tracer.start_as_current_span("brew_install_tool") as span:
        span.set_attribute("package", package)

        try:
            flags_str = f" {flags}" if flags else ""
            cmd = f"brew install{flags_str} {package}"

            result = await asyncio.create_subprocess_shell(
                cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                if _current_agent:
                    _current_agent._log_tool_call("brew_install", {"package": package})
                    _current_agent._log_tool_result("brew_install", "Installed successfully", True)
                return f"✅ Installed {package} via Homebrew"
            else:
                error = stderr.decode() if stderr else "Unknown error"
                if _current_agent:
                    _current_agent._log_tool_call("brew_install", {"package": package})
                    _current_agent._log_tool_result("brew_install", error, False)
                return f"❌ Failed to install {package}: {error}"

        except Exception as e:
            if _current_agent:
                _current_agent._log_tool_call("brew_install", {"package": package})
                _current_agent._log_tool_result("brew_install", str(e), False)
            raise ToolExecutionError(f"Error installing brew package: {e}", {"package": package})


async def go_install_tool(ctx: RunContext, package: str) -> str:
    """Install a Go package."""
    with tracer.start_as_current_span("go_install_tool") as span:
        span.set_attribute("package", package)

        try:
            cmd = f"go install {package}"

            result = await asyncio.create_subprocess_shell(
                cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                if _current_agent:
                    _current_agent._log_tool_call("go_install", {"package": package})
                    _current_agent._log_tool_result("go_install", "Installed successfully", True)
                return f"✅ Installed {package} via go"
            else:
                error = stderr.decode() if stderr else "Unknown error"
                if _current_agent:
                    _current_agent._log_tool_call("go_install", {"package": package})
                    _current_agent._log_tool_result("go_install", error, False)
                return f"❌ Failed to install {package}: {error}"

        except Exception as e:
            if _current_agent:
                _current_agent._log_tool_call("go_install", {"package": package})
                _current_agent._log_tool_result("go_install", str(e), False)
            raise ToolExecutionError(f"Error installing go package: {e}", {"package": package})


async def fetch_url_tool(ctx: RunContext, url: str, max_chars: int = 8000) -> str:
    """Fetch the content of a web page using HTTP (no browser required)."""
    with tracer.start_as_current_span("fetch_url_tool") as span:
        span.set_attribute("url", url)
        span.set_attribute("max_chars", max_chars)

        try:
            import httpx

            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()

                content_type = resp.headers.get("content-type", "").lower()
                text = resp.text

                if len(text) > max_chars:
                    text = (
                        text[:max_chars]
                        + f"\n\n... ({len(resp.text) - max_chars} more chars truncated)"
                    )

                if _current_agent:
                    _current_agent._log_tool_call("fetch_url", {"url": url})
                    _current_agent._log_tool_result(
                        "fetch_url", f"Fetched {len(resp.text)} chars", True
                    )

                return f"URL: {resp.url}\nStatus: {resp.status_code}\nContent-Type: {content_type}\n\n{text}"

        except ImportError:
            return "Error: httpx is not installed. Run: pip install httpx"
        except httpx.HTTPError as e:
            return f"HTTP error fetching {url}: {e}"
        except Exception as e:
            if _current_agent:
                _current_agent._log_tool_call("fetch_url", {"url": url})
                _current_agent._log_tool_result("fetch_url", str(e), False)
            return f"Error fetching {url}: {e}"


async def webfetch_tool(ctx: RunContext, url: str, max_chars: int = 8000) -> str:
    """Fetch a web page and return its text content. Use this for GitHub, docs, or any public URL."""
    with tracer.start_as_current_span("webfetch_tool") as span:
        span.set_attribute("url", url)
        span.set_attribute("max_chars", max_chars)
        if format_tool_call:
            format_tool_call("webfetch", {"url": url})
        try:
            import httpx

            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                text = resp.text
                if len(text) > max_chars:
                    text = (
                        text[:max_chars] + f"\n\n... ({len(text) - max_chars} more chars truncated)"
                    )
                if _current_agent:
                    _current_agent._log_tool_call("webfetch", {"url": url})
                    _current_agent._log_tool_result("webfetch", f"Fetched {len(text)} chars", True)
                return text
        except ImportError:
            return "Error: httpx is not installed. Run: pip install httpx"
        except httpx.HTTPError as e:
            return f"HTTP error fetching {url}: {e}"
        except Exception as e:
            if _current_agent:
                _current_agent._log_tool_call("webfetch", {"url": url})
                _current_agent._log_tool_result("webfetch", str(e), False)
            return f"Error fetching {url}: {e}"


async def verify_response_quality(ctx: RunContext, response: str) -> str:
    """Verify if the agent's response is specific and contains actual information.
    
    Args:
        response: The agent's response to verify
    
    Returns:
        Quality assessment with suggestions for improvement
    """
    with tracer.start_as_current_span("verify_response_quality") as span:
        span.set_attribute("response_length", len(response))
        if format_tool_call:
            format_tool_call("verify_response_quality", {"response_length": len(response)})
        
        issues = []
        suggestions = []
        
        # Check for generic descriptions
        generic_phrases = [
            "provides headlines",
            "visit this page",
            "you can visit",
            "offers coverage",
            "check their website",
            "provides comprehensive",
            "stay informed"
        ]
        
        for phrase in generic_phrases:
            if phrase.lower() in response.lower():
                issues.append(f"Contains generic phrase: '{phrase}'")
                suggestions.append("Extract actual headlines/content instead of describing the site")
        
        # Check for specific information
        has_dates = any(char.isdigit() for char in response)  # Simple check for numbers/dates
        has_quotes = '"' in response or "'" in response
        has_specific_names = any(word[0].isupper() for word in response.split() if len(word) > 1)
        
        if not has_dates:
            issues.append("Missing specific dates or numbers")
            suggestions.append("Include specific dates, times, or numbers")
        
        if not has_quotes:
            issues.append("Missing quotes or direct content")
            suggestions.append("Include direct quotes or actual headlines")
        
        if not has_specific_names:
            issues.append("Missing specific names or entities")
            suggestions.append("Include specific names of people, companies, or places")
        
        # Check response length
        if len(response) < 200:
            issues.append("Response is too short")
            suggestions.append("Provide more detailed information")
        
        # Check if response is just a list of URLs
        url_count = response.count("http")
        if url_count > 3 and len(response.split('\n')) < url_count + 5:
            issues.append("Response is mostly URLs without content")
            suggestions.append("Fetch and summarize actual content from URLs")
        
        # Generate assessment
        if not issues:
            return "✅ Response Quality: GOOD\n\nThe response contains specific information and is not generic."
        else:
            output = "⚠️ Response Quality: NEEDS IMPROVEMENT\n\n"
            output += "Issues Found:\n"
            for issue in issues:
                output += f"  • {issue}\n"
            
            output += "\nSuggestions:\n"
            for suggestion in suggestions:
                output += f"  • {suggestion}\n"
            
            output += "\nRecommendation: Use web_search(query, fetch_content=True) to get actual content."
            
            return output


async def extract_article_content(ctx: RunContext, url: str) -> str:
    """Extract main article content from a URL. Removes navigation, ads, and extracts key information.
    
    Args:
        url: URL to extract content from
    
    Returns:
        Structured article content with headline, summary, key points, and quotes
    """
    with tracer.start_as_current_span("extract_article_content") as span:
        span.set_attribute("url", url)
        if format_tool_call:
            format_tool_call("extract_article_content", {"url": url})
        try:
            # Fetch the page content
            content = await webfetch_tool(ctx, url, max_chars=10000)
            
            # Try to extract structured content using readability if available
            try:
                from readability import Document
                import html
                doc = Document(content)
                title = doc.title()
                main_content = doc.summary()
                
                # Extract key information
                output = f"Article: {title}\n"
                output += f"URL: {url}\n"
                output += "=" * 60 + "\n\n"
                
                # Extract summary (first paragraph)
                paragraphs = main_content.split('\n')
                if paragraphs:
                    output += f"Summary:\n{paragraphs[0][:500]}...\n\n"
                
                # Extract key points (look for bullet points or numbered lists)
                output += "Key Points:\n"
                for para in paragraphs[1:10]:  # Check first 10 paragraphs
                    if para.strip() and (para.strip().startswith('•') or 
                                         para.strip().startswith('-') or
                                         para.strip().startswith('*') or
                                         any(para.strip().startswith(str(i)+'.') for i in range(1, 10))):
                        output += f"  {para.strip()}\n"
                
                # Extract quotes (look for text in quotes)
                import re
                quotes = re.findall(r'"([^"]{20,200})"', main_content)
                if quotes:
                    output += "\nNotable Quotes:\n"
                    for quote in quotes[:3]:
                        output += f'  "{quote}"\n'
                
                return output
                
            except ImportError:
                # Fallback: simple text extraction
                output = f"Article Content (basic extraction)\n"
                output += f"URL: {url}\n"
                output += "=" * 60 + "\n\n"
                
                # Extract first few paragraphs
                paragraphs = content.split('\n\n')
                output += "Content Preview:\n"
                for para in paragraphs[:5]:
                    if len(para.strip()) > 50:  # Skip very short lines
                        output += para.strip()[:300] + "...\n\n"
                
                return output
            
        except Exception as e:
            error_msg = f"Error extracting article content: {str(e)}"
            span.set_attribute("error", error_msg)
            if _current_agent:
                _current_agent._log_tool_call("extract_article_content", {"url": url})
                _current_agent._log_tool_result("extract_article_content", error_msg, False)
            return error_msg


async def web_search_tool(ctx: RunContext, query: str, max_results: int = 5, fetch_content: bool = False) -> str:
    """Search the web for a query and return structured result text. Use this for ANY question about current events, games, news, people, products, or facts you do not already know. Pass a concise query string.
    
    Args:
        query: Search query string
        max_results: Maximum number of results to return
        fetch_content: If True, fetches actual content from top 2-3 results (slower but better quality)
    """
    with tracer.start_as_current_span("web_search_tool") as span:
        span.set_attribute("query", query)
        span.set_attribute("max_results", max_results)
        span.set_attribute("fetch_content", fetch_content)
        if format_tool_call:
            format_tool_call("web_search", {"query": query, "max_results": max_results, "fetch_content": fetch_content})
        try:
            from ddgs import DDGS

            results = DDGS().text(query, max_results=max_results)
            if not results:
                return f"No web search results found for '{query}'."

            output_lines = [f"Web search results for '{query}':\n"]
            
            # If fetch_content is enabled, get actual content from top results
            if fetch_content and results:
                output_lines.append("(Fetching actual content from top results...)\n")
                for idx, r in enumerate(results[:3], 1):  # Fetch content for top 3
                    title = r.get("title", "No title")
                    href = r.get("href", "")
                    body = r.get("body", "")
                    
                    output_lines.append(f"{idx}. {title}")
                    output_lines.append(f"   URL: {href}")
                    output_lines.append(f"   Summary: {body}\n")
                    
                    # Fetch actual content
                    try:
                        content = await webfetch_tool(ctx, href, max_chars=3000)
                        # Extract key info from content
                        content_preview = content[:500] + "..." if len(content) > 500 else content
                        output_lines.append(f"   Content Preview:\n{content_preview}\n")
                    except Exception as e:
                        output_lines.append(f"   (Could not fetch content: {str(e)})\n")
                    output_lines.append("-" * 60 + "\n")
                
                # Add remaining results without content
                for idx, r in enumerate(results[3:], 4):
                    title = r.get("title", "No title")
                    href = r.get("href", "")
                    body = r.get("body", "")
                    output_lines.append(f"{idx}. {title}")
                    output_lines.append(f"   URL: {href}")
                    output_lines.append(f"   {body}\n")
            else:
                # Standard search without content fetching
                for idx, r in enumerate(results, 1):
                    title = r.get("title", "No title")
                    href = r.get("href", "")
                    body = r.get("body", "")
                    output_lines.append(f"{idx}. {title}")
                    output_lines.append(f"   URL: {href}")
                    output_lines.append(f"   {body}\n")

            text = "\n".join(output_lines)
            if _current_agent:
                _current_agent._log_tool_call(
                    "web_search", {"query": query, "max_results": max_results}
                )
                _current_agent._log_tool_result("web_search", f"Found {len(results)} results", True)
            return text

        except ImportError:
            return "Error: ddgs is not installed. Run: pip install ddgs"
        except Exception as e:
            if _current_agent:
                _current_agent._log_tool_call("web_search", {"query": query})
                _current_agent._log_tool_result("web_search", str(e), False)
            return f"Error searching for '{query}': {e}"
