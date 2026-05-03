"""Browser-based Reddit login using Playwright with full anti-bot stealth.

Opens a visible browser window that masquerades as a real human Chrome
session so Reddit bot detection does not block login. After successful
login, session cookies are captured and saved for PRAW reuse or direct
browser automation.

No username or password is ever stored — only session cookies.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
from datetime import datetime
from pathlib import Path
from typing import Optional

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
# Cookie helpers (sync — no Playwright involved)
# ---------------------------------------------------------------------------

def _save_cookies_playwright_format(cookies: list[dict], path: Path) -> None:
    """Save cookies in Playwright JSON format."""
    data = {
        "format": "playwright",
        "saved_at": datetime.now().isoformat(),
        "cookies": cookies,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _convert_to_httpx_cookiejar(cookies: list[dict]) -> dict:
    """Convert Playwright cookies to a simple name->value dict."""
    jar: dict[str, str] = {}
    for c in cookies:
        name = c.get("name", "")
        value = c.get("value", "")
        if name:
            jar[name] = value
    return jar


def load_browser_cookies() -> Optional[list[dict]]:
    """Load previously saved browser cookies if they exist."""
    path = get_cookie_path()
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "cookies" in data:
            return data["cookies"]
        if isinstance(data, list):
            return data
        return None
    except Exception:
        return None


def has_saved_reddit_session() -> bool:
    """Return True if a saved Reddit browser session exists."""
    cookies = load_browser_cookies()
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
# Anti-bot evasion scripts (evaluated via CDP before any page loads)
# ---------------------------------------------------------------------------

# Remove the tell-tale automation flag.
_WEBDRIVER_PATCH = """
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined
});
"""

# Chrome plugins / mime-types should look like a real install.
_CHROME_FINGERPRINT_PATCH = """
const makeArray = (len) => {
    const arr = [];
    for (let i = 0; i < len; i++) arr.push(i);
    return arr;
};

// Fake plugins
Object.defineProperty(navigator, 'plugins', {
    get: () => [
        {
            0: {type: "application/x-google-chrome-pdf", suffixes: "pdf", description: "Portable Document Format", enabledPlugin: null},
            description: "Portable Document Format",
            filename: "internal-pdf-viewer",
            length: 1,
            name: "Chrome PDF Plugin"
        },
        {
            0: {type: "application/pdf", suffixes: "pdf", description: "Portable Document Format", enabledPlugin: null},
            description: "Portable Document Format",
            filename: "mhjfbmdgcfjbbpaeojofohoefgiehjai",
            length: 1,
            name: "Chrome PDF Viewer"
        },
        {
            0: {type: "application/x-nacl", suffixes: "", description: "Native Client module", enabledPlugin: null},
            description: "Native Client module",
            filename: "internal-nacl-plugin",
            length: 2,
            name: "Native Client"
        }
    ]
});

// Fake mime-types
Object.defineProperty(navigator, 'mimeTypes', {
    get: () => [
        {type: "application/x-google-chrome-pdf", suffixes: "pdf", description: "Portable Document Format", enabledPlugin: null},
        {type: "application/pdf", suffixes: "pdf", description: "Portable Document Format", enabledPlugin: null},
        {type: "application/x-nacl", suffixes: "", description: "Native Client module", enabledPlugin: null},
        {type: "application/x-pnacl", suffixes: "", description: "Portable Native Client module", enabledPlugin: null}
    ]
});

// Languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en']
});

