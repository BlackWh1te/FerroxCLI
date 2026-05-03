"""Platform compatibility utilities for Ferrox.

Provides Windows/MINGW-specific workarounds for daemon control,
path handling, and asyncio event loop management.
"""

import os
import sys
import asyncio
import subprocess
from pathlib import Path
from typing import Optional, Tuple
from contextlib import contextmanager


def is_windows() -> bool:
    """Check if running on Windows."""
    return os.name == "nt" or sys.platform.startswith("win")


def is_mingw() -> bool:
    """Check if running in MINGW environment."""
    return "MINGW" in os.environ.get("MSYSTEM", "") or "MINGW" in sys.platform


def safe_path(path: str) -> str:
    """Escape path for use in shell commands on Windows with spaces.
    
    Args:
        path: File path that may contain spaces
        
    Returns:
        Escaped path string
    """
    if is_windows():
        # Wrap in quotes if contains spaces
        if " " in path:
            return f'"{path}"'
    return path


def safe_filename(filename: str) -> str:
    """Make a filename safe for cross-platform use.
    
    Args:
        filename: Original filename
        
    Returns:
        Safe filename without problematic characters
    """
    # Remove characters that are problematic on Windows
    unsafe_chars = '<>:"/\\|?*'
    for char in unsafe_chars:
        filename = filename.replace(char, "_")
    
    # Limit length
    if len(filename) > 200:
        name, ext = os.path.splitext(filename)
        filename = name[:200 - len(ext)] + ext
    
    return filename


class LockFileDaemon:
    """Cross-platform daemon control using lockfiles (works on Windows/MINGW).
    
    Unlike Unix signals which don't work properly on Windows/MINGW,
    this uses lockfiles for IPC.
    """
    
    def __init__(self, lockfile_path: Path):
        self.lockfile_path = Path(lockfile_path)
        self.pidfile_path = self.lockfile_path.with_suffix(".pid")
        self.command_path = self.lockfile_path.with_suffix(".cmd")
    
    def is_running(self) -> bool:
        """Check if daemon is currently running."""
        if not self.pidfile_path.exists():
            return False
        
        try:
            with open(self.pidfile_path, "r") as f:
                pid = int(f.read().strip())
            
            # Check if process exists
            if is_windows():
                # Windows: use tasklist
                result = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                    capture_output=True,
                    text=True,
                )
                return str(pid) in result.stdout
            else:
                # Unix: check if /proc/PID exists or use kill -0
                try:
                    os.kill(pid, 0)
                    return True
                except ProcessLookupError:
                    return False
        except (ValueError, FileNotFoundError, PermissionError):
            # Stale lockfile
            self._cleanup()
            return False
    
    def start(self, pid: int) -> bool:
        """Mark daemon as started."""
        try:
            self.lockfile_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.pidfile_path, "w") as f:
                f.write(str(pid))
            return True
        except Exception as e:
            print(f"Failed to write pidfile: {e}")
            return False
    
    def stop(self) -> bool:
        """Mark daemon as stopped and cleanup."""
        self._cleanup()
        return True
    
    def send_command(self, command: str) -> bool:
        """Send a command to the running daemon."""
        if not self.is_running():
            return False
        
        try:
            with open(self.command_path, "w") as f:
                f.write(command)
            return True
        except Exception as e:
            print(f"Failed to send command: {e}")
            return False
    
    def read_command(self) -> Optional[str]:
        """Read and clear any pending command."""
        if not self.command_path.exists():
            return None
        
        try:
            with open(self.command_path, "r") as f:
                command = f.read().strip()
            self.command_path.unlink()
            return command if command else None
        except Exception:
            return None
    
    def _cleanup(self):
        """Remove all lock files."""
        for path in [self.lockfile_path, self.pidfile_path, self.command_path]:
            try:
                if path.exists():
                    path.unlink()
            except Exception:
                pass


def get_asyncio_event_loop_policy():
    """Get the appropriate event loop policy for the platform.
    
    On Windows, ProactorEventLoop is needed for subprocess support.
    """
    if is_windows():
        return asyncio.WindowsProactorEventLoopPolicy()
    return asyncio.DefaultEventLoopPolicy()


@contextmanager
def managed_event_loop():
    """Context manager for properly configured event loop.
    
    Usage:
        with managed_event_loop() as loop:
            # Use loop
    """
    if is_windows():
        # Use ProactorEventLoop on Windows for subprocess support
        loop = asyncio.ProactorEventLoop()
        asyncio.set_event_loop(loop)
    else:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    try:
        yield loop
    finally:
        try:
            # Cancel all pending tasks
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()
        except Exception:
            pass


def run_subprocess_windows(cmd: list, **kwargs) -> subprocess.Popen:
    """Run subprocess with Windows-specific settings.
    
    Args:
        cmd: Command list
        **kwargs: Additional subprocess arguments
        
    Returns:
        Popen object
    """
    if is_windows():
        # Windows-specific: don't create console window
        kwargs.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
    
    return subprocess.Popen(cmd, **kwargs)


def get_config_dir() -> Path:
    """Get the appropriate config directory for the platform.
    
    Returns:
        Path to Ferrox config directory
    """
    if is_windows():
        # Use LOCALAPPDATA on Windows
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / "Ferrox"
    
    # Default to ~/.ferrox
    return Path.home() / ".ferrox"


def sanitize_unicode_for_mingw(text: str) -> str:
    """Sanitize Unicode text for MINGW terminal compatibility.
    
    MINGW terminals sometimes mangle certain Unicode characters.
    
    Args:
        text: Text that may contain problematic Unicode
        
    Returns:
        Sanitized text with ASCII-safe alternatives
    """
    if not is_mingw():
        return text
    
    # Replace emojis with text equivalents
    replacements = {
        "✅": "[OK]",
        "❌": "[X]",
        "⚠️": "[!]",
        "🔴": "[STOP]",
        "🟢": "[GO]",
        "🟡": "[WAIT]",
        "📊": "[STATS]",
        "💭": "[THOUGHT]",
        "🤖": "[BOT]",
        "📝": "[NOTE]",
        "🗺️": "[MAP]",
        "🌐": "[WEB]",
        "📦": "[PKG]",
        "⚡": "[FAST]",
        "●": "*",
        "◎": "o",
        "✎": "[EDIT]",
    }
    
    for emoji, replacement in replacements.items():
        text = text.replace(emoji, replacement)
    
    return text
