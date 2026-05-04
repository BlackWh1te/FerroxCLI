"""Browser-based X (Twitter) login using Playwright with full anti-bot stealth.

Opens a visible browser window that masquerades as a real human Chrome
session so X/Twitter bot detection does not block login. After successful
login, session cookies are captured and saved for twikit reuse.

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
    """Return the canonical path for saved X session cookies."""
    return Path.home() / ".ferrox" / "twikit_cookies.json"


def get_user_data_dir() -> Path:
    """Persistent Chromium profile so X sees a returning user."""
    return Path.home() / ".ferrox" / "browser_profile"


# ---------------------------------------------------------------------------
# Re-export shared helpers with X-specific defaults
# ---------------------------------------------------------------------------

_save_cookies_playwright_format = save_cookies_playwright_format
_convert_to_httpx_cookiejar = convert_to_httpx_cookiejar


def has_saved_x_session() -> bool:
    """Return True if a saved X browser session exists."""
    cookies = load_browser_cookies(get_cookie_path())
    return bool(cookies)


def clear_x_session() -> None:
    """Delete any saved X session cookies."""
    path = get_cookie_path()
    if path.exists():
        path.unlink()
    jar_path = path.with_suffix(".jar.json")
    if jar_path.exists():
        jar_path.unlink()


# ---------------------------------------------------------------------------
# Main async browser-login flow
# ---------------------------------------------------------------------------


def _is_x_logged_in(url: str) -> bool:
    lowered = url.lower()
    return (
        "x.com/home" in lowered
        or "twitter.com/home" in lowered
        or ("x.com/" in lowered and "/i/flow/login" not in lowered)
    )


async def x_login_via_browser(timeout_seconds: int = 180) -> str:
    """Open a stealth browser for X login and save session cookies."""
    config = BrowserLoginConfig(
        cookie_path=get_cookie_path(),
        profile_dir=get_user_data_dir(),
        login_url="https://x.com/i/flow/login",
        is_logged_in=_is_x_logged_in,
        title="X Browser Login (Stealth Mode)",
        fallback_cmd="/social login",
        start_cmd="/social start",
        key_cookie_names={"auth_token", "ct0", "twid", "guest_id"},
        timeout_seconds=timeout_seconds,
    )
    return await run_browser_login(config)
