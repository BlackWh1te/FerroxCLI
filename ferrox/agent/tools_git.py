"""Git operations tools for Ferrox agent.

Provides comprehensive git operations with permission checks and safety features.
"""

import subprocess
from typing import Optional

# Import tracer
from opentelemetry import trace
from pydantic_ai import RunContext

from ..modes import Mode
from ..permissions import PermissionAction, PermissionEngine

tracer = trace.get_tracer(__name__)

# Import _current_agent
try:
    from ferrox.agent.orchestrator import _current_agent
except ImportError:
    _current_agent = None

# Import output formatters
try:
    from ..ui.output import format_tool_call
except ImportError:
    format_tool_call = None

# Shared permission engine
permissions = PermissionEngine()


async def git_status_tool(ctx: RunContext, path: str = ".") -> str:
    """Get git status of the repository at the given path."""
    with tracer.start_as_current_span("git_status_tool") as span:
        span.set_attribute("path", path)

        try:
            (
                ctx.deps.mode if hasattr(ctx, "deps") and hasattr(ctx.deps, "mode") else Mode.NORMAL
            )

            # Git status is read-only, always allowed
            if format_tool_call:
                format_tool_call("git_status", {"path": path})

            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=path,
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                error_msg = f"Git status failed: {result.stderr}"
                span.set_attribute("error", error_msg)
                if _current_agent:
                    _current_agent._log_tool_call("git_status", {"path": path})
                    _current_agent._log_tool_result("git_status", error_msg, False)
                return error_msg

            # Parse porcelain output
            lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
            if not lines or lines == [""]:
                output = "Working directory clean (no changes)"
            else:
                output = f"Git status ({len(lines)} changed files):\n"
                for line in lines:
                    if line:
                        status = line[:2]
                        filepath = line[3:]
                        output += f"  {status} {filepath}\n"

            if _current_agent:
                _current_agent._log_tool_call("git_status", {"path": path})
                _current_agent._log_tool_result("git_status", f"Found {len(lines)} changed files", True)

            return output

        except subprocess.TimeoutExpired:
            error_msg = "Git status timed out"
            span.set_attribute("error", error_msg)
            if _current_agent:
                _current_agent._log_tool_call("git_status", {"path": path})
                _current_agent._log_tool_result("git_status", error_msg, False)
            return error_msg
        except FileNotFoundError:
            error_msg = "Git not found in PATH"
            span.set_attribute("error", error_msg)
            if _current_agent:
                _current_agent._log_tool_call("git_status", {"path": path})
                _current_agent._log_tool_result("git_status", error_msg, False)
            return error_msg
        except Exception as e:
            error_msg = f"Error running git status: {str(e)}"
            span.set_attribute("error", error_msg)
            if _current_agent:
                _current_agent._log_tool_call("git_status", {"path": path})
                _current_agent._log_tool_result("git_status", error_msg, False)
            return error_msg


