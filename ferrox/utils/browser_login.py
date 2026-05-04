"""Shared browser-login utilities for social platform logins.

Anti-bot evasion patches, cookie helpers, and a generic Playwright browser-login
flow used by both Reddit and X/Twitter login modules.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

# ---------------------------------------------------------------------------
# Cookie helpers (sync — no Playwright involved)
# ---------------------------------------------------------------------------


def save_cookies_playwright_format(cookies: list[dict], path: Path) -> None:
    """Save cookies in Playwright JSON format."""
    data = {
        "format": "playwright",
        "saved_at": __import__("datetime").datetime.now().isoformat(),
        "cookies": cookies,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def convert_to_httpx_cookiejar(cookies: list[dict]) -> dict:
    """Convert Playwright cookies to a simple name->value dict."""
    jar: dict[str, str] = {}
    for c in cookies:
        name = c.get("name", "")
        value = c.get("value", "")
        if name:
            jar[name] = value
    return jar


def load_browser_cookies(path: Path) -> list[dict] | None:
    """Load previously saved browser cookies if they exist."""
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "cookies" in data:
            return data["cookies"]
        if isinstance(data, list):
            return data
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Anti-bot evasion scripts (evaluated via CDP before any page loads)
# ---------------------------------------------------------------------------

_WEBDRIVER_PATCH = """
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined
});
"""

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

_PERMISSIONS_PATCH = """
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : originalQuery(parameters)
);
"""

_WEBGL_PATCH = """
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) return 'Intel Inc.';
    if (parameter === 37446) return 'Intel Iris OpenGL Engine';
    return getParameter(parameter);
};
"""

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

_IFRAME_PATCH = """
const originalAttachShadow = Element.prototype.attachShadow;
Element.prototype.attachShadow = function(init) {
    if (init && init.mode === 'closed') init.mode = 'open';
    return originalAttachShadow.call(this, init);
};
"""

_WINDOW_PATCH = """
Object.defineProperty(window, 'outerWidth', { get: () => window.innerWidth });
Object.defineProperty(window, 'outerHeight', { get: () => window.innerHeight + 80 });
"""

ALL_PATCHES = [
    _WEBDRIVER_PATCH,
    _CHROME_FINGERPRINT_PATCH,
    _PERMISSIONS_PATCH,
    _WEBGL_PATCH,
    _CHROME_RUNTIME_PATCH,
    _IFRAME_PATCH,
    _WINDOW_PATCH,
]

# ---------------------------------------------------------------------------
# Browser launch configuration (shared)
# ---------------------------------------------------------------------------

BROWSER_LAUNCH_ARGS = [
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
]

BROWSER_HTTP_HEADERS = {
    "Accept-Language": "en-US,en;q=0.9",
    "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "DNT": "1",
    "Upgrade-Insecure-Requests": "1",
}

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# ---------------------------------------------------------------------------
# Generic browser-login flow
# ---------------------------------------------------------------------------


@dataclass
class BrowserLoginConfig:
    """Platform-specific configuration for a browser-login flow."""

    cookie_path: Path
    profile_dir: Path
    login_url: str
    is_logged_in: Callable[[str], bool]
    title: str
    fallback_cmd: str
    start_cmd: str
    key_cookie_names: set[str]
    timeout_seconds: int = 180


async def run_browser_login(config: BrowserLoginConfig) -> str:  # noqa: C901
    """Open a stealth browser, wait for login, and save session cookies.

    The browser is launched with:
    - Persistent user-data dir (looks like a returning user)
    - CDP evasion scripts (removes webdriver, patches navigator, etc.)
    - Realistic viewport, locale, timezone, color scheme
    - Human-like user-agent and Accept-Language headers

    Once the user completes login (including 2FA / CAPTCHA) we detect
    the redirect away from the login page, capture cookies, and persist them.
    """
    try:
        from playwright.async_api import TimeoutError as PWTimeout
        from playwright.async_api import async_playwright
    except ImportError:
        return (
            "Playwright not installed.\n"
            "Install it with:\n"
            "  pip install playwright\n"
            "  playwright install chromium\n"
            f"Or use '{config.fallback_cmd}' for manual username/password entry."
        )

    config.profile_dir.mkdir(parents=True, exist_ok=True)

    # ---- try playwright-stealth if available (community package) ----
    stealth_available = False
    try:
        from playwright_stealth import stealth_async  # type: ignore[import-untyped]
        stealth_available = True
    except Exception:  # nosec: B110 — intentional suppression
        pass

    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=str(config.profile_dir),
            headless=False,
            viewport={"width": 1366, "height": 768},
            locale="en-US",
            timezone_id="America/New_York",
            color_scheme="light",
            geolocation={"latitude": 40.7128, "longitude": -74.0060},
            permissions=["geolocation"],
            bypass_csp=True,
            args=BROWSER_LAUNCH_ARGS,
            extra_http_headers=BROWSER_HTTP_HEADERS,
            user_agent=BROWSER_USER_AGENT,
        )

        page = await browser.new_page()

        # ---- CDP evasion: inject scripts BEFORE any navigation ----
        for script in ALL_PATCHES:
            await page.add_init_script(script)

        # ---- Optional: apply playwright-stealth on top ----
        if stealth_available:
            with contextlib.suppress(Exception):
                await stealth_async(page)

        try:
            await page.goto(
                config.login_url,
                wait_until="domcontentloaded",
                timeout=30000,
            )

            print("\n" + "=" * 60)
            print(f"  {config.title}")
            print("=" * 60)
            print("  A Chromium window has opened.")
            print("  It looks like a normal Chrome browser to the target site.")
            print("  Please log in normally:")
            print("    1. Enter your username/email + password")
            print("    2. Complete any 2FA / CAPTCHA if shown")
            print("    3. Wait for the home timeline / feed to load")
            print(f"\n  Timeout: {config.timeout_seconds} seconds")
            print("=" * 60 + "\n")

            await page.wait_for_url(
                config.is_logged_in, timeout=config.timeout_seconds * 1000
            )

            print("  Login detected! Capturing session cookies...\n")

            # Small random wait so cookie writes settle
            await asyncio.sleep(random.uniform(1.0, 2.5))  # nosec: B311

            cookies = await browser.cookies()

            if not cookies:
                return "No cookies captured — login may have failed."

            save_cookies_playwright_format(cookies, config.cookie_path)

            # Also save a flat jar alongside
            jar_path = config.cookie_path.with_suffix(".jar.json")
            try:
                jar = convert_to_httpx_cookiejar(cookies)
                with open(jar_path, "w", encoding="utf-8") as f:
                    json.dump(jar, f, indent=2)
            except Exception:  # nosec: B110 — intentional suppression
                pass

            found = {c["name"] for c in cookies if c["name"] in config.key_cookie_names}
            print(f"  Captured {len(cookies)} cookies")
            print(
                f"  Key tokens: {', '.join(sorted(found)) or 'none recognised'}"
            )
            print(f"  Saved to: {config.cookie_path}")
            print(f"\n  You can now run '{config.start_cmd}' to use the Bot.")
            print("=" * 60 + "\n")

            return (
                f"Session saved ({len(cookies)} cookies). "
                f"Run '{config.start_cmd}' to begin."
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
