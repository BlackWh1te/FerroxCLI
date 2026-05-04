"""Reddit Bot Daemon for Ferrox - Background scheduler for Reddit automation.

Provides autonomous operation with warmup routine, night mode, visibility checks,
and comprehensive anti-ban protections.
"""

import asyncio
import contextlib
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Reddit config and state
from .reddit_config import (
    RedditConfig,
    get_rate_limits_for_account_type,
    load_reddit_state,
    save_reddit_state,
)

# Content safety
# Platform compatibility
from .utils.platform_compat import (
    LockFileDaemon,
    managed_event_loop,
)

# Tools (imported dynamically to avoid circular deps)

# Lock file for daemon control
LOCK_FILE = Path.home() / ".ferrox" / "reddit_daemon.lock"


def check_ollama_status() -> bool:
    """Check if Ollama is reachable (lightweight TCP probe)."""
    import socket
    try:
        with socket.create_connection(("localhost", 11434), timeout=2):
            return True
    except Exception:
        return False


class RedditBotDaemon:
    """Daemon for automated Reddit posting with anti-ban protections."""

    def __init__(self, config: RedditConfig):
        self.config = config
        self.state = load_reddit_state()
        self.lock = LockFileDaemon(LOCK_FILE)
        self.running = False
        self.current_account_type = "new"
        self._stop_event = asyncio.Event()

    async def warmup_routine(self):
        """Execute warmup routine before posting to appear human."""
        print("[Reddit Bot] Starting warmup routine...")

        # Import tools here to avoid circular imports
        from pydantic_ai import RunContext

        from .agent.tools_reddit import get_trending_subreddits_tool, search_subreddit_tool

        mock_ctx = RunContext({})

        # 1. Search/browse a neutral subreddit
        neutral_subs = ["AskReddit", "news", "technology", "space", "science"]
        sub = random.choice(neutral_subs)  # nosec: B311 — jitter delay, not cryptographic
        print(f"[Reddit Bot] Warmup: Browsing r/{sub}...")
        with contextlib.suppress(Exception):
            await search_subreddit_tool(mock_ctx, subreddit=sub, query="", max_results=3)

        # Wait 30-60 seconds
        wait = random.randint(30, 60)  # nosec: B311 — jitter delay, not cryptographic
        print(f"[Reddit Bot] Warmup: Waiting {wait}s...")
        await asyncio.sleep(wait)

        # 2. Check trending subreddits
        print("[Reddit Bot] Warmup: Checking trending subreddits...")
        with contextlib.suppress(Exception):
            await get_trending_subreddits_tool(mock_ctx)

        # Wait another 30-60 seconds
        wait = random.randint(30, 60)  # nosec: B311 — jitter delay, not cryptographic
        print(f"[Reddit Bot] Warmup: Waiting {wait}s...")
        await asyncio.sleep(wait)

        # 3. Upvote a random post (established accounts only)
        if self.current_account_type in ["established", "legacy"]:
            print("[Reddit Bot] Warmup: Upvoting a post...")
            # Upvote action omitted for safety in new accounts
            pass

        print("[Reddit Bot] Warmup complete.")

    def check_night_mode(self) -> bool:
        """Check if currently in night mode hours.

        Returns:
            True if in night mode (should not post)
        """
        if not self.config.night_mode.enabled:
            return False

        now = datetime.now()
        current_hour = now.hour

        start = self.config.night_mode.start_hour
        end = self.config.night_mode.end_hour

        if start < end:
            # Same day range (e.g., 01:00-07:00)
            return start <= current_hour < end
        else:
            # Crosses midnight (e.g., 22:00-06:00)
            return current_hour >= start or current_hour < end

    def check_account_health(self) -> tuple[bool, str]:
        """Check if account is healthy enough to post.

        Returns:
            Tuple of (can_post, reason_if_not)
        """
        self.state = load_reddit_state()

        # Check if daemon was manually stopped
        if self.lock.read_command() == "STOP":
            return False, "Daemon received STOP command"

        # Check night mode
        if self.check_night_mode():
            return False, "In night mode hours"

        # Check Ollama status
        if not check_ollama_status():
            return False, "Ollama is unreachable - skipping cycle"

        # Get limits
        limits = get_rate_limits_for_account_type(self.current_account_type)

        # Check daily limits
        if self.state.posts_today >= limits.max_posts_per_day:
            return False, f"Daily post limit reached ({limits.max_posts_per_day})"

        # Check consecutive failures
        if self.state.consecutive_failures >= self.config.safety.auto_pause_on_failures:
            return False, f"Too many consecutive failures ({self.state.consecutive_failures})"

        # Check if session is valid
        if not self.state.session_valid:
            return False, "Session not valid - need to login"

        return True, ""

    async def generate_and_post(self) -> bool:
        """Generate content and post it.

        Returns:
            True if successful
        """
        try:

            # In a real implementation, this would use the LLM to:
            # 1. Fetch news from RSS/web
            # 2. Analyze and synthesize
            # 3. Generate post title and body
            # 4. Post to configured subreddit

            # For this scaffold, we'll just log what would happen
            print("[Reddit Bot] Would generate and post content based on strategy:")
            print(f"  Strategy: {self.config.strategy}")
            print(f"  Target subreddits: {self.config.content.subreddits}")

            # TODO: Integrate with LLM for content generation
            # This would call the agent with the strategy and tools

            return True

        except Exception as e:
            print(f"[Reddit Bot] Error in generate_and_post: {e}")
            self.state.consecutive_failures += 1
            save_reddit_state(self.state)
            return False

    async def run_cycle(self):
        """Run one posting cycle."""
        # Check commands
        command = self.lock.read_command()
        if command == "STOP":
            print("[Reddit Bot] Received STOP command")
            self.running = False
            return

        # Check health
        can_post, reason = self.check_account_health()
        if not can_post:
            print(f"[Reddit Bot] Skipping cycle: {reason}")
            return

        # Warmup (if enabled and enough time passed)
        if self.config.safety.warmup_enabled:
            await self.warmup_routine()

        # Generate and post
        success = await self.generate_and_post()

        if success:
            print("[Reddit Bot] Cycle completed successfully")
        else:
            print("[Reddit Bot] Cycle failed")

    async def run(self):
        """Main daemon loop."""
        self.running = True

        print("[Reddit Bot] Daemon starting...")

        # Write PID
        import os
        self.lock.start(os.getpid())

        # Update state
        self.state.daemon_running = True
        self.state.daemon_started_at = datetime.now()
        self.state.daemon_pid = os.getpid()
        save_reddit_state(self.state)

        print(f"[Reddit Bot] Daemon started (PID: {os.getpid()})")

        try:
            while self.running:
                await self.run_cycle()

                if not self.running:
                    break

                # Calculate next run time with jitter
                interval_hours = self.config.schedule.interval_hours
                jitter_minutes = self.config.schedule.jitter_minutes

                jitter = random.randint(-jitter_minutes, jitter_minutes)  # nosec: B311 — jitter delay, not cryptographic
                wait_seconds = (interval_hours * 3600) + (jitter * 60)

                next_run = datetime.now() + timedelta(seconds=wait_seconds)
                print(f"[Reddit Bot] Next run at {next_run.strftime('%H:%M')}")

                # Wait, but check for commands periodically
                for _ in range(wait_seconds // 10):
                    if not self.running:
                        break
                    await asyncio.sleep(10)

                    # Check for stop command
                    if self.lock.read_command() == "STOP":
                        self.running = False
                        break

        except asyncio.CancelledError:
            print("[Reddit Bot] Daemon cancelled")
        except Exception as e:
            print(f"[Reddit Bot] Error: {e}")
        finally:
            self.shutdown()

    def shutdown(self):
        """Clean shutdown."""
        print("[Reddit Bot] Daemon shutting down...")
        self.running = False
        self.lock.stop()

        self.state.daemon_running = False
        self.state.daemon_pid = None
        save_reddit_state(self.state)

        print("[Reddit Bot] Daemon stopped")


def start_daemon(config: Optional[RedditConfig] = None) -> bool:
    """Start the Reddit bot daemon.

    Args:
        config: Configuration (uses default if None)

    Returns:
        True if started successfully
    """
    if config is None:
        config = RedditConfig()

    # Check if already running
    lock = LockFileDaemon(LOCK_FILE)
    if lock.is_running():
        print("[Reddit Bot] Daemon already running")
        return False

    # Check account type restrictions
    state = load_reddit_state()
    if state.last_login:
        # Determine account type from state
        # For now, assume new account for safety
        account_type = "new"
    else:
        print("[Reddit Bot] Not logged in. Please run /reddit login first")
        return False

    if account_type == "new":
        print("[Reddit Bot] CRITICAL: New accounts cannot use background daemon")
        print("  Use manual /post command only for first 14 days")
        return False

    # Use managed event loop for platform compatibility
    with managed_event_loop() as loop:
        daemon = RedditBotDaemon(config)
        daemon.current_account_type = account_type

        try:
            loop.run_until_complete(daemon.run())
            return True
        except KeyboardInterrupt:
            print("\n[Reddit Bot] Interrupted by user")
            daemon.shutdown()
            return True


def stop_daemon() -> bool:
    """Stop the running daemon.

    Returns:
        True if stop signal sent
    """
    lock = LockFileDaemon(LOCK_FILE)

    if not lock.is_running():
        print("[Reddit Bot] Daemon not running")
        return False

    lock.send_command("STOP")
    print("[Reddit Bot] Stop signal sent to daemon")
    return True


def get_daemon_status() -> dict:
    """Get daemon status.

    Returns:
        Dictionary with status info
    """
    lock = LockFileDaemon(LOCK_FILE)
    state = load_reddit_state()

    return {
        "running": lock.is_running(),
        "pid": state.daemon_pid,
        "started_at": state.daemon_started_at,
        "posts_today": state.posts_today,
        "comments_today": state.comments_today,
        "session_valid": state.session_valid,
        "consecutive_failures": state.consecutive_failures,
    }


async def run_daemon_once(config: Optional[RedditConfig] = None) -> bool:
    """Run one cycle of the daemon (for manual execution).

    Args:
        config: Configuration

    Returns:
        True if successful
    """
    if config is None:
        config = RedditConfig()

    daemon = RedditBotDaemon(config)
    await daemon.run_cycle()
    return True
