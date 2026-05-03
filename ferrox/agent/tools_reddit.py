"""Reddit tools for Ferrox agent using PRAW (primary) with Playwright browser fallback.

Provides rate-limited, anti-ban protected access to Reddit API.
All tools include built-in safety checks and logging.
"""

import os
import random
import asyncio
import hashlib
import json
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
from ..reddit_config import (
    RedditConfig,
    RedditState,
    load_reddit_state,
    save_reddit_state,
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

# Token bucket rate limiter for Reddit calls
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
_post_bucket = TokenBucket(rate=0.05, burst=2)     # 1 post per 20 seconds max
_comment_bucket = TokenBucket(rate=0.05, burst=2)  # 1 comment per 20 seconds max
_search_bucket = TokenBucket(rate=0.5, burst=5)    # 1 search per 2 seconds max
_read_bucket = TokenBucket(rate=1.0, burst=10)    # Read operations


def _get_praw_client(config: RedditConfig):
    """Get or create PRAW client with credentials.

    Tries API credentials first. Falls back to browser cookie scraping
    if PRAW auth fails (documented as secondary mode).
    """
    try:
        import praw
    except ImportError:
        raise ToolExecutionError(
            "praw not installed. Run: pip install praw",
            {"action": "get_praw_client"}
        )

    creds = config.credentials

    # If OAuth credentials are present, use them
    if creds.client_id and creds.client_secret and creds.username and creds.password:
        try:
            client = praw.Reddit(
                client_id=creds.client_id,
                client_secret=creds.client_secret,
                username=creds.username,
                password=creds.password,
                user_agent=creds.user_agent,
            )
            # Verify auth
            client.user.me()
            return client
        except Exception:
            pass  # Fall through to cookie/browser fallback

    # Fallback: try browser cookies if available
    cookie_path = Path.home() / ".ferrox" / "reddit_cookies.json"
    if cookie_path.exists():
        # PRAW does not support raw cookie auth directly; caller must use
        # browser_driver mode. Signal this clearly.
        raise ToolExecutionError(
            "PRAW OAuth failed and cookie fallback requires browser mode. "
            "Run /reddit login via browser, or provide client_id/client_secret.",
            {"action": "get_praw_client", "fallback": "browser_cookie"}
        )

    raise ToolExecutionError(
        "No valid Reddit credentials. Provide OAuth details or run /reddit login.",
        {"action": "get_praw_client"}
    )


def _get_browser_driver():
    """Get a Playwright browser page for cookie-based actions.

    Used as fallback when PRAW OAuth is unavailable.
    Loads saved cookies from ~/.ferrox/reddit_cookies.json if present.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise ToolExecutionError(
            "Playwright not installed. Run: pip install playwright",
            {"action": "get_browser_driver"}
        )

    # Return a factory; actual page creation is async and done per-call
    return async_playwright


def validate_reddit_session() -> Optional[Dict[str, Any]]:
    """Validate the current Reddit session.

    Checks if PRAW OAuth or browser cookies exist in usable form.
    Returns placeholder user data if session looks valid,
    or None if no valid session found.
    """
    # Check OAuth credentials
    config = RedditConfig()
    creds = config.credentials
    if creds.client_id and creds.client_secret and creds.username:
        try:
            client = _get_praw_client(config)
            me = client.user.me()
            if me:
                return {
                    "name": me.name,
                    "link_karma": me.link_karma,
                    "comment_karma": me.comment_karma,
                    "created_utc": me.created_utc,
                    "is_mod": me.is_mod,
                }
        except Exception:
            pass

    # Check browser cookies
    cookie_path = Path.home() / ".ferrox" / "reddit_cookies.json"
    if cookie_path.exists():
        try:
            with open(cookie_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "cookies" in data:
                return {
                    "name": "(unknown — browser session)",
                    "link_karma": 0,
                    "comment_karma": 0,
                    "created_utc": None,
                    "is_mod": False,
                    "_cookie_dict": data["cookies"],
                }
        except Exception:
            pass

    return None


def _log_tool_call(name: str, args: dict):
    """Log tool call via current agent."""
    if _current_agent:
        _current_agent._log_tool_call(name, args)


def _log_tool_result(name: str, result: str, success: bool):
    """Log tool result via current agent."""
    if _current_agent:
        _current_agent._log_tool_result(name, result, success)


async def reddit_check_account_health_tool(ctx: RunContext) -> str:
    """Check Reddit account health and determine account type and limits.

    Returns:
        Account status including type, limits, and recommendations
    """
    if tracer:
        with tracer.start_as_current_span("check_account_health") as span:
            span.set_attribute("tool", "check_account_health")

    _log_tool_call("check_account_health", {})

    try:
        state = load_reddit_state()

        # Get config
        if hasattr(ctx, "deps") and hasattr(ctx.deps, "config"):
            from ..config import FerroxConfig
            main_config = ctx.deps.config
            if hasattr(main_config, "reddit") and main_config.reddit:
                config = main_config.reddit
            else:
                config = RedditConfig()
        else:
            config = RedditConfig()

        # Try PRAW client
        try:
            client = _get_praw_client(config)
            me = client.user.me()

            # Calculate account metrics
            created_utc = getattr(me, "created_utc", None)
            link_karma = getattr(me, "link_karma", 0)
            comment_karma = getattr(me, "comment_karma", 0)
            total_karma = link_karma + comment_karma

            # Determine account type
            account_type = "new"
            account_age_days = 0
            if created_utc:
                account_age_days = (datetime.now() - datetime.fromtimestamp(created_utc)).days
                if account_age_days > 730 and total_karma > 5000:
                    account_type = "legacy"
                elif account_age_days > 90 and total_karma > 500:
                    account_type = "established"
                elif account_age_days > 30 and total_karma > 100:
                    account_type = "warming"

            # Get appropriate limits
            limits = get_rate_limits_for_account_type(account_type)

            # Reset daily counters if needed
            today = datetime.now().date()
            if state.last_reset_date != today:
                state.posts_today = 0
                state.comments_today = 0
                state.upvotes_today = 0
                state.searches_today = 0
                state.last_reset_date = today
                save_reddit_state(state)

            # Build status report
            output = f"""Account Health Check Results:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Account Type: {account_type.upper()}
Username: /u/{getattr(me, 'name', 'unknown')}
Link Karma: {link_karma:,}
Comment Karma: {comment_karma:,}
Total Karma: {total_karma:,}
Account Age: {account_age_days if created_utc else 'unknown'} days

Today's Usage:
  Posts: {state.posts_today}/{limits.max_posts_per_day}
  Comments: {state.comments_today}/{limits.max_comments_per_day}
  Upvotes: {state.upvotes_today}/{limits.max_upvotes_per_day}

Limits Applied:
  Max posts/day: {limits.max_posts_per_day}
  Max posts/hour: {limits.max_posts_per_hour}
  Max comments/day: {limits.max_comments_per_day}
  Draft mode: {'ENABLED (approval required)' if config.content.draft_mode else 'DISABLED (auto-post)'}

Recommendations:
"""
            if account_type == "new":
                output += "  CRITICAL: New account - use extreme caution\n"
                output += "  - Max 1 post/day for first 14 days\n"
                output += "  - Manual posting only (no daemon)\n"
                output += "  - No links in first 7 days\n"
                output += "  - Warmup routine REQUIRED\n"
                output += "  - Comment more than post (build karma)\n"
            elif account_type == "warming":
                output += "  HIGH: Warming account - be careful\n"
                output += "  - Max 3 posts/day\n"
                output += "  - Daemon allowed with 6h intervals\n"
                output += "  - Comment-to-post ratio 3:1 minimum\n"
            else:
                output += f"  {account_type.upper()}: Standard limits apply\n"

            state.session_valid = True
            state.last_login = datetime.now()
            state.link_karma = link_karma
            state.comment_karma = comment_karma
            save_reddit_state(state)

            _log_tool_result("check_account_health", f"Account type: {account_type}", True)
            return output

        except ToolExecutionError:
            # OAuth/browser unavailable - check cookie presence only
            cookie_path = Path.home() / ".ferrox" / "reddit_cookies.json"
            if cookie_path.exists():
                state.session_valid = True  # optimistic
                state.last_login = datetime.now()
                save_reddit_state(state)
                _log_tool_result("check_account_health", "Browser session (unverified)", True)
                return (
                    "Account Health Check Results:\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "Auth mode: BROWSER COOKIE (unverified)\n"
                    "Session cookies exist. Run check_account_health after "
                    "/reddit login to verify live access.\n"
                    f"Posts today: {state.posts_today}\n"
                    f"Comments today: {state.comments_today}\n"
                )

            state.session_valid = False
            save_reddit_state(state)
            _log_tool_result("check_account_health", "No session", False)
            return "Session invalid. Please run /reddit login or provide OAuth credentials."

    except Exception as e:
        _log_tool_result("check_account_health", str(e), False)
        return f"Error checking account health: {e}"


async def search_subreddit_tool(
    ctx: RunContext,
    subreddit: str,
    query: str,
    max_results: int = 10,
) -> str:
    """Search for posts in a subreddit.

    Args:
        subreddit: Subreddit name (without /r/)
        query: Search query string
        max_results: Maximum results to return (max 50)

    Returns:
        Search results with post details
    """
    if tracer:
        with tracer.start_as_current_span("search_subreddit") as span:
            span.set_attribute("subreddit", subreddit)
            span.set_attribute("query", query)
            span.set_attribute("max_results", max_results)

    _log_tool_call("search_subreddit", {"subreddit": subreddit, "query": query, "max_results": max_results})

    # Rate limit check
    await _search_bucket.acquire()

    # Update state
    state = load_reddit_state()
    state.searches_today += 1
    save_reddit_state(state)

    try:
        config = RedditConfig()
        client = _get_praw_client(config)

        sub = client.subreddit(subreddit)
        results = list(sub.search(query, limit=min(max_results, 50)))

        output = f"Search results in r/{subreddit} for '{query}':\n"
        output += "=" * 60 + "\n\n"

        for i, post in enumerate(results, 1):
            output += f"{i}. {post.title[:120]}\n"
            output += f"   Score: {post.score} | Comments: {post.num_comments}\n"
            output += f"   ID: {post.id}\n\n"

        _log_tool_result("search_subreddit", f"Found {len(results)} posts", True)
        return output

    except Exception as e:
        _log_tool_result("search_subreddit", str(e), False)
        return f"Error searching subreddit: {e}"


async def post_submission_tool(
    ctx: RunContext,
    subreddit: str,
    title: str,
    text: str,
    url: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Post a submission to a subreddit.

    Args:
        subreddit: Target subreddit name (without /r/)
        title: Submission title
        text: Submission body text (for self-post)
        url: Optional URL (for link post; overrides text)
        dry_run: If True, preview only without posting

    Returns:
        Dict with success, data, message keys
    """
    if tracer:
        with tracer.start_as_current_span("post_submission") as span:
            span.set_attribute("subreddit", subreddit)
            span.set_attribute("title_length", len(title))
            span.set_attribute("dry_run", dry_run)

    _log_tool_call("post_submission", {"subreddit": subreddit, "title": title, "dry_run": dry_run})

    try:
        config = RedditConfig()
        state = load_reddit_state()

        # Get limits
        limits = get_rate_limits_for_account_type("new")  # Conservative default

        # Check daily limit
        if state.posts_today >= limits.max_posts_per_day:
            msg = f"CRITICAL: Daily post limit reached ({limits.max_posts_per_day}). Refusing to post."
            _log_tool_result("post_submission", msg, False)
            return {"success": False, "data": None, "message": msg}

        # Sanitize content
        full_text = title + "\n\n" + text
        sanitized, warnings = sanitize_content(full_text)
        if warnings:
            _log_tool_result("post_submission", f"Content blocked: {warnings[0]}", False)
            return {"success": False, "data": None, "message": f"Content blocked: {warnings[0]}"}

        # Moderation check
        is_safe, violations = moderation_check(sanitized)
        if not is_safe:
            violations_str = "; ".join(violations)
            _log_tool_result("post_submission", f"Moderation failed: {violations_str}", False)
            return {"success": False, "data": None, "message": f"MODERATION FAILED:\n{violations_str}\n\nPlease revise content."}

        # Validate post length (Reddit title max 300)
        is_valid, effective_len, length_msg = validate_tweet_length(title, max_length=300)
        if not is_valid:
            _log_tool_result("post_submission", length_msg, False)
            return {"success": False, "data": None, "message": f"TITLE TOO LONG: {length_msg}"}

        # Check duplicates
        recent_texts = [p.get("title", "") for p in state.recent_post_hashes[-20:]]
        is_dup, similarity, closest = check_duplicate_content(title, recent_texts)
        if is_dup:
            msg = f"DUPLICATE DETECTED ({similarity:.0%} similar to previous post). Refusing."
            _log_tool_result("post_submission", msg, False)
            return {"success": False, "data": None, "message": f"{msg}\n\nPrevious: {closest}"}

        # Draft mode check
        if config.content.draft_mode and not dry_run:
            output = "DRAFT MODE - Submission ready for approval:\n"
            output += f"Subreddit: r/{subreddit}\n"
            output += f"Title: {title}\n"
            output += f"Type: {'Link' if url else 'Self'}\n"
            output += f"Safe: Yes\n"
            output += "\nType 'APPROVE' to post, or revise and try again."
            _log_tool_result("post_submission", "Draft presented for approval", True)
            return {"success": True, "data": {"draft": True}, "message": output}

        if dry_run:
            output = "DRY RUN - Submission would be posted:\n"
            output += f"Subreddit: r/{subreddit}\n"
            output += f"Title: {title}\n"
            output += f"Type: {'Link' if url else 'Self'}\n"
            output += "\nUse dry_run=False to actually post."
            _log_tool_result("post_submission", "Dry run preview", True)
            return {"success": True, "data": {"dry_run": True}, "message": output}

        # Rate limit
        await _post_bucket.acquire()

        # Post submission
        client = _get_praw_client(config)
        sub = client.subreddit(subreddit)

        if url:
            submission = sub.submit(title=title, url=url)
        else:
            submission = sub.submit(title=title, selftext=text)

        # Update state
        state.posts_today += 1
        post_record = {
            "id": submission.id,
            "title": title[:100],
            "hash": hashlib.md5(title.lower().encode(), usedforsecurity=False).hexdigest()[:16],
            "subreddit": subreddit,
            "posted_at": datetime.now().isoformat(),
        }
        state.recent_submissions.append(post_record)
        state.recent_post_hashes.append(post_record)
        state.consecutive_failures = 0
        save_reddit_state(state)

        output = f"Posted successfully!\n"
        output += f"Post ID: {submission.id}\n"
        output += f"Permalink: https://reddit.com{submission.permalink}"

        _log_tool_result("post_submission", f"Post {submission.id} posted", True)
        return {"success": True, "data": {"post_id": submission.id, "permalink": submission.permalink}, "message": output}

    except Exception as e:
        # Update failure tracking
        state = load_reddit_state()
        state.consecutive_failures += 1
        state.last_failure = datetime.now()
        save_reddit_state(state)

        _log_tool_result("post_submission", str(e), False)
        return {"success": False, "data": None, "message": f"Error posting submission: {e}"}


async def post_comment_tool(
    ctx: RunContext,
    post_id: str,
    text: str,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Post a comment on a Reddit submission.

    Args:
        post_id: Reddit post ID (e.g., '1abc123')
        text: Comment text
        dry_run: If True, preview only without posting

    Returns:
        Dict with success, data, message keys
    """
    if tracer:
        with tracer.start_as_current_span("post_comment") as span:
            span.set_attribute("post_id", post_id)
            span.set_attribute("text_length", len(text))
            span.set_attribute("dry_run", dry_run)

    _log_tool_call("post_comment", {"post_id": post_id, "text_length": len(text), "dry_run": dry_run})

    try:
        config = RedditConfig()
        state = load_reddit_state()
        limits = get_rate_limits_for_account_type("new")

        # Check daily limit
        if state.comments_today >= limits.max_comments_per_day:
            msg = f"CRITICAL: Daily comment limit reached ({limits.max_comments_per_day}). Refusing to comment."
            _log_tool_result("post_comment", msg, False)
            return {"success": False, "data": None, "message": msg}

        # Sanitize content
        sanitized, warnings = sanitize_content(text)
        if warnings:
            _log_tool_result("post_comment", f"Content blocked: {warnings[0]}", False)
            return {"success": False, "data": None, "message": f"Content blocked: {warnings[0]}"}

        # Moderation check
        is_safe, violations = moderation_check(sanitized)
        if not is_safe:
            violations_str = "; ".join(violations)
            _log_tool_result("post_comment", f"Moderation failed: {violations_str}", False)
            return {"success": False, "data": None, "message": f"MODERATION FAILED:\n{violations_str}\n\nPlease revise content."}

        # Draft mode check
        if config.content.draft_mode and not dry_run:
            output = "DRAFT MODE - Comment ready for approval:\n"
            output += f"Post ID: {post_id}\n"
            output += f"Comment: {sanitized[:200]}...\n" if len(sanitized) > 200 else f"Comment: {sanitized}\n"
            output += "\nType 'APPROVE' to post, or revise and try again."
            _log_tool_result("post_comment", "Draft presented for approval", True)
            return {"success": True, "data": {"draft": True}, "message": output}

        if dry_run:
            output = "DRY RUN - Comment would be posted:\n"
            output += f"Post ID: {post_id}\n"
            output += f"Comment: {sanitized[:200]}...\n" if len(sanitized) > 200 else f"Comment: {sanitized}\n"
            output += "\nUse dry_run=False to actually post."
            _log_tool_result("post_comment", "Dry run preview", True)
            return {"success": True, "data": {"dry_run": True}, "message": output}

        # Rate limit
        await _comment_bucket.acquire()

        # Post comment
        client = _get_praw_client(config)
        submission = client.submission(id=post_id)
        comment = submission.reply(sanitized)

        # Update state
        state.comments_today += 1
        state.recent_comments.append({
            "id": comment.id,
            "body": sanitized[:100],
            "post_id": post_id,
            "posted_at": datetime.now().isoformat(),
        })
        state.consecutive_failures = 0
        save_reddit_state(state)

        output = f"Comment posted successfully!\n"
        output += f"Comment ID: {comment.id}\n"
        output += f"Permalink: https://reddit.com{comment.permalink}"

        _log_tool_result("post_comment", f"Comment {comment.id} posted", True)
        return {"success": True, "data": {"comment_id": comment.id, "permalink": comment.permalink}, "message": output}

    except Exception as e:
        state = load_reddit_state()
        state.consecutive_failures += 1
        state.last_failure = datetime.now()
        save_reddit_state(state)

        _log_tool_result("post_comment", str(e), False)
        return {"success": False, "data": None, "message": f"Error posting comment: {e}"}


async def get_trending_subreddits_tool(ctx: RunContext) -> str:
    """Get currently trending subreddits.

    Returns:
        List of trending subreddit names
    """
    if tracer:
        with tracer.start_as_current_span("get_trending_subreddits") as span:
            span.set_attribute("tool", "get_trending_subreddits")

    _log_tool_call("get_trending_subreddits", {})

    await _read_bucket.acquire()

    try:
        config = RedditConfig()
        client = _get_praw_client(config)

        # Use PRAW's default subreddits as proxy for trending
        trending = list(client.subreddits.default(limit=25))

        output = "Trending / Default Subreddits:\n"
        output += "=" * 60 + "\n\n"

        for i, sub in enumerate(trending, 1):
            output += f"{i}. r/{sub.display_name} - {sub.subscribers:,} subscribers\n"
            output += f"   {sub.public_description[:100]}\n\n"

        _log_tool_result("get_trending_subreddits", f"Retrieved {len(trending)} subreddits", True)
        return output

    except Exception as e:
        _log_tool_result("get_trending_subreddits", str(e), False)
        return f"Error getting trending subreddits: {e}"


async def get_user_karma_tool(ctx: RunContext) -> Dict[str, Any]:
    """Get current user's karma breakdown.

    Returns:
        Dict with success, data, message keys
    """
    if tracer:
        with tracer.start_as_current_span("get_user_karma") as span:
            span.set_attribute("tool", "get_user_karma")

    _log_tool_call("get_user_karma", {})

    try:
        config = RedditConfig()
        client = _get_praw_client(config)
        me = client.user.me()

        link_karma = getattr(me, "link_karma", 0)
        comment_karma = getattr(me, "comment_karma", 0)

        # Update state
        state = load_reddit_state()
        state.link_karma = link_karma
        state.comment_karma = comment_karma
        save_reddit_state(state)

        output = f"Karma Breakdown for /u/{me.name}:\n"
        output += f"  Link Karma: {link_karma:,}\n"
        output += f"  Comment Karma: {comment_karma:,}\n"
        output += f"  Total: {link_karma + comment_karma:,}"

        _log_tool_result("get_user_karma", f"Link: {link_karma}, Comment: {comment_karma}", True)
        return {
            "success": True,
            "data": {"link_karma": link_karma, "comment_karma": comment_karma, "username": me.name},
            "message": output,
        }

    except Exception as e:
        _log_tool_result("get_user_karma", str(e), False)
        return {"success": False, "data": None, "message": f"Error getting karma: {e}"}


async def reddit_check_visibility_tool(ctx: RunContext, post_id: str) -> Dict[str, Any]:
    """Check if a post is visible (not shadowbanned / removed).

    Args:
        post_id: Reddit post ID to check

    Returns:
        Dict with success, data (visible, shadowban_detected), message
    """
    if tracer:
        with tracer.start_as_current_span("check_visibility") as span:
            span.set_attribute("post_id", post_id)

    _log_tool_call("check_visibility", {"post_id": post_id})

    try:
        config = RedditConfig()
        client = _get_praw_client(config)

        # Wait a bit for indexing
        await asyncio.sleep(5)

        submission = client.submission(id=post_id)

        # Force refresh
        submission._fetch()

        # Heuristic: if author is None and subreddit is known, likely removed/shadowbanned
        visible = submission.author is not None and not submission.removed_by_category
        shadowban_detected = False

        if not visible:
            # Try to find via search as secondary check
            try:
                results = list(client.subreddit("all").search(f"id:{post_id}", limit=1))
                if not results:
                    shadowban_detected = True
            except Exception:
                shadowban_detected = True

        if visible:
            _log_tool_result("check_visibility", f"Post {post_id} is visible", True)
            return {
                "success": True,
                "data": {"visible": True, "shadowban_detected": False},
                "message": f"Post {post_id} is visible and indexed.",
            }
        else:
            _log_tool_result("check_visibility", f"Post {post_id} not visible - possible shadowban", False)
            return {
                "success": True,
                "data": {"visible": False, "shadowban_detected": shadowban_detected},
                "message": f"Post {post_id} is not visible. Possible shadowban or removal detected.",
            }

    except Exception as e:
        _log_tool_result("check_visibility", str(e), False)
        return {"success": False, "data": None, "message": f"Error checking visibility: {e}"}


async def delete_submission_tool(ctx: RunContext, post_id: str) -> Dict[str, Any]:
    """Delete a Reddit submission.

    Args:
        post_id: Reddit post ID to delete

    Returns:
        Dict with success, data, message keys
    """
    if tracer:
        with tracer.start_as_current_span("delete_submission") as span:
            span.set_attribute("post_id", post_id)

    _log_tool_call("delete_submission", {"post_id": post_id})

    await _post_bucket.acquire()

    try:
        config = RedditConfig()
        client = _get_praw_client(config)

        submission = client.submission(id=post_id)
        submission.delete()

        # Remove from recent posts
        state = load_reddit_state()
        state.recent_submissions = [s for s in state.recent_submissions if s.get("id") != post_id]
        save_reddit_state(state)

        _log_tool_result("delete_submission", f"Deleted {post_id}", True)
        return {"success": True, "data": {"deleted": True}, "message": f"Deleted submission {post_id}"}

    except Exception as e:
        _log_tool_result("delete_submission", str(e), False)
        return {"success": False, "data": None, "message": f"Error deleting submission: {e}"}


async def get_inbox_tool(ctx: RunContext, limit: int = 20) -> str:
    """Get Reddit inbox messages and mentions.

    Args:
        limit: Number of items to retrieve

    Returns:
        Inbox contents
    """
    if tracer:
        with tracer.start_as_current_span("get_inbox") as span:
            span.set_attribute("limit", limit)

    _log_tool_call("get_inbox", {"limit": limit})

    await _read_bucket.acquire()

    try:
        config = RedditConfig()
        client = _get_praw_client(config)

        inbox = client.inbox
        messages = []

        for i, item in enumerate(inbox.unread(limit=min(limit, 50))):
            msg_type = "message" if hasattr(item, "subject") else "comment_reply"
            author = getattr(item, "author", None)
            author_name = author.name if author else "(deleted)"
            body = getattr(item, "body", getattr(item, "message", ""))
            subject = getattr(item, "subject", "(no subject)")

            messages.append({
                "type": msg_type,
                "author": author_name,
                "subject": subject,
                "body": body[:200],
                "id": item.id,
            })

        output = f"Unread Inbox ({len(messages)} items):\n"
        output += "=" * 60 + "\n\n"

        for i, msg in enumerate(messages, 1):
            output += f"{i}. [{msg['type']}] from /u/{msg['author']}\n"
            output += f"   Subject: {msg['subject']}\n"
            output += f"   {msg['body'][:150]}...\n" if len(msg['body']) > 150 else f"   {msg['body']}\n"
            output += f"   ID: {msg['id']}\n\n"

        _log_tool_result("get_inbox", f"Retrieved {len(messages)} items", True)
        return output

    except Exception as e:
        _log_tool_result("get_inbox", str(e), False)
        return f"Error getting inbox: {e}"