async def git_diff_tool(ctx: RunContext, path: str = ".", cached: bool = False) -> str:
    """Get git diff of changes. If cached=True, shows staged changes."""
    with tracer.start_as_current_span("git_diff_tool") as span:
        span.set_attribute("path", path)
        span.set_attribute("cached", cached)

        try:
            (
                ctx.deps.mode if hasattr(ctx, "deps") and hasattr(ctx.deps, "mode") else Mode.NORMAL
            )

            # Git diff is read-only, always allowed
            if format_tool_call:
                format_tool_call("git_diff", {"path": path, "cached": cached})

            cmd = ["git", "diff"]
            if cached:
                cmd.append("--cached")
            cmd.append("--")

            result = subprocess.run(
                cmd + [path],
                cwd=".",
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                error_msg = f"Git diff failed: {result.stderr}"
                span.set_attribute("error", error_msg)
                if _current_agent:
                    _current_agent._log_tool_call("git_diff", {"path": path})
                    _current_agent._log_tool_result("git_diff", error_msg, False)
                return error_msg

            output = result.stdout
            if not output.strip():
                output = "No changes to show"

            if _current_agent:
                _current_agent._log_tool_call("git_diff", {"path": path, "cached": cached})
                _current_agent._log_tool_result("git_diff", f"Generated diff ({len(output)} chars)", True)

            return output

        except subprocess.TimeoutExpired:
            error_msg = "Git diff timed out"
            span.set_attribute("error", error_msg)
            if _current_agent:
                _current_agent._log_tool_call("git_diff", {"path": path})
                _current_agent._log_tool_result("git_diff", error_msg, False)
            return error_msg
        except Exception as e:
            error_msg = f"Error running git diff: {str(e)}"
            span.set_attribute("error", error_msg)
            if _current_agent:
                _current_agent._log_tool_call("git_diff", {"path": path})
                _current_agent._log_tool_result("git_diff", error_msg, False)
            return error_msg


async def git_commit_tool(ctx: RunContext, message: str, path: str = ".", amend: bool = False) -> str:
    """Create a git commit with the given message. Requires permission."""
    with tracer.start_as_current_span("git_commit_tool") as span:
        span.set_attribute("message", message)
        span.set_attribute("path", path)
        span.set_attribute("amend", amend)

        try:
            mode = (
                ctx.deps.mode if hasattr(ctx, "deps") and hasattr(ctx.deps, "mode") else Mode.NORMAL
            )

            # Git commit is a write operation, check permissions
            if not permissions.check_access(path, PermissionAction.WRITE, mode):
                error_msg = f"Permission denied: git commit requires write access to {path}"
                span.set_attribute("access", "denied")
                if _current_agent:
                    _current_agent._log_tool_call("git_commit", {"message": message})
                    _current_agent._log_tool_result("git_commit", error_msg, False)
                return error_msg

            if format_tool_call:
                format_tool_call("git_commit", {"message": message, "amend": amend})

            cmd = ["git", "commit"]
            if amend:
                cmd.append("--amend")
            cmd.extend(["-m", message])

            result = subprocess.run(
                cmd,
                cwd=path,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                error_msg = f"Git commit failed: {result.stderr}"
                span.set_attribute("error", error_msg)
                if _current_agent:
                    _current_agent._log_tool_call("git_commit", {"message": message})
                    _current_agent._log_tool_result("git_commit", error_msg, False)
                return error_msg

            output = result.stdout if result.stdout else result.stderr
            if _current_agent:
                _current_agent._log_tool_call("git_commit", {"message": message})
                _current_agent._log_tool_result("git_commit", "Commit created successfully", True)

            return output

        except subprocess.TimeoutExpired:
            error_msg = "Git commit timed out"
            span.set_attribute("error", error_msg)
            if _current_agent:
                _current_agent._log_tool_call("git_commit", {"message": message})
                _current_agent._log_tool_result("git_commit", error_msg, False)
            return error_msg
        except Exception as e:
            error_msg = f"Error running git commit: {str(e)}"
            span.set_attribute("error", error_msg)
            if _current_agent:
                _current_agent._log_tool_call("git_commit", {"message": message})
                _current_agent._log_tool_result("git_commit", error_msg, False)
            return error_msg


async def git_branch_tool(ctx: RunContext, show_current: bool = True) -> str:
    """List all git branches. If show_current=True, highlights current branch."""
    with tracer.start_as_current_span("git_branch_tool") as span:
        span.set_attribute("show_current", show_current)

        try:
            (
                ctx.deps.mode if hasattr(ctx, "deps") and hasattr(ctx.deps, "mode") else Mode.NORMAL
            )

            # Git branch is read-only, always allowed
            if format_tool_call:
                format_tool_call("git_branch", {"show_current": show_current})

            result = subprocess.run(
                ["git", "branch", "-a"],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                error_msg = f"Git branch failed: {result.stderr}"
                span.set_attribute("error", error_msg)
                if _current_agent:
                    _current_agent._log_tool_call("git_branch", {})
                    _current_agent._log_tool_result("git_branch", error_msg, False)
                return error_msg

            lines = result.stdout.strip().split("\n")
            output = "Git branches:\n"
            for line in lines:
                if line.strip():
                    if line.startswith("*"):
                        output += f"  * {line[2:].strip()} (current)\n"
                    else:
                        output += f"    {line.strip()}\n"

            if _current_agent:
                _current_agent._log_tool_call("git_branch", {})
                _current_agent._log_tool_result("git_branch", f"Found {len(lines)} branches", True)

            return output

        except subprocess.TimeoutExpired:
            error_msg = "Git branch timed out"
            span.set_attribute("error", error_msg)
            if _current_agent:
                _current_agent._log_tool_call("git_branch", {})
                _current_agent._log_tool_result("git_branch", error_msg, False)
            return error_msg
        except Exception as e:
            error_msg = f"Error running git branch: {str(e)}"
            span.set_attribute("error", error_msg)
            if _current_agent:
                _current_agent._log_tool_call("git_branch", {})
                _current_agent._log_tool_result("git_branch", error_msg, False)
            return error_msg


async def git_checkout_tool(ctx: RunContext, branch: str, create: bool = False) -> str:
    """Checkout a git branch. If create=True, creates and checks out new branch."""
    with tracer.start_as_current_span("git_checkout_tool") as span:
        span.set_attribute("branch", branch)
        span.set_attribute("create", create)

        try:
            mode = (
                ctx.deps.mode if hasattr(ctx, "deps") and hasattr(ctx.deps, "mode") else Mode.NORMAL
            )

            # Git checkout is a write operation, check permissions
            if not permissions.check_access(".", PermissionAction.WRITE, mode):
                error_msg = "Permission denied: git checkout requires write access"
                span.set_attribute("access", "denied")
                if _current_agent:
                    _current_agent._log_tool_call("git_checkout", {"branch": branch})
                    _current_agent._log_tool_result("git_checkout", error_msg, False)
                return error_msg

            if format_tool_call:
                format_tool_call("git_checkout", {"branch": branch, "create": create})

            cmd = ["git", "checkout"]
            if create:
                cmd.append("-b")
            cmd.append(branch)

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                error_msg = f"Git checkout failed: {result.stderr}"
                span.set_attribute("error", error_msg)
                if _current_agent:
                    _current_agent._log_tool_call("git_checkout", {"branch": branch})
                    _current_agent._log_tool_result("git_checkout", error_msg, False)
                return error_msg

            output = result.stdout if result.stdout else result.stderr
            if _current_agent:
                _current_agent._log_tool_call("git_checkout", {"branch": branch})
                _current_agent._log_tool_result("git_checkout", f"Checked out {branch}", True)

            return output

        except subprocess.TimeoutExpired:
            error_msg = "Git checkout timed out"
            span.set_attribute("error", error_msg)
            if _current_agent:
                _current_agent._log_tool_call("git_checkout", {"branch": branch})
                _current_agent._log_tool_result("git_checkout", error_msg, False)
            return error_msg
        except Exception as e:
            error_msg = f"Error running git checkout: {str(e)}"
            span.set_attribute("error", error_msg)
            if _current_agent:
                _current_agent._log_tool_call("git_checkout", {"branch": branch})
                _current_agent._log_tool_result("git_checkout", error_msg, False)
            return error_msg


async def git_log_tool(ctx: RunContext, max_count: int = 10, path: str = ".") -> str:
    """Get git log history."""
    with tracer.start_as_current_span("git_log_tool") as span:
        span.set_attribute("max_count", max_count)
        span.set_attribute("path", path)

        try:
            (
                ctx.deps.mode if hasattr(ctx, "deps") and hasattr(ctx.deps, "mode") else Mode.NORMAL
            )

            # Git log is read-only, always allowed
            if format_tool_call:
                format_tool_call("git_log", {"max_count": max_count, "path": path})

            result = subprocess.run(
                ["git", "log", f"-{max_count}", "--oneline", "--decorate"],
                cwd=path,
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                error_msg = f"Git log failed: {result.stderr}"
                span.set_attribute("error", error_msg)
                if _current_agent:
                    _current_agent._log_tool_call("git_log", {"max_count": max_count})
                    _current_agent._log_tool_result("git_log", error_msg, False)
                return error_msg

            output = result.stdout if result.stdout else "No commits found"
            if _current_agent:
                _current_agent._log_tool_call("git_log", {"max_count": max_count})
                _current_agent._log_tool_result("git_log", f"Retrieved {max_count} commits", True)

            return output

        except subprocess.TimeoutExpired:
            error_msg = "Git log timed out"
            span.set_attribute("error", error_msg)
            if _current_agent:
                _current_agent._log_tool_call("git_log", {"max_count": max_count})
                _current_agent._log_tool_result("git_log", error_msg, False)
            return error_msg
        except Exception as e:
            error_msg = f"Error running git log: {str(e)}"
            span.set_attribute("error", error_msg)
            if _current_agent:
                _current_agent._log_tool_call("git_log", {"max_count": max_count})
                _current_agent._log_tool_result("git_log", error_msg, False)
            return error_msg


async def git_stash_tool(ctx: RunContext, action: str = "save", message: str = "") -> str:
    """Git stash operations: save, list, pop, apply, drop."""
    with tracer.start_as_current_span("git_stash_tool") as span:
        span.set_attribute("action", action)
        span.set_attribute("message", message)

        try:
            mode = (
                ctx.deps.mode if hasattr(ctx, "deps") and hasattr(ctx.deps, "mode") else Mode.NORMAL
            )

            # Git stash is a write operation, check permissions (except for list)
            if action != "list" and not permissions.check_access(".", PermissionAction.WRITE, mode):
                error_msg = f"Permission denied: git stash {action} requires write access"
                span.set_attribute("access", "denied")
                if _current_agent:
                    _current_agent._log_tool_call("git_stash", {"action": action})
                    _current_agent._log_tool_result("git_stash", error_msg, False)
                return error_msg

            if format_tool_call:
                format_tool_call("git_stash", {"action": action, "message": message})

            cmd = ["git", "stash"]
            if action == "save":
                cmd.append("save")
                if message:
                    cmd.extend(["-m", message])
            elif action == "list":
                cmd.append("list")
            elif action == "pop":
                cmd.append("pop")
            elif action == "apply":
                cmd.append("apply")
            elif action == "drop":
                cmd.append("drop")
            else:
                return f"Unknown stash action: {action}"

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                error_msg = f"Git stash {action} failed: {result.stderr}"
                span.set_attribute("error", error_msg)
                if _current_agent:
                    _current_agent._log_tool_call("git_stash", {"action": action})
                    _current_agent._log_tool_result("git_stash", error_msg, False)
                return error_msg

            output = result.stdout if result.stdout else result.stderr
            if _current_agent:
                _current_agent._log_tool_call("git_stash", {"action": action})
                _current_agent._log_tool_result("git_stash", f"Stash {action} completed", True)

            return output

        except subprocess.TimeoutExpired:
            error_msg = "Git stash timed out"
            span.set_attribute("error", error_msg)
            if _current_agent:
                _current_agent._log_tool_call("git_stash", {"action": action})
                _current_agent._log_tool_result("git_stash", error_msg, False)
            return error_msg
        except Exception as e:
            error_msg = f"Error running git stash: {str(e)}"
            span.set_attribute("error", error_msg)
            if _current_agent:
                _current_agent._log_tool_call("git_stash", {"action": action})
                _current_agent._log_tool_result("git_stash", error_msg, False)
            return error_msg


async def git_blame_tool(ctx: RunContext, path: str, line: Optional[int] = None) -> str:
    """Get git blame information for a file."""
    with tracer.start_as_current_span("git_blame_tool") as span:
        span.set_attribute("path", path)
        span.set_attribute("line", line)

        try:
            (
                ctx.deps.mode if hasattr(ctx, "deps") and hasattr(ctx.deps, "mode") else Mode.NORMAL
            )

            # Git blame is read-only, always allowed
            if format_tool_call:
                format_tool_call("git_blame", {"path": path, "line": line})

            cmd = ["git", "blame"]
            if line is not None:
                cmd.extend(["-L", f"{line},{line}"])
            cmd.append(path)

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                error_msg = f"Git blame failed: {result.stderr}"
                span.set_attribute("error", error_msg)
                if _current_agent:
                    _current_agent._log_tool_call("git_blame", {"path": path})
                    _current_agent._log_tool_result("git_blame", error_msg, False)
                return error_msg

            output = result.stdout
            if _current_agent:
                _current_agent._log_tool_call("git_blame", {"path": path})
                _current_agent._log_tool_result("git_blame", f"Generated blame ({len(output)} chars)", True)

            return output

        except subprocess.TimeoutExpired:
            error_msg = "Git blame timed out"
            span.set_attribute("error", error_msg)
            if _current_agent:
                _current_agent._log_tool_call("git_blame", {"path": path})
                _current_agent._log_tool_result("git_blame", error_msg, False)
            return error_msg
        except Exception as e:
            error_msg = f"Error running git blame: {str(e)}"
            span.set_attribute("error", error_msg)
            if _current_agent:
                _current_agent._log_tool_call("git_blame", {"path": path})
                _current_agent._log_tool_result("git_blame", error_msg, False)
            return error_msg
