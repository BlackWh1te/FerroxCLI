"""Browser-based X (Twitter) login using Playwright.

Opens a visible browser window so the user can log in to X naturally
(including 2FA and CAPTCHA). After successful login, captures session
cookies and saves them for twikit reuse. No username or password is ever
stored — only session cookies.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional


def get_cookie_path() -> Path:
    """Return the canonical path for saved X session cookies."""
    return Path.home() / ".ferrox" / "twikit_cookies.json"


def _save_cookies_playwright_format(cookies: list[dict], path: Path) -> None:
    """Save cookies in Playwright JSON format (most compatible)."""
    data = {
        "format": "playwright",
        "saved_at": datetime.now().isoformat(),
        "cookies": cookies,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _convert_to_httpx_cookiejar(cookies: list[dict]) -> dict:
    """Convert Playwright cookies to a simple name->value dict.

    Twikit's Client.load_cookies() often expects a flat dict or
    a JSON serialisable cookie jar. We provide both formats.
    """
    jar = {}
    for c in cookies:
        name = c.get("name", "")
        value = c.get("value", "")
        if name:
            jar[name] = value
    return jar


def load_browser_cookies() -> Optional[list[dict]]:
    """Load previously saved browser cookies if they exist.

    Returns:
        List of cookie dicts or None if no saved session.
    """
    path = get_cookie_path()
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Handle both "playwright" format and raw list
        if isinstance(data, dict) and "cookies" in data:
            return data["cookies"]
        if isinstance(data, list):
            return data
        return None
    except Exception:
        return None


def x_login_via_browser(timeout_seconds: int = 180) -> str:
    """Open a visible browser for X login and save session cookies.

    The user completes login manually in the opened Chromium window
    (including any 2FA or CAPTCHA). Once the URL changes to the X home
    timeline we capture all cookies and persist them so twikit can reuse
    the session without ever storing a password.

    Args:
        timeout_seconds: Maximum seconds to wait for login completion.

    Returns:
        Human-readable success or error message.
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        return (
            "Playwright not installed.\n"
            "Install it with:\n"
            "  pip install playwright\n"
            "  playwright install chromium\n"
            "Or use '/social login' for manual username/password entry."
        )

    cookie_path = get_cookie_path()

    with sync_playwright() as p:
        # Visible browser so the user can interact naturally
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        try:
            page.goto(
                "https://x.com/i/flow/login",
                wait_until="domcontentloaded",
                timeout=30000,
            )

            # Print instructions via stdout (we're outside the rich console here)
            print("\n" + "=" * 56)
            print("  🐦  X Browser Login")
            print("=" * 56)
            print("  A browser window has opened.")
            print("  Please log in to X normally:")
            print("    1. Enter your username/email + password")
            print("    2. Complete any 2FA / CAPTCHA if shown")
            print("    3. Wait for the home timeline to load")
            print(f"\n  Timeout: {timeout_seconds} seconds")
            print("=" * 56 + "\n")

            # Detect successful login by waiting for the home timeline URL.
            # X redirects to /home after login. We accept either x.com or
            # twitter.com domains in case of redirects.
            def is_logged_in(url: str) -> bool:
                lowered = url.lower()
                return (
                    "x.com/home" in lowered
                    or "twitter.com/home" in lowered
                    or ("x.com/" in lowered and "/i/flow/login" not in lowered)
                )

            page.wait_for_url(is_logged_in, timeout=timeout_seconds * 1000)

            print("  ✅ Login detected! Capturing session cookies...\n")

            # Capture all cookies from the browser context
            cookies = context.cookies()

            if not cookies:
                return "No cookies captured — login may have failed."

            # Save in Playwright JSON format (most compatible)
            _save_cookies_playwright_format(cookies, cookie_path)

            # Also try to save a simple httpx jar alongside it
            jar_path = cookie_path.with_suffix(".jar.json")
            try:
                jar = _convert_to_httpx_cookiejar(cookies)
                with open(jar_path, "w", encoding="utf-8") as f:
                    json.dump(jar, f, indent=2)
            except Exception:
                pass  # jar is optional

            # Report key cookies for user confidence
            key_names = {"auth_token", "ct0", "twid", "guest_id"}
            found = {c["name"] for c in cookies if c["name"] in key_names}
            print(f"  Captured {len(cookies)} cookies")
            print(f"  Key tokens: {', '.join(sorted(found)) or 'none recognised'}")
            print(f"  Saved to: {cookie_path}")
            print("\n  You can now run '/social start' to use the X Bot.")
            print("=" * 56 + "\n")

            return (
                f"✅ X session saved ({len(cookies)} cookies). "
                f"Run '/social start' to begin."
            )

        except PWTimeout:
            return (
                "❌ Login timed out. The browser window closed.\n"
                "Tips:\n"
                "  - Make sure you entered your credentials\n"
                "  - 2FA / CAPTCHA can take extra time\n"
                "  - Try again with a longer timeout"
            )
        except Exception as exc:
            return f"❌ Browser login error: {exc}"
        finally:
            browser.close()


def has_saved_x_session() -> bool:
    """Return True if a saved X browser session exists and is non-empty."""
    cookies = load_browser_cookies()
    return bool(cookies)


def clear_x_session() -> None:
    """Delete any saved X session cookies."""
    path = get_cookie_path()
    if path.exists():
        path.unlink()
    jar_path = path.with_suffix(".jar.json")
    if jar_path.exists():
        jar_path.unlink()
