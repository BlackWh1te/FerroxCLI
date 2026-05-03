"""Social Bot Daemon for Ferrox - Background scheduler for X automation.

Provides autonomous operation with warmup routine, night mode, visibility checks,
and comprehensive anti-ban protections.
"""

import asyncio
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Social config and state
from .social_config import (
    SocialConfig,
    get_rate_limits_for_account_type,
    load_social_state,
    save_social_state,
)

# Content safety
# Platform compatibility
from .utils.platform_compat import (
    LockFileDaemon,
    managed_event_loop,
)

# Tools (imported dynamically to avoid circular deps)

# Lock file for daemon control
LOCK_FILE = Path.home() / ".ferrox" / "social_daemon.lock"


class SocialBotDaemon:
    """Daemon for automated X posting with anti-ban protections."""

    def __init__(self, config: SocialConfig):
        self.config = config
        self.state = load_social_state()
        self.lock = LockFileDaemon(LOCK_FILE)
        self.running = False
        self.current_account_type = "new"
        self._stop_event = asyncio.Event()

    async def warmup_routine(self):
        """Execute warmup routine before posting to appear human."""
        print("[Social Bot] Starting warmup routine...")

        # Import tools here to avoid circular imports
        from pydantic_ai import RunContext

        from .agent.tools_social import get_trends_tool, search_tweets_tool

        mock_ctx = RunContext({})

        # 1. Search some neutral topics
        neutral_topics = ["weather", "sports", "music", "technology", "news"]
        topic = random.choice(neutral_topics)
        print(f"[Social Bot] Warmup: Searching for '{topic}'...")
        await search_tweets_tool(mock_ctx, topic, max_results=3)

        # Wait 30-60 seconds
        wait = random.randint(30, 60)
        print(f"[Social Bot] Warmup: Waiting {wait}s...")
        await asyncio.sleep(wait)

        # 2. Get trends
        print("[Social Bot] Warmup: Checking trends...")
        await get_trends_tool(mock_ctx)

        # Wait another 30-60 seconds
        wait = random.randint(30, 60)
        print(f"[Social Bot] Warmup: Waiting {wait}s...")
        await asyncio.sleep(wait)

        # 3. Like 1-2 tweets (optional, for established accounts)
        if self.current_account_type in ["established", "legacy"]:
            print("[Social Bot] Warmup: Liking a tweet...")
            # This would require fetching timeline and liking
            # Skipped for safety in new accounts
            pass

        print("[Social Bot] Warmup complete.")

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
        self.state = load_social_state()

        # Check if daemon was manually stopped
        if self.lock.read_command() == "STOP":
            return False, "Daemon received STOP command"

        # Check night mode
        if self.check_night_mode():
            return False, "In night mode hours"

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
            # 3. Generate tweet text
            # 4. Post

            # For this scaffold, we'll just log what would happen
            print("[Social Bot] Would generate and post content based on strategy:")
            print(f"  Strategy: {self.config.strategy}")

            # TODO: Integrate with LLM for content generation
            # This would call the agent with the strategy and tools

            return True

        except Exception as e:
            print(f"[Social Bot] Error in generate_and_post: {e}")
            self.state.consecutive_failures += 1
            save_social_state(self.state)
            return False

    async def run_cycle(self):
        """Run one posting cycle."""
        # Check commands
        command = self.lock.read_command()
        if command == "STOP":
            print("[Social Bot] Received STOP command")
            self.running = False
            return

        # Check health
        can_post, reason = self.check_account_health()
        if not can_post:
            print(f"[Social Bot] Skipping cycle: {reason}")
            return

        # Warmup (if enabled and enough time passed)
        if self.config.safety.warmup_enabled:
            await self.warmup_routine()

        # Generate and post
        success = await self.generate_and_post()

        if success:
            print("[Social Bot] Cycle completed successfully")
        else:
            print("[Social Bot] Cycle failed")

    async def run(self):
        """Main daemon loop."""
        self.running = True

        print("[Social Bot] Daemon starting...")

        # Write PID
        import os
        self.lock.start(os.getpid())

        # Update state
        self.state.daemon_running = True
        self.state.daemon_started_at = datetime.now()
        self.state.daemon_pid = os.getpid()
        save_social_state(self.state)

        print(f"[Social Bot] Daemon started (PID: {os.getpid()})")

        try:
            while self.running:
                await self.run_cycle()

                if not self.running:
                    break

                # Calculate next run time with jitter
                interval_hours = self.config.schedule.interval_hours
                jitter_minutes = self.config.schedule.jitter_minutes

                jitter = random.randint(-jitter_minutes, jitter_minutes)
                wait_seconds = (interval_hours * 3600) + (jitter * 60)

                next_run = datetime.now() + timedelta(seconds=wait_seconds)
                print(f"[Social Bot] Next run at {next_run.strftime('%H:%M')}")

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
            print("[Social Bot] Daemon cancelled")
        except Exception as e:
            print(f"[Social Bot] Error: {e}")
        finally:
            self.shutdown()

    def shutdown(self):
        """Clean shutdown."""
        print("[Social Bot] Daemon shutting down...")
        self.running = False
        self.lock.stop()

        self.state.daemon_running = False
        self.state.daemon_pid = None
        save_social_state(self.state)

        print("[Social Bot] Daemon stopped")


def start_daemon(config: Optional[SocialConfig] = None) -> bool:
    """Start the social bot daemon.
    
    Args:
        config: Configuration (uses default if None)
        
    Returns:
        True if started successfully
    """
    if config is None:
        config = SocialConfig()

    # Check if already running
    lock = LockFileDaemon(LOCK_FILE)
    if lock.is_running():
        print("[Social Bot] Daemon already running")
        return False

    # Check account type restrictions
    state = load_social_state()
    if state.last_login:
        # Determine account type from state
        # For now, assume new account for safety
        account_type = "new"
    else:
        print("[Social Bot] Not logged in. Please run /social login first")
        return False

    if account_type == "new":
        print("[Social Bot] CRITICAL: New accounts cannot use background daemon")
        print("  Use manual /post command only for first 14 days")
        return False

    # Use managed event loop for platform compatibility
    with managed_event_loop() as loop:
        daemon = SocialBotDaemon(config)
        daemon.current_account_type = account_type

        try:
            loop.run_until_complete(daemon.run())
            return True
        except KeyboardInterrupt:
            print("\n[Social Bot] Interrupted by user")
            daemon.shutdown()
            return True


def stop_daemon() -> bool:
    """Stop the running daemon.
    
    Returns:
        True if stop signal sent
    """
    lock = LockFileDaemon(LOCK_FILE)

    if not lock.is_running():
        print("[Social Bot] Daemon not running")
        return False

    lock.send_command("STOP")
    print("[Social Bot] Stop signal sent to daemon")
    return True


def get_daemon_status() -> dict:
    """Get daemon status.
    
    Returns:
        Dictionary with status info
    """
    lock = LockFileDaemon(LOCK_FILE)
    state = load_social_state()

    return {
        "running": lock.is_running(),
        "pid": state.daemon_pid,
        "started_at": state.daemon_started_at,
        "posts_today": state.posts_today,
        "session_valid": state.session_valid,
        "consecutive_failures": state.consecutive_failures,
    }


async def run_daemon_once(config: Optional[SocialConfig] = None) -> bool:
    """Run one cycle of the daemon (for manual execution).
    
    Args:
        config: Configuration
        
    Returns:
        True if successful
    """
    if config is None:
        config = SocialConfig()

    daemon = SocialBotDaemon(config)
    await daemon.run_cycle()
    return True
