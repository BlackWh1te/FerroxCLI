"""Browser-based Reddit login using Playwright with full anti-bot stealth.

Opens a visible browser window that masquerades as a real human Chrome
session so Reddit bot detection does not block login. After successful
login, session cookies are captured and saved for PRAW reuse or direct
browser automation.

No username or password is ever stored — only session cookies.
"""

from __future__ import annotations

from pathlib import Path

from ferrox.utils.browser_login import (
    BrowserLoginConfig,
    convert_to_httpx_cookiejar,
    load_browser_cookies,
    run_browser_login,
    save_cookies_playwright_format,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def get_cookie_path() -> Path:
    """Return the canonical path for saved Reddit session cookies."""
    return Path.home() / ".ferrox" / "reddit_cookies.json"


def get_user_data_dir() -> Path:
    """Persistent Chromium profile so Reddit sees a returning user."""
    return Path.home() / ".ferrox" / "reddit_browser_profile"


# ---------------------------------------------------------------------------
# Re-export shared helpers with Reddit-specific defaults
# ---------------------------------------------------------------------------

_save_cookies_playwright_format = save_cookies_playwright_format
_convert_to_httpx_cookiejar = convert_to_httpx_cookiejar


def has_saved_reddit_session() -> bool:
    """Return True if a saved Reddit browser session exists."""
    cookies = load_browser_cookies(get_cookie_path())
    return bool(cookies)


def clear_reddit_session() -> None:
    """Delete any saved Reddit session cookies."""
    path = get_cookie_path()
    if path.exists():
        path.unlink()
    jar_path = path.with_suffix(".jar.json")
    if jar_path.exists():
        jar_path.unlink()


# ---------------------------------------------------------------------------
# Main async browser-login flow
# ---------------------------------------------------------------------------


def _is_reddit_logged_in(url: str) -> bool:
    lowered = url.lower()
    return (
        "reddit.com/login" not in lowered
        and "reddit.com/account" not in lowered
        and "reddit.com/register" not in lowered
    )


async def reddit_login_via_browser(timeout_seconds: int = 180) -> str:
    """Open a stealth browser for Reddit login and save session cookies."""
    config = BrowserLoginConfig(
        cookie_path=get_cookie_path(),
        profile_dir=get_user_data_dir(),
        login_url="https://www.reddit.com/login/",
        is_logged_in=_is_reddit_logged_in,
        title="Reddit Browser Login (Stealth Mode)",
        fallback_cmd="/reddit login",
        start_cmd="/reddit start",
        key_cookie_names={"reddit_session", "token_v2", "session_tracker", "loid"},
        timeout_seconds=timeout_seconds,
    )
    return await run_browser_login(config)
