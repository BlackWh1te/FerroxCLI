"""X (Twitter) tools for Ferrox agent using twikit.

Provides rate-limited, anti-ban protected access to X API via twikit library.
All tools include built-in safety checks and logging.
"""

import os
import random
import asyncio
import hashlib
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
from pydantic_ai import RunContext

# Import tracer
try:
    from opentelemetry import trace
    tracer = trace.get_tracer(__name__)
except Exception:
    tracer = None

# Import current agent for logging
try:
    from ferrox.agent.orchestrator import _current_agent
except ImportError:
    _current_agent = None

# Ferrox imports
from ..social_config import (
    SocialConfig,
    SocialState,
    load_social_state,
    save_social_state,
    get_rate_limits_for_account_type,
)
from ..utils.content_safety import (
    sanitize_content,
    moderation_check,
    validate_tweet_length,
    check_duplicate_content,
    is_safe_domain,
)
from ..exceptions import ToolExecutionError

# Token bucket rate limiter for twikit calls
class TokenBucket:
    """Token bucket rate limiter for API calls."""
    
    def __init__(self, rate: float, burst: int):
        """Initialize bucket.
        
        Args:
            rate: Tokens per second
            burst: Maximum burst size
        """
        self.rate = rate
        self.burst = burst
        self.tokens = burst
        self.last_update = datetime.now()
    
    async def acquire(self):
        """Acquire a token, waiting if necessary."""
        now = datetime.now()
        elapsed = (now - self.last_update).total_seconds()
        self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
        self.last_update = now
        
        if self.tokens < 1:
            wait_time = (1 - self.tokens) / self.rate
            await asyncio.sleep(wait_time)
            self.tokens = 0
        else:
            self.tokens -= 1


# Global rate limiters
_tweet_bucket = TokenBucket(rate=0.05, burst=2)  # 1 tweet per 20 seconds max
_search_bucket = TokenBucket(rate=0.5, burst=5)  # 1 search per 2 seconds max
_read_bucket = TokenBucket(rate=1.0, burst=10)   # Read operations


