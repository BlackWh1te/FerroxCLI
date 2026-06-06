"""Reddit configuration for Ferrox Reddit Bot.

Provides Pydantic models for Reddit credentials, schedule, rate limits, and bot settings.
"""

from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class RedditCredentials(BaseModel):
    """Reddit credentials for PRAW (API) or browser authentication."""

    username: str = Field(default="", description="Reddit username")
    password: str = Field(default="", description="Reddit password (one-time use for login)")
    client_id: str = Field(default="", description="Reddit API app client ID")
    client_secret: str = Field(default="", description="Reddit API app client secret")
    user_agent: str = Field(
        default="FerroxBot/1.0 by /u/ (github.com/ferrox)", description="PRAW user_agent string"
    )

    # Cookie storage (used after first browser login)
    cookie_file: str = Field(
        default_factory=lambda: str(Path.home() / ".ferrox" / "reddit_cookies.json"),
        description="Path to cookie file for session persistence",
    )


class RateLimits(BaseModel):
    """Rate limit configuration based on account type."""

    max_posts_per_day: int = Field(default=5, ge=1, le=100)
    max_posts_per_hour: int = Field(default=1, ge=1, le=10)
    max_comments_per_day: int = Field(default=20, ge=1, le=500)
    max_comments_per_hour: int = Field(default=3, ge=1, le=50)
    max_upvotes_per_day: int = Field(default=50, ge=1, le=1000)
    max_searches_per_hour: int = Field(default=30, ge=1, le=100)


class NightMode(BaseModel):
    """Night mode configuration - no activity during these hours."""

    enabled: bool = Field(default=True)
    start_hour: int = Field(default=1, ge=0, le=23)  # 01:00
    end_hour: int = Field(default=7, ge=0, le=23)  # 07:00

    @field_validator("end_hour")
    @classmethod
    def validate_hours(cls, v: int, info) -> int:
        """Ensure end hour is after start hour."""
        if (
            hasattr(info, "data")
            and info.data.get("start_hour") is not None
            and v <= info.data.get("start_hour")
        ):
            # If end is before start, assume next day (valid for night mode)
            pass
        return v


class PostingSchedule(BaseModel):
    """Schedule for automated posting."""

    enabled: bool = Field(default=False)
    interval_hours: int = Field(default=3, ge=1, le=24, description="Hours between posts")
    jitter_minutes: int = Field(default=30, ge=0, le=120, description="Random +/- minutes")
    timezone: str = Field(default="local", description="Timezone for scheduling")


class ContentPreferences(BaseModel):
    """Content generation preferences."""

    subreddits: list[str] = Field(default_factory=list, description="Target subreddit names")
    tone: Literal["professional", "casual", "witty", "neutral"] = Field(default="casual")
    max_links_per_post: int = Field(default=1, ge=0, le=5)
    include_media: bool = Field(default=False)
    auto_comment_on_own_posts: bool = Field(default=True)

    # Safety settings
    draft_mode: bool = Field(default=True, description="Require approval before posting")
    auto_moderation: bool = Field(default=True, description="Run moderation check")


class SafetySettings(BaseModel):
    """Safety and anti-ban settings."""

    warmup_enabled: bool = Field(default=True)
    visibility_check_enabled: bool = Field(default=True)
    dedup_enabled: bool = Field(default=True)
    dedup_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    dedup_window_hours: int = Field(default=72, ge=1, le=720)

    # Auto-pause triggers
    auto_pause_on_failures: int = Field(default=3, ge=1, le=10)
    auto_pause_duration_hours: int = Field(default=6, ge=1, le=48)

    # Gradual ramp-up for new accounts
    ramp_up_mode: bool = Field(default=True)