// Platform
Object.defineProperty(navigator, 'platform', {
    get: () => 'Win32'
});
"""

# Patch Notification / Permissions API so headless check fails.
_PERMISSIONS_PATCH = """
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : originalQuery(parameters)
);
"""

# Patch WebGL vendor / renderer.
_WEBGL_PATCH = """
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) return 'Intel Inc.';
    if (parameter === 37446) return 'Intel Iris OpenGL Engine';
    return getParameter(parameter);
};
"""

# Hide Chrome runtime.
_CHROME_RUNTIME_PATCH = """
window.chrome = {
    runtime: {
        OnInstalledReason: {CHROME_UPDATE: "chrome_update", SHARED_MODULE_UPDATE: "shared_module_update", INSTALL: "install", UPDATE: "update"},
        OnRestartRequiredReason: {APP_UPDATE: "app_update", OS_UPDATE: "os_update", PERIODIC: "periodic"},
        PlatformArch: {ARM: "arm", ARM64: "arm64", MIPS: "mips", MIPS64: "mips64", MIPS64EL: "mips64el", MIPSel: "mipsel", X86_32: "x86-32", X86_64: "x86-64"},
        PlatformNaclArch: {ARM: "arm", MIPS: "mips", MIPS64: "mips64", MIPS64EL: "mips64el", MIPSel: "mipsel", X86_32: "x86-32", X86_64: "x86-64"},
        PlatformOs: {ANDROID: "android", CROS: "cros", LINUX: "linux", MAC: "mac", OPENBSD: "openbsd", WIN: "win"},
        RequestUpdateCheckStatus: {NO_UPDATE: "no_update", THROTTLED: "throttled", UPDATE_AVAILABLE: "update_available"}
    }
};
"""

# Hide automation from iframe contentWindow (advanced).
_IFRAME_PATCH = """
const originalAttachShadow = Element.prototype.attachShadow;
Element.prototype.attachShadow = function(init) {
    if (init && init.mode === 'closed') init.mode = 'open';
    return originalAttachShadow.call(this, init);
};
"""

# Prevent detection via window.outerWidth / outerHeight mismatch.
_WINDOW_PATCH = """
Object.defineProperty(window, 'outerWidth', { get: () => window.innerWidth });
Object.defineProperty(window, 'outerHeight', { get: () => window.innerHeight + 80 });
"""


_ALL_PATCHES = [
    _WEBDRIVER_PATCH,
    _CHROME_FINGERPRINT_PATCH,
    _PERMISSIONS_PATCH,
    _WEBGL_PATCH,
    _CHROME_RUNTIME_PATCH,
    _IFRAME_PATCH,
    _WINDOW_PATCH,
]


# ---------------------------------------------------------------------------
# Main async browser-login flow
# ---------------------------------------------------------------------------

async def reddit_login_via_browser(timeout_seconds: int = 180) -> str:
    """Open a stealth browser for Reddit login and save session cookies.

    The browser is launched with:
    - Persistent user-data dir (looks like a returning user)
    - CDP evasion scripts (removes webdriver, patches navigator, etc.)
    - Realistic viewport, locale, timezone, color scheme
    - Human-like user-agent and Accept-Language headers

    Once the user completes login (including 2FA / CAPTCHA) we detect
    the redirect away from the login page, capture cookies, and persist them.
    """
    try:
        from playwright.async_api import (
            async_playwright,
            TimeoutError as PWTimeout,
        )
    except ImportError:
        return (
            "Playwright not installed.\n"
            "Install it with:\n"
            "  pip install playwright\n"
            "  playwright install chromium\n"
            "Or use '/reddit login' for manual username/password entry."
        )

    cookie_path = get_cookie_path()
    profile_dir = get_user_data_dir()
    profile_dir.mkdir(parents=True, exist_ok=True)

    # ---- try playwright-stealth if available (community package) ----
    stealth_available = False
    try:
        from playwright_stealth import stealth_async  # type: ignore[import-untyped]
        stealth_available = True
    except Exception:
        pass

    async with async_playwright() as p:
        # Launch with persistent profile AND extra args to mask automation.
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,                         # visible browser = human
            viewport={"width": 1366, "height": 768},  # common laptop res
            locale="en-US",
            timezone_id="America/New_York",
            color_scheme="light",
            geolocation={"latitude": 40.7128, "longitude": -74.0060},
            permissions=["geolocation"],
            bypass_csp=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--window-size=1366,768",
                "--window-position=0,0",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-accelerated-2d-canvas",
                "--disable-gpu",
                "--hide-scrollbars",
                "--disable-notifications",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-breakpad",
                "--disable-component-update",
                "--disable-default-apps",
                "--disable-features=TranslateUI",
                "--enable-automation=false",
            ],
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "DNT": "1",
                "Upgrade-Insecure-Requests": "1",
            },
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )

        # Create a new page inside the persistent context
        page = await browser.new_page()

        # ---- CDP evasion: inject scripts BEFORE any navigation ----
        for script in _ALL_PATCHES:
            await page.add_init_script(script)

        # ---- Optional: apply playwright-stealth on top ----
        if stealth_available:
            try:
                await stealth_async(page)
            except Exception:
                pass  # manual patches above already cover the basics

        try:
            await page.goto(
                "https://www.reddit.com/login/",
                wait_until="domcontentloaded",
                timeout=30000,
            )

            # Print instructions via stdout
            print("\n" + "=" * 60)
            print("  Reddit Browser Login (Stealth Mode)")
            print("=" * 60)
            print("  A Chromium window has opened.")
            print("  It looks like a normal Chrome browser to Reddit.")
            print("  Please log in to Reddit normally:")
            print("    1. Enter your username + password")
            print("    2. Complete any 2FA / CAPTCHA if shown")
            print("    3. Wait for the feed / homepage to load")
            print(f"\n  Timeout: {timeout_seconds} seconds")
            print("=" * 60 + "\n")

            # Detect successful login: wait for URL that is NOT login.
            def _is_logged_in(url: str) -> bool:
                lowered = url.lower()
                return (
                    "reddit.com/login" not in lowered
                    and "reddit.com/account" not in lowered
                    and "reddit.com/register" not in lowered
                )

            await page.wait_for_url(_is_logged_in, timeout=timeout_seconds * 1000)

            print("  Login detected! Capturing session cookies...\n")

            # Small random wait so cookie writes settle
            await asyncio.sleep(random.uniform(1.0, 2.5))

            # Capture cookies from the persistent browser context
            cookies = await browser.cookies()

            if not cookies:
                return "No cookies captured — login may have failed."

            _save_cookies_playwright_format(cookies, cookie_path)

            # Also save a flat jar alongside
            jar_path = cookie_path.with_suffix(".jar.json")
            try:
                jar = _convert_to_httpx_cookiejar(cookies)
                with open(jar_path, "w", encoding="utf-8") as f:
                    json.dump(jar, f, indent=2)
            except Exception:
                pass

            # Report key cookies for confidence
            key_names = {"reddit_session", "token_v2", "session_tracker", "loid"}
            found = {c["name"] for c in cookies if c["name"] in key_names}
            print(f"  Captured {len(cookies)} cookies")
            print(
                f"  Key tokens: {', '.join(sorted(found)) or 'none recognised'}"
            )
            print(f"  Saved to: {cookie_path}")
            print("\n  You can now run '/reddit start' to use the Reddit Bot.")
            print("=" * 60 + "\n")

            return (
                f"Reddit session saved ({len(cookies)} cookies). "
                f"Run '/reddit start' to begin."
            )

        except PWTimeout:
            return (
                "Login timed out. The browser window closed.\n"
                "Tips:\n"
                "  - Make sure you entered your credentials\n"
                "  - 2FA / CAPTCHA can take extra time\n"
                "  - Try again with a longer timeout"
            )
        except Exception as exc:
            return f"Browser login error: {exc}"
        finally:
            await browser.close()