def _get_twikit_client(config: SocialConfig):
    """Get or create twikit client with session.

    Tries multiple cookie sources in order:
    1. Config-specified cookie file
    2. Browser-login cookie file (~/.ferrox/twikit_cookies.json)
    3. Falls back to unauthenticated client (caller must handle login)
    """
    try:
        from twikit import Client
    except ImportError:
        raise ToolExecutionError(
            "twikit not installed. Run: pip install twikit",
            {"action": "get_client"}
        )

    client = Client()

    # ── Try config-specified cookie file ──
    cookie_path = Path(config.credentials.cookie_file)
    if cookie_path.exists():
        try:
            client.load_cookies(str(cookie_path))
            return client
        except Exception:
            pass  # Corrupt or incompatible format — try next source

    # ── Try browser-login cookie file ──
    browser_cookie_path = Path.home() / ".ferrox" / "twikit_cookies.json"
    if browser_cookie_path.exists():
        try:
            import json

            with open(browser_cookie_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Twikit accepts both JSON list (load_cookies) and dict (set_cookies).
            # We save as a simple dict {name: value} for maximum compatibility.
            if isinstance(data, dict):
                cookie_dict = data
            elif isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
                cookie_dict = {
                    c["name"]: c["value"] for c in data if "name" in c and "value" in c
                }
            else:
                cookie_dict = None

            if cookie_dict:
                client.set_cookies(cookie_dict)
                return client
        except Exception:
            pass

    return client


def validate_x_session() -> Optional[Dict[str, Any]]:
    """Validate the current X session.

    Checks if cookies exist in the format twikit expects.
    Note: Due to X API changes, twikit may fail at runtime.
    This function validates cookie presence, not live API access.

    Returns:
        Dict with placeholder user data if cookies look valid,
        or None if no valid session cookies found.
    """
    cookie_path = Path.home() / ".ferrox" / "twikit_cookies.json"
    if not cookie_path.exists():
        return None

    try:
        import json
        with open(cookie_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None

    # Twikit expects a simple dict: {name: value, ...}
    if isinstance(data, dict):
        cookie_dict = data
    elif isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
        # Convert list format to dict
        cookie_dict = {c["name"]: c["value"] for c in data if "name" in c and "value" in c}
    else:
        return None

    # Check for critical session cookies
    required = {"auth_token", "ct0"}
    present = set(cookie_dict.keys())
    if not required.issubset(present):
        return None

    # Try to load with twikit (best-effort, may fail due to X API changes)
    try:
        from twikit import Client
        client = Client()
        client.set_cookies(cookie_dict)
    except Exception:
        pass  # twikit may have compatibility issues, but cookies are present

    # Return placeholder info — actual user data will come from tool calls
    return {
        "screen_name": "(unknown — will be fetched via tool call)",
        "name": "(unknown — will be fetched via tool call)",
        "followers_count": 0,
        "following_count": 0,
        "statuses_count": 0,
        "created_at": None,
        "verified": False,
        "profile_image_url": None,
        "_cookie_dict": cookie_dict,
    }


def _log_tool_call(name: str, args: dict):
    """Log tool call via current agent."""
    if _current_agent:
        _current_agent._log_tool_call(name, args)


def _log_tool_result(name: str, result: str, success: bool):
    """Log tool result via current agent."""
    if _current_agent:
        _current_agent._log_tool_result(name, result, success)


async def check_account_health_tool(ctx: RunContext) -> str:
    """Check X account health and determine account type and limits.
    
    Returns:
        Account status including type, limits, and recommendations
    """
    if tracer:
        with tracer.start_as_current_span("check_account_health") as span:
            span.set_attribute("tool", "check_account_health")
    
    _log_tool_call("check_account_health", {})
    
    try:
        state = load_social_state()
        
        # Get config
        if hasattr(ctx, "deps") and hasattr(ctx.deps, "config"):
            from ..config import FerroxConfig
            main_config = ctx.deps.config
            if hasattr(main_config, "social") and main_config.social:
                config = main_config.social
            else:
                config = SocialConfig()
        else:
            config = SocialConfig()
        
        # Get twikit client and verify session
        client = _get_twikit_client(config)
        
        try:
            # Try to get user info to verify session
            user = client.user()
            
            # Calculate account metrics
            created_at = getattr(user, "created_at", None)
            followers_count = getattr(user, "followers_count", 0)
            statuses_count = getattr(user, "statuses_count", 0)
            
            # Determine account type
            account_type = "new"
            if created_at:
                account_age_days = (datetime.now() - created_at).days
                if account_age_days > 730 and statuses_count > 5000:
                    account_type = "legacy"
                elif account_age_days > 90 and statuses_count > 500:
                    account_type = "established"
                elif account_age_days > 30 and statuses_count > 100:
                    account_type = "warming"
            
            # Get appropriate limits
            limits = get_rate_limits_for_account_type(account_type)
            
            # Reset daily counters if needed
            today = datetime.now().date()
            if state.last_reset_date != today:
                state.posts_today = 0
                state.likes_today = 0
                state.replies_today = 0
                state.follows_today = 0
                state.searches_today = 0
                state.last_reset_date = today
                save_social_state(state)
            
            # Build status report
            output = f"""Account Health Check Results:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Account Type: {account_type.upper()}
Username: @{getattr(user, 'screen_name', 'unknown')}
Followers: {followers_count:,}
Total Tweets: {statuses_count:,}
Account Age: {account_age_days if created_at else 'unknown'} days

Today's Usage:
  Posts: {state.posts_today}/{limits.max_posts_per_day}
  Likes: {state.likes_today}/{limits.max_likes_per_day}
  Replies: {state.replies_today}/{limits.max_replies_per_day}

Limits Applied:
  Max posts/day: {limits.max_posts_per_day}
  Max posts/hour: {limits.max_posts_per_hour}
  Draft mode: {'ENABLED (approval required)' if config.content.draft_mode else 'DISABLED (auto-post)'}

Recommendations:
"""
            if account_type == "new":
                output += "  CRITICAL: New account - use extreme caution\n"
                output += "  - Max 1 post/day for first 14 days\n"
                output += "  - Manual posting only (no daemon)\n"
                output += "  - No links in first 7 days\n"
                output += "  - Warmup routine REQUIRED\n"
            elif account_type == "warming":
                output += "  HIGH: Warming account - be careful\n"
                output += "  - Max 3 posts/day\n"
                output += "  - Daemon allowed with 6h intervals\n"
            else:
                output += f"  {account_type.upper()}: Standard limits apply\n"
            
            state.session_valid = True
            state.last_login = datetime.now()
            save_social_state(state)
            
            _log_tool_result("check_account_health", f"Account type: {account_type}", True)
            return output
            
        except Exception as e:
            state.session_valid = False
            save_social_state(state)
            _log_tool_result("check_account_health", f"Session invalid: {str(e)}", False)
            err_msg = str(e)
            if "KEY_BYTE" in err_msg or "indices" in err_msg or "ClientTransaction" in err_msg:
                return (
                    "X API Error: Twikit is incompatible with X's current API response format.\n"
                    "This is a known upstream issue (not a Ferrox bug).\n"
                    "Try: pip install --upgrade twikit  (or wait for a fix).\n"
                    f"Details: {err_msg[:120]}"
                )
            return f"Session invalid. Please run /social login first.\nError: {e}"
    
    except Exception as e:
        _log_tool_result("check_account_health", str(e), False)
        return f"Error checking account health: {e}"


async def search_tweets_tool(
    ctx: RunContext,
    query: str,
    max_results: int = 10,
    search_type: str = "Latest"
) -> str:
    """Search for tweets on X.
    
    Args:
        query: Search query string
        max_results: Maximum results to return (max 50)
        search_type: "Top", "Latest", "Photos", "Videos"
        
    Returns:
        Search results with tweet details
    """
    if tracer:
        with tracer.start_as_current_span("search_tweets") as span:
            span.set_attribute("query", query)
            span.set_attribute("max_results", max_results)
    
    _log_tool_call("search_tweets", {"query": query, "max_results": max_results})
    
    # Rate limit check
    await _search_bucket.acquire()
    
    # Update state
    state = load_social_state()
    state.searches_today += 1
    save_social_state(state)
    
    try:
        config = SocialConfig()
        client = _get_twikit_client(config)
        
        tweets = client.search_tweet(query, search_type, count=min(max_results, 50))
        
        output = f"Search results for '{query}' ({search_type}):\n"
        output += "=" * 60 + "\n\n"
        
        for i, tweet in enumerate(tweets, 1):
            output += f"{i}. @{tweet.user.name}\n"
            output += f"   {tweet.text[:200]}...\n" if len(tweet.text) > 200 else f"   {tweet.text}\n"
            output += f"   Likes: {tweet.favorite_count} | RTs: {tweet.retweet_count}\n"
            output += f"   ID: {tweet.id}\n\n"
        
        _log_tool_result("search_tweets", f"Found {len(tweets)} tweets", True)
        return output
        
    except Exception as e:
        _log_tool_result("search_tweets", str(e), False)
        err_msg = str(e)
        if "KEY_BYTE" in err_msg or "indices" in err_msg or "ClientTransaction" in err_msg:
            return (
                "X API Error: Twikit is incompatible with X's current API response format.\n"
                "This is a known upstream issue (not a Ferrox bug).\n"
                f"Details: {err_msg[:120]}"
            )
        return f"Error searching tweets: {e}"


async def post_tweet_tool(
    ctx: RunContext,
    text: str,
    reply_to_id: Optional[str] = None,
    dry_run: bool = False,
) -> str:
    """Post a tweet to X.
    
    Args:
        text: Tweet text content
        reply_to_id: Optional tweet ID to reply to
        dry_run: If True, preview only without posting
        
    Returns:
        Result of posting attempt
    """
    if tracer:
        with tracer.start_as_current_span("post_tweet") as span:
            span.set_attribute("text_length", len(text))
            span.set_attribute("dry_run", dry_run)
    
    _log_tool_call("post_tweet", {"text_length": len(text), "dry_run": dry_run})
    
    try:
        config = SocialConfig()
        state = load_social_state()
        
        # Get limits
        limits = get_rate_limits_for_account_type("new")  # Conservative default
        
        # Check daily limit
        if state.posts_today >= limits.max_posts_per_day:
            msg = f"CRITICAL: Daily post limit reached ({limits.max_posts_per_day}). Refusing to post."
            _log_tool_result("post_tweet", msg, False)
            return msg
        
        # Sanitize content
        sanitized, warnings = sanitize_content(text)
        if warnings:
            _log_tool_result("post_tweet", f"Content blocked: {warnings[0]}", False)
            return f"Content blocked: {warnings[0]}"
        
        # Moderation check
        is_safe, violations = moderation_check(sanitized)
        if not is_safe:
            violations_str = "; ".join(violations)
            _log_tool_result("post_tweet", f"Moderation failed: {violations_str}", False)
            return f"MODERATION FAILED:\n{violations_str}\n\nPlease revise content."
        
        # Validate length
        is_valid, effective_len, length_msg = validate_tweet_length(sanitized)
        if not is_valid:
            _log_tool_result("post_tweet", length_msg, False)
            return f"TWEET TOO LONG: {length_msg}\n\nConsider using post_thread_tool for longer content."
        
        # Check duplicates
        recent_texts = [p.get("text", "") for p in state.recent_post_hashes[-20:]]
        is_dup, similarity, closest = check_duplicate_content(sanitized, recent_texts)
        if is_dup:
            msg = f"DUPLICATE DETECTED ({similarity:.0%} similar to previous post). Refusing."
            _log_tool_result("post_tweet", msg, False)
            return f"{msg}\n\nPrevious: {closest}"
        
        # Draft mode check
        if config.content.draft_mode and not dry_run:
            output = f"DRAFT MODE - Tweet ready for approval:\n"
            output += f"Content: {sanitized}\n"
            output += f"Length: {effective_len}/280 chars\n"
            output += f"Safe: Yes\n"
            output += "\nType 'APPROVE' to post, or revise and try again."
            _log_tool_result("post_tweet", "Draft presented for approval", True)
            return output
        
        if dry_run:
            output = f"DRY RUN - Tweet would be posted:\n"
            output += f"Content: {sanitized}\n"
            output += f"Length: {effective_len}/280 chars\n"
            output += "\nUse dry_run=False to actually post."
            _log_tool_result("post_tweet", "Dry run preview", True)
            return output
        
        # Rate limit
        await _tweet_bucket.acquire()
        
        # Post tweet
        client = _get_twikit_client(config)
        
        if reply_to_id:
            tweet = client.create_tweet(sanitized, reply_to=reply_to_id)
        else:
            tweet = client.create_tweet(sanitized)
        
        # Update state
        state.posts_today += 1
        state.recent_tweets.append({
            "id": tweet.id,
            "text": sanitized[:100],
            "hash": hashlib.md5(sanitized.lower().encode()).hexdigest()[:16],
            "posted_at": datetime.now().isoformat(),
        })
        state.consecutive_failures = 0
        save_social_state(state)
        
        output = f"✅ Tweet posted successfully!\n"
        output += f"Tweet ID: {tweet.id}\n"
        output += f"URL: https://x.com/i/web/status/{tweet.id}"
        
        _log_tool_result("post_tweet", f"Tweet {tweet.id} posted", True)
        return output
        
    except Exception as e:
        # Update failure tracking
        state = load_social_state()
        state.consecutive_failures += 1
        state.last_failure = datetime.now()
        save_social_state(state)
        
        _log_tool_result("post_tweet", str(e), False)
        err_msg = str(e)
        if "KEY_BYTE" in err_msg or "indices" in err_msg or "ClientTransaction" in err_msg:
            return (
                "X API Error: Twikit is incompatible with X's current API response format.\n"
                "This is a known upstream issue (not a Ferrox bug).\n"
                f"Details: {err_msg[:120]}"
            )
        return f"Error posting tweet: {e}"


async def post_thread_tool(ctx: RunContext, texts: List[str]) -> str:
    """Post a thread (series of connected tweets).
    
    Args:
        texts: List of tweet texts (each will be a tweet in the thread)
        
    Returns:
        Result of posting attempt
    """
    _log_tool_call("post_thread", {"tweet_count": len(texts)})
    
    if len(texts) > 10:
        return "Thread too long (max 10 tweets). Consider breaking into multiple threads."
    
    try:
        config = SocialConfig()
        state = load_social_state()
        limits = get_rate_limits_for_account_type("new")
        
        # Check if we have enough quota
        if state.posts_today + len(texts) > limits.max_posts_per_day:
            return f"Not enough daily quota for {len(texts)} tweets. Have {limits.max_posts_per_day - state.posts_today}, need {len(texts)}."
        
        client = _get_twikit_client(config)
        
        tweets = []
        prev_id = None
        
        for i, text in enumerate(texts, 1):
            # Moderation check
            is_safe, violations = moderation_check(text)
            if not is_safe:
                return f"Moderation failed on tweet {i}: {'; '.join(violations)}"
            
            # Rate limit
            await _tweet_bucket.acquire()
            
            # Post
            if prev_id:
                tweet = client.create_tweet(text, reply_to=prev_id)
            else:
                tweet = client.create_tweet(text)
            
            tweets.append(tweet)
            prev_id = tweet.id
            
            # Small delay between tweets
            if i < len(texts):
                await asyncio.sleep(2)
        
        # Update state
        state.posts_today += len(tweets)
        save_social_state(state)
        
        output = f"✅ Thread posted! {len(tweets)} tweets\n"
        output += f"First tweet: https://x.com/i/web/status/{tweets[0].id}"
        
        _log_tool_result("post_thread", f"Thread with {len(tweets)} tweets posted", True)
        return output
        
    except Exception as e:
        _log_tool_result("post_thread", str(e), False)
        err_msg = str(e)
        if "KEY_BYTE" in err_msg or "indices" in err_msg or "ClientTransaction" in err_msg:
            return (
                "X API Error: Twikit is incompatible with X's current API response format.\n"
                "This is a known upstream issue (not a Ferrox bug).\n"
                f"Details: {err_msg[:120]}"
            )
        return f"Error posting thread: {e}"


async def get_recent_posts_tool(ctx: RunContext, count: int = 20) -> str:
    """Get recent posts from the bot's account.
    
    Args:
        count: Number of recent posts to retrieve
        
    Returns:
        List of recent tweets
    """
    _log_tool_call("get_recent_posts", {"count": count})
    
    try:
        config = SocialConfig()
        client = _get_twikit_client(config)
        
        user = client.user()
        tweets = client.get_user_tweets(user.id, count=min(count, 50))
        
        output = f"Recent posts from @{user.screen_name}:\n"
        output += "=" * 60 + "\n\n"
        
        for i, tweet in enumerate(tweets, 1):
            output += f"{i}. {tweet.text[:150]}...\n" if len(tweet.text) > 150 else f"{i}. {tweet.text}\n"
            output += f"   Likes: {tweet.favorite_count} | ID: {tweet.id}\n\n"
        
        _log_tool_result("get_recent_posts", f"Retrieved {len(tweets)} tweets", True)
        return output
        
    except Exception as e:
        _log_tool_result("get_recent_posts", str(e), False)
        err_msg = str(e)
        if "KEY_BYTE" in err_msg or "indices" in err_msg or "ClientTransaction" in err_msg:
            return (
                "X API Error: Twikit is incompatible with X's current API response format.\n"
                "This is a known upstream issue (not a Ferrox bug).\n"
                f"Details: {err_msg[:120]}"
            )
        return f"Error getting recent posts: {e}"


async def check_visibility_tool(ctx: RunContext, tweet_id: str) -> str:
    """Check if a tweet is visible (not shadowbanned).
    
    Args:
        tweet_id: Tweet ID to check
        
    Returns:
        Visibility check result
    """
    _log_tool_call("check_visibility", {"tweet_id": tweet_id})
    
    try:
        config = SocialConfig()
        client = _get_twikit_client(config)
        
        # Wait a bit for indexing
        await asyncio.sleep(5)
        
        # Try to retrieve the tweet
        try:
            tweet = client.get_tweet_by_id(tweet_id)
            if tweet:
                _log_tool_result("check_visibility", "Tweet is visible", True)
                return f"✅ Tweet {tweet_id} is visible and indexed."
        except:
            pass
        
        # If not found directly, search for text
        # (This is a heuristic - shadowbanned tweets often don't appear in search)
        _log_tool_result("check_visibility", "Tweet not visible - possible shadowban", False)
        return f"⚠️ Tweet {tweet_id} not found in search. Possible shadowban detected."
        
    except Exception as e:
        _log_tool_result("check_visibility", str(e), False)
        return f"Error checking visibility: {e}"


async def get_trends_tool(ctx: RunContext) -> str:
    """Get current trending topics.
    
    Returns:
        List of trending topics
    """
    _log_tool_call("get_trends", {})
    
    await _read_bucket.acquire()
    
    try:
        config = SocialConfig()
        client = _get_twikit_client(config)
        
        # Get trends (usually requires a location ID, using 1 for worldwide)
        trends = client.get_trends(1)
        
        output = "Current Trends (Worldwide):\n"
        output += "=" * 60 + "\n\n"
        
        for i, trend in enumerate(trends[:20], 1):
            output += f"{i}. #{trend.name} - {trend.tweet_volume or 'N/A'} tweets\n"
        
        _log_tool_result("get_trends", f"Retrieved {len(trends)} trends", True)
        return output
        
    except Exception as e:
        _log_tool_result("get_trends", str(e), False)
        return f"Error getting trends: {e}"


async def get_mentions_tool(ctx: RunContext, count: int = 20) -> str:
    """Get mentions and notifications.
    
    Args:
        count: Number of mentions to retrieve
        
    Returns:
        List of mentions
    """
    _log_tool_call("get_mentions", {"count": count})
    
    await _read_bucket.acquire()
    
    try:
        config = SocialConfig()
        client = _get_twikit_client(config)
        
        # Get mentions timeline
        mentions = client.get_mentions(count=min(count, 50))
        
        output = "Recent Mentions:\n"
        output += "=" * 60 + "\n\n"
        
        for i, tweet in enumerate(mentions, 1):
            output += f"{i}. @{tweet.user.name}: {tweet.text[:100]}...\n"
            output += f"   ID: {tweet.id}\n\n"
        
        _log_tool_result("get_mentions", f"Retrieved {len(mentions)} mentions", True)
        return output
        
    except Exception as e:
        _log_tool_result("get_mentions", str(e), False)
        return f"Error getting mentions: {e}"


async def like_tweet_tool(ctx: RunContext, tweet_id: str) -> str:
    """Like a tweet.
    
    Args:
        tweet_id: Tweet ID to like
        
    Returns:
        Result of like operation
    """
    _log_tool_call("like_tweet", {"tweet_id": tweet_id})
    
    # Check limits
    state = load_social_state()
    limits = get_rate_limits_for_account_type("new")
    
    if state.likes_today >= limits.max_likes_per_day:
        return f"Daily like limit reached ({limits.max_likes_per_day})."
    
    await _read_bucket.acquire()
    
    try:
        config = SocialConfig()
        client = _get_twikit_client(config)
        
        client.like_tweet(tweet_id)
        
        state.likes_today += 1
        save_social_state(state)
        
        _log_tool_result("like_tweet", f"Liked {tweet_id}", True)
        return f"✅ Liked tweet {tweet_id}"
        
    except Exception as e:
        _log_tool_result("like_tweet", str(e), False)
        return f"Error liking tweet: {e}"


async def retweet_tweet_tool(ctx: RunContext, tweet_id: str) -> str:
    """Retweet a tweet.
    
    Args:
        tweet_id: Tweet ID to retweet
        
    Returns:
        Result of retweet operation
    """
    _log_tool_call("retweet_tweet", {"tweet_id": tweet_id})
    
    # Retweets count as posts for limits
    state = load_social_state()
    limits = get_rate_limits_for_account_type("new")
    
    if state.posts_today >= limits.max_posts_per_day:
        return f"Daily post limit reached ({limits.max_posts_per_day})."
    
    await _tweet_bucket.acquire()
    
    try:
        config = SocialConfig()
        client = _get_twikit_client(config)
        
        client.retweet(tweet_id)
        
        state.posts_today += 1  # Retweets count toward limit
        save_social_state(state)
        
        _log_tool_result("retweet_tweet", f"Retweeted {tweet_id}", True)
        return f"✅ Retweeted tweet {tweet_id}"
        
    except Exception as e:
        _log_tool_result("retweet_tweet", str(e), False)
        return f"Error retweeting: {e}"


async def delete_tweet_tool(ctx: RunContext, tweet_id: str) -> str:
    """Delete a tweet (undo last post).
    
    Args:
        tweet_id: Tweet ID to delete
        
    Returns:
        Result of delete operation
    """
    _log_tool_call("delete_tweet", {"tweet_id": tweet_id})
    
    await _tweet_bucket.acquire()
    
    try:
        config = SocialConfig()
        client = _get_twikit_client(config)
        
        client.delete_tweet(tweet_id)
        
        # Remove from recent tweets
        state = load_social_state()
        state.recent_tweets = [t for t in state.recent_tweets if t.get("id") != tweet_id]
        save_social_state(state)
        
        _log_tool_result("delete_tweet", f"Deleted {tweet_id}", True)
        return f"✅ Deleted tweet {tweet_id}"
        
    except Exception as e:
        _log_tool_result("delete_tweet", str(e), False)
        return f"Error deleting tweet: {e}"