class RedditState(BaseModel):
    """Runtime state for the Reddit bot (persisted)."""

    version: int = Field(default=1, description="State file version for migrations")

    # Daily counters (reset at midnight)
    posts_today: int = Field(default=0)
    comments_today: int = Field(default=0)
    upvotes_today: int = Field(default=0)
    searches_today: int = Field(default=0)
    last_reset_date: Optional[datetime] = Field(default=None)

    # Recent posts for deduplication
    recent_post_hashes: list[dict] = Field(default_factory=list)

    # Karma tracking
    link_karma: int = Field(default=0)
    comment_karma: int = Field(default=0)
    karma_last_checked: Optional[datetime] = Field(default=None)

    # Session info
    last_login: Optional[datetime] = Field(default=None)
    session_valid: bool = Field(default=False)
    auth_mode: Literal["praw", "browser", "none"] = Field(default="none")

    # Recent submissions / comments
    recent_submissions: list[dict] = Field(default_factory=list)
    recent_comments: list[dict] = Field(default_factory=list)
    pending_replies: list[dict] = Field(default_factory=list)

    # Daemon status
    daemon_running: bool = Field(default=False)
    daemon_started_at: Optional[datetime] = Field(default=None)
    daemon_pid: Optional[int] = Field(default=None)

    # Error tracking
    consecutive_failures: int = Field(default=0)
    last_failure: Optional[datetime] = Field(default=None)

    # Engagement tracking
    engagement_data: dict = Field(default_factory=dict)


class RedditConfig(BaseModel):
    """Complete Reddit bot configuration."""

    version: str = Field(default="1.0.0")
    enabled: bool = Field(default=False)

    # Account settings
    credentials: RedditCredentials = Field(default_factory=RedditCredentials)

    # Rate limits (auto-adjusted based on account type)
    rate_limits: RateLimits = Field(default_factory=RateLimits)

    # Scheduling
    schedule: PostingSchedule = Field(default_factory=PostingSchedule)
    night_mode: NightMode = Field(default_factory=NightMode)

    # Content preferences
    content: ContentPreferences = Field(default_factory=ContentPreferences)

    # Safety settings
    safety: SafetySettings = Field(default_factory=SafetySettings)

    # Proxy settings (if needed)
    http_proxy: str = Field(default="")
    https_proxy: str = Field(default="")

    # Strategy text (what the bot should do)
    strategy: str = Field(
        default="Post interesting tech news to relevant subreddits. Keep it casual and engaging. Comment on posts in target communities.",
        description="Natural language strategy for the bot",
    )

    # News sources for content
    news_sources: list[str] = Field(
        default_factory=lambda: [
            "https://news.ycombinator.com/rss",
            "https://techcrunch.com/feed/",
        ]
    )


# Default configs for account types
DEFAULT_NEW_ACCOUNT_LIMITS = RateLimits(
    max_posts_per_day=1,
    max_posts_per_hour=1,
    max_comments_per_day=5,
    max_comments_per_hour=1,
    max_upvotes_per_day=10,
    max_searches_per_hour=10,
)

DEFAULT_WARMING_LIMITS = RateLimits(
    max_posts_per_day=3,
    max_posts_per_hour=1,
    max_comments_per_day=15,
    max_comments_per_hour=2,
    max_upvotes_per_day=30,
    max_searches_per_hour=30,
)

DEFAULT_ESTABLISHED_LIMITS = RateLimits(
    max_posts_per_day=10,
    max_posts_per_hour=2,
    max_comments_per_day=30,
    max_comments_per_hour=5,
    max_upvotes_per_day=100,
    max_searches_per_hour=50,
)


def get_rate_limits_for_account_type(
    account_type: Literal["new", "warming", "established", "legacy"],
) -> RateLimits:
    """Get appropriate rate limits for account type.

    Args:
        account_type: Type of Reddit account

    Returns:
        RateLimits configuration
    """
    limits = {
        "new": DEFAULT_NEW_ACCOUNT_LIMITS,
        "warming": DEFAULT_WARMING_LIMITS,
        "established": DEFAULT_ESTABLISHED_LIMITS,
        "legacy": DEFAULT_ESTABLISHED_LIMITS,
    }
    return limits.get(account_type, DEFAULT_NEW_ACCOUNT_LIMITS)


# State file location
STATE_FILE = Path.home() / ".ferrox" / "reddit_state.json"
REDDIT_CONFIG_KEY = "reddit"  # Key in main FerroxConfig


def load_reddit_state() -> RedditState:
    """Load Reddit bot state from file.

    Returns:
        RedditState object
    """
    if not STATE_FILE.exists():
        return RedditState()

    try:
        import json

        with open(STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return RedditState(**data)
    except Exception:
        return RedditState()


def save_reddit_state(state: RedditState) -> bool:
    """Save Reddit bot state to file.

    Args:
        state: State to save

    Returns:
        True if successful
    """
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        import json

        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state.model_dump(), f, indent=2, default=str)
        return True
    except Exception as e:
        print(f"Failed to save Reddit state: {e}")
        return False
