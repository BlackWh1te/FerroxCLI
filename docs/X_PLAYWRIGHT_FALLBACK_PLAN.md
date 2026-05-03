# X Playwright Anti-Detection Fallback Plan

## Problem Statement

Twikit and tweety-ns are in a constant cat-and-mouse game with X's internal API:
- Twikit 2.3.3: Fails on encrypted response parsing ("KEY_BYTE indices")
- Tweety-ns 2.4.1: Fails on rotated GraphQL endpoint hashes ("Page not Found")
- X rotates operation IDs, adds Cloudflare challenges, and obfuscates responses weekly

**Playwright fallback** bypasses ALL of this by using X's actual web UI — just like a real human with a browser.

---

## Architecture

```
User asks: "post a tweet about AI"
    ↓
FerroxAgent → check_account_health_tool()
    ↓
_try_twikit_first() → FAILS (API broken)
    ↓
_playwright_fallback() → SUCCESS
    ↓
Launch stealth Chromium → inject cookies → navigate x.com
    ↓
Click "Post" → type text → click "Post" button
    ↓
Read confirmation → extract tweet URL → return to user
```

---

## Module Structure

```
ferrox/agent/tools_social.py          ← existing, add fallback logic
ferrox/agent/x_playwright_fallback.py  ← NEW: all Playwright automation
ferrox/agent/x_stealth.py              ← NEW: anti-detection utilities
```

---

## 1. Anti-Detection Strategy (Critical)

### 1.1 Browser Fingerprint Evasion

X detects automation via:
- `navigator.webdriver = true` (headless browser flag)
- `window.chrome` missing (headless lacks Chrome APIs)
- Plugins list too short (real Chrome has PDF, Native Client, etc.)
- `navigator.languages` revealing headless locale
- User-Agent mismatch with platform

**Mitigation:**

```python
# playwright-stealth or manual overrides
await page.evaluate("""
    // Hide automation
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    window.chrome = { runtime: {} };
    
    // Fake plugins
    Object.defineProperty(navigator, 'plugins', {
        get: () => [
            {name: "Chrome PDF Plugin", filename: "internal-pdf-viewer"},
            {name: "Native Client", filename: "internal-nacl-plugin"},
            {name: "Widevine Content Decryption Module", filename: "widevinecdmadapter.dll"}
        ]
    });
    
    // Languages matching user's real browser
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-US', 'en']  // or user's actual from cookies
    });
""")
```

### 1.2 Playwright Stealth Launch Args

```python
browser = await p.chromium.launch(
    headless=False,  # HEADED mode for X — headless is INSTANTLY flagged by Cloudflare
    args=[
        "--disable-blink-features=AutomationControlled",
        "--disable-web-security",
        "--disable-features=IsolateOrigins,site-per-process",
        "--disable-site-isolation-trials",
        "--disable-features=BlockInsecurePrivateNetworkRequests",
        "--window-size=1920,1080",
        "--start-maximized",
        "--no-sandbox",  # Windows safe, Linux needs care
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-accelerated-2d-canvas",
        "--disable-gpu",
        "--hide-scrollbars",
        "--mute-audio",
        "--disable-background-networking",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-breakpad",
        "--disable-component-update",
        "--disable-default-apps",
        "--disable-extensions",
        "--disable-features=TranslateUI",
        "--disable-hang-monitor",
        "--disable-ipc-flooding-protection",
        "--disable-popup-blocking",
        "--disable-prompt-on-repost",
        "--disable-renderer-backgrounding",
        "--force-color-profile=srgb",
        "--metrics-recording-only",
        "--no-first-run",
        "--safebrowsing-disable-auto-update",
        "--password-store=basic",
        "--use-mock-keychain",
    ]
)
```

**Key insight:** `headless=False` (visible browser) is REQUIRED for X. Cloudflare's JS challenge detects headless Chromium and blocks it. The user must see the browser.

### 1.3 Human-Like Behavior Patterns

**Anti-bot detection looks for:**
- Instant typing (humans type 150-400ms per key)
- Instant clicking (humans take 200-800ms to move mouse)
- No scrolling before action (humans scroll to find the button)
- Same timing every action (robots are perfectly periodic)
- No mouse movement (bots teleport the cursor)

**Implementation:**

```python
import random
import asyncio
from playwright.async_api import Page

class HumanBehavior:
    """Mimics human interaction patterns to evade bot detection."""
    
    @staticmethod
    async def random_delay(min_ms=800, max_ms=2500):
        """Pause for random time — humans don't act instantly."""
        await asyncio.sleep(random.uniform(min_ms, max_ms) / 1000)
    
    @staticmethod
    async def type_like_human(page: Page, selector: str, text: str):
        """Type with variable speed, occasional pauses, corrections."""
        for char in text:
            # Human typing speed: 150-400ms per character
            await page.type(selector, char, delay=random.randint(50, 200))
            
            # Occasional pause mid-sentence (thinking)
            if random.random() < 0.05:
                await asyncio.sleep(random.uniform(0.5, 1.5))
        
        # Pause after finishing (reviewing before posting)
        await asyncio.sleep(random.uniform(0.8, 2.0))
    
    @staticmethod
    async def move_mouse_naturally(page: Page, target_selector: str):
        """Move mouse via intermediate points, not instant teleport."""
        # Get current and target positions
        current = await page.evaluate("() => ({x: window.mouseX || 0, y: window.mouseY || 0})")
        target = await page.locator(target_selector).bounding_box()
        
        if target:
            # Move in a slight curve with 2-4 intermediate points
            steps = random.randint(2, 4)
            for i in range(1, steps):
                t = i / steps
                # Add slight curve (bezier-ish)
                offset_x = random.randint(-30, 30)
                offset_y = random.randint(-20, 20)
                x = current['x'] + (target['x'] - current['x']) * t + offset_x
                y = current['y'] + (target['y'] - current['y']) * t + offset_y
                await page.mouse.move(x, y)
                await asyncio.sleep(random.uniform(0.05, 0.15))
    
    @staticmethod
    async def scroll_and_read(page: Page, scroll_pixels: int = 800):
        """Scroll slowly, pausing to 'read' — mimics human browsing."""
        for _ in range(random.randint(2, 5)):
            await page.mouse.wheel(0, random.randint(200, 500))
            await asyncio.sleep(random.uniform(0.3, 0.8))  # "reading"
    
    @staticmethod
    async def click_like_human(page: Page, selector: str):
        """Move to element, hover, pause, then click."""
        await HumanBehavior.move_mouse_naturally(page, selector)
        await asyncio.sleep(random.uniform(0.2, 0.6))  # hover
        await page.locator(selector).click()
        await asyncio.sleep(random.uniform(0.3, 0.7))  # pause after click
```

### 1.4 Session Warmup Protocol

Before ANY action on X, perform a "warmup" that looks like a real user session start:

```python
async def warmup_session(page: Page):
    """Mimics a real user opening X.com after a break."""
    # 1. Navigate to home (not directly to compose)
    await page.goto("https://x.com/home")
    await HumanBehavior.random_delay(2000, 4000)
    
    # 2. Scroll through timeline "reading"
    await HumanBehavior.scroll_and_read(page)
    
    # 3. Maybe like a random tweet (engagement pattern)
    if random.random() < 0.3:
        like_buttons = await page.locator("[data-testid='like']").all()
        if like_buttons:
            await HumanBehavior.click_like_human(page, like_buttons[0])
            await HumanBehavior.random_delay(1000, 2000)
    
    # 4. Now ready for actual task
    await asyncio.sleep(random.uniform(1.0, 2.0))
```

### 1.5 IP / Fingerprint Consistency

- **User-Agent:** Must match the browser that created the cookies. Extract from cookies or use a consistent one.
- **Screen resolution:** Match real monitor (1920x1080 minimum).
- **Timezone:** Must match cookie's timezone / user's location.
- **Language:** Match cookie `lang` value.
- **Color depth:** Real browsers report 24-bit, headless sometimes reports 32-bit.

---

## 2. Implementation: Core Actions

### 2.1 Post a Tweet

```python
async def post_tweet(text: str) -> dict:
    """Post a tweet using Playwright with anti-detection."""
    
    async with async_playwright() as p:
        browser, page = await _launch_stealth_browser(p)
        
        try:
            # Inject cookies first
            await _inject_cookies(page)
            
            # Warmup — look like a real user
            await warmup_session(page)
            
            # Click "Post" button (the blue "Post" in left sidebar)
            # X's selectors change; use multiple fallback strategies
            compose_selectors = [
                '[data-testid="SideNav_NewTweet_Button"]',
                'a[href="/compose/tweet"]',
                'button[aria-label="Post"]',
            ]
            
            for selector in compose_selectors:
                try:
                    await HumanBehavior.click_like_human(page, selector)
                    break
                except:
                    continue
            
            await HumanBehavior.random_delay(800, 1500)
            
            # Find the tweet text input
            input_selectors = [
                '[data-testid="tweetTextarea_0"]',
                '.public-DraftEditor-content',
                'div[contenteditable="true"]',
            ]
            
            for selector in input_selectors:
                try:
                    await HumanBehavior.type_like_human(page, selector, text)
                    break
                except:
                    continue
            
            await HumanBehavior.random_delay(1000, 2000)
            
            # Click the "Post" button in the modal
            post_button_selectors = [
                '[data-testid="tweetButton"]',
                'button[data-testid="tweetButtonInline"]',
            ]
            
            for selector in post_button_selectors:
                try:
                    await HumanBehavior.click_like_human(page, selector)
                    break
                except:
                    continue
            
            # Wait for post to appear on timeline
            await page.wait_for_timeout(3000)
            
            # Extract tweet URL from the timeline
            tweet_links = await page.locator(
                f'a[href*="/status/"]'
            ).all()
            
            if tweet_links:
                href = await tweet_links[0].get_attribute('href')
                tweet_id = href.split('/status/')[-1].split('?')[0]
                return {
                    "success": True,
                    "tweet_id": tweet_id,
                    "url": f"https://x.com{href}",
                }
            
            return {"success": True, "message": "Tweet posted (ID extraction failed)"}
            
        finally:
            await browser.close()
```

### 2.2 Search Tweets

```python
async def search_tweets(query: str, max_results: int = 10) -> list:
    """Search X using the web UI and extract results from DOM."""
    
    async with async_playwright() as p:
        browser, page = await _launch_stealth_browser(p)
        
        try:
            await _inject_cookies(page)
            await warmup_session(page)
            
            # Navigate to search URL directly
            encoded_query = urllib.parse.quote(query)
            await page.goto(f"https://x.com/search?q={encoded_query}&src=typed_query&f=live")
            await HumanBehavior.random_delay(2000, 4000)
            
            # Scroll to load more results
            tweets = []
            for _ in range(min(max_results // 5, 5)):
                await HumanBehavior.scroll_and_read(page, 600)
                
                # Extract tweet data from DOM
                tweet_elements = await page.locator('article[data-testid="tweet"]').all()
                
                for el in tweet_elements[:max_results]:
                    tweet = await _extract_tweet_from_element(el)
                    if tweet and tweet not in tweets:
                        tweets.append(tweet)
                
                if len(tweets) >= max_results:
                    break
            
            return tweets[:max_results]
            
        finally:
            await browser.close()
```

### 2.3 Get User Profile / Follower Count

```python
async def get_user_info() -> dict:
    """Navigate to own profile and extract stats from DOM."""
    
    async with async_playwright() as p:
        browser, page = await _launch_stealth_browser(p)
        
        try:
            await _inject_cookies(page)
            
            # Navigate to profile
            await page.goto("https://x.com/home")
            await HumanBehavior.random_delay(1500, 3000)
            
            # Click profile link
            await HumanBehavior.click_like_human(
                page, '[data-testid="AppTabBar_Profile_Link"]'
            )
            await HumanBehavior.random_delay(2000, 4000)
            
            # Extract follower count from DOM
            # X shows: "123 Following 456 Followers"
            followers_text = await page.locator(
                'a[href$="/followers"]'
            ).inner_text()
            
            following_text = await page.locator(
                'a[href$="/following"]'
            ).inner_text()
            
            name = await page.locator(
                '[data-testid="UserName"]'
            ).inner_text()
            
            return {
                "name": name,
                "followers": _parse_count(followers_text),
                "following": _parse_count(following_text),
            }
            
        finally:
            await browser.close()
```

### 2.4 Reply to a Tweet

```python
async def reply_to_tweet(tweet_url: str, text: str) -> dict:
    """Navigate to tweet, click reply, type, post."""
    
    async with async_playwright() as p:
        browser, page = await _launch_stealth_browser(p)
        
        try:
            await _inject_cookies(page)
            await warmup_session(page)
            
            # Navigate to tweet
            await page.goto(tweet_url)
            await HumanBehavior.random_delay(2000, 4000)
            
            # Scroll to read tweet
            await HumanBehavior.scroll_and_read(page, 400)
            
            # Click reply button
            await HumanBehavior.click_like_human(
                page, '[data-testid="reply"]'
            )
            await HumanBehavior.random_delay(1000, 2000)
            
            # Type reply
            await HumanBehavior.type_like_human(
                page, '[data-testid="tweetTextarea_0"]', text
            )
            
            # Click reply button
            await HumanBehavior.click_like_human(
                page, '[data-testid="tweetButton"], [data-testid="tweetButtonInline"]'
            )
            
            await page.wait_for_timeout(3000)
            return {"success": True, "message": "Reply posted"}
            
        finally:
            await browser.close()
```

---

## 3. Error Handling & Resilience

### 3.1 Cloudflare Challenge Detection

```python
async def detect_cloudflare(page) -> bool:
    """Check if Cloudflare JS challenge is active."""
    title = await page.title()
    content = await page.content()
    
    return (
        "Just a moment" in title or
        "cf-browser-verification" in content or
        "challenge-platform" in content or
        await page.locator("#cf-challenge-running").count() > 0
    )

async def handle_cloudflare(page):
    """Wait for Cloudflare challenge to complete."""
    max_wait = 30  # seconds
    for _ in range(max_wait):
        if not await detect_cloudflare(page):
            return True
        await asyncio.sleep(1)
    return False  # Failed
```

### 3.2 Rate Limit / "Something went wrong"

```python
async def detect_rate_limit(page) -> bool:
    """X shows 'Something went wrong' or 'Rate limit exceeded'."""
    content = await page.content()
    return any(phrase in content for phrase in [
        "Rate limit exceeded",
        "Something went wrong",
        "Sorry, something went wrong",
        "You have reached your daily limit",
    ])

async def handle_rate_limit():
    """Back off exponentially. Log incident. Alert user."""
    # Implementation: exponential backoff, mark account state
    pass
```

### 3.3 Selector Evolution (X Changes DOM)

X changes `data-testid` values and class names frequently. Strategy:

```python
# Priority-based selector fallback system
SELECTOR_FALLBACKS = {
    "compose_button": [
        '[data-testid="SideNav_NewTweet_Button"]',
        '[data-testid="primaryColumn"] a[href="/compose/tweet"]',
        'button:has-text("Post")',
        'a:has-text("Post")',
    ],
    "tweet_input": [
        '[data-testid="tweetTextarea_0"]',
        '.public-DraftEditor-content',
        'div[contenteditable="true"][role="textbox"]',
        'div[contenteditable="true"]',
    ],
    "post_button": [
        '[data-testid="tweetButton"]',
        '[data-testid="tweetButtonInline"]',
        'button:has-text("Post"):not([disabled])',
    ],
    "timeline_tweet": [
        'article[data-testid="tweet"]',
        'article[role="article"]',
    ],
}

async def find_element_with_fallback(page, key: str, timeout=5000):
    """Try multiple selectors, return first match."""
    selectors = SELECTOR_FALLBACKS.get(key, [])
    for selector in selectors:
        try:
            el = page.locator(selector).first
            await el.wait_for(timeout=timeout // len(selectors))
            return el
        except:
            continue
    raise ElementNotFound(f"None of the selectors worked for '{key}'")
```

---

## 4. Integration with Existing Ferrox

### 4.1 Fallback Logic in `_get_twikit_client()`

```python
async def _get_x_client(config=None):
    """Try twikit first, fall back to Playwright."""
    # Attempt 1: Twikit (fast, headless, no browser window)
    try:
        client = _get_twikit_client(config)
        # Quick test: can we get user info?
        user = client.user()
        return {"client": client, "type": "twikit"}
    except Exception as e:
        logger.info(f"Twikit failed ({e}), using Playwright fallback")
    
    # Attempt 2: Playwright (slower, needs browser window)
    return {"client": None, "type": "playwright"}
```

### 4.2 Unified Tool Interface

```python
async def post_tweet_tool(ctx: RunContext, text: str, ...) -> str:
    config = SocialConfig()
    client_info = await _get_x_client(config)
    
    if client_info["type"] == "twikit":
        # Fast path
        tweet = client_info["client"].create_tweet(text)
        return f"✅ Tweet posted: {tweet.id}"
    else:
        # Playwright fallback
        from .x_playwright_fallback import post_tweet
        result = await post_tweet(text)
        if result["success"]:
            return f"✅ Tweet posted via browser: {result.get('url', 'N/A')}"
        return f"❌ Failed: {result.get('error', 'Unknown error')}"
```

### 4.3 User Experience

When Playwright fallback activates, the user sees:

```
[THINK] Twikit API unavailable (X changed their internal API). 
        Switching to browser automation (slower but reliable)...
[THINK] Opening stealth Chromium browser...
[THINK] Injecting session cookies...
[THINK] Navigating to X.com... (warming up session)
[THINK] Scrolling timeline... (anti-detection warmup)
[THINK] Clicking 'Post' button...
[THINK] Typing tweet text (human speed)...
[THINK] Clicking submit...
[THINK] Tweet posted successfully! Extracting URL...
[OK]    Tweet posted: https://x.com/username/status/1234567890
```

---

## 5. Performance & Resource Considerations

| Metric | Twikit | Playwright Fallback |
|--------|--------|---------------------|
| **Startup time** | ~1s | ~3-5s (browser launch) |
| **Per-action time** | ~1-2s | ~8-15s (human delays) |
| **Browser window** | None | Visible Chromium |
| **Memory** | Low (~50MB) | Medium (~200-300MB) |
| **Reliability** | Breaks when X changes API | **Stable** (uses real UI) |
| **Rate limit risk** | Higher (fast = bot-like) | **Lower** (human pacing) |

**Recommendation:** Always try twikit first (fast). Fall back to Playwright only when twikit fails. This gives best performance with guaranteed reliability.

---

## 6. Security & Safety

- **Browser isolation:** Each action gets a fresh browser context (isolated cookies, storage).
- **No password storage:** Only session cookies are used.
- **Screenshot evidence:** Optional — capture before/after for audit trail.
- **Timeout guards:** Every action has max timeout (30-60s) to prevent hangs.
- **Graceful degradation:** If Playwright fails too, return clear error + suggest `/x-login` refresh.

---

## 7. Implementation Phases

### Phase 1: Core Infrastructure (2-3 hours)
- `x_stealth.py` — Browser launch, fingerprint evasion, cookie injection
- `x_playwright_fallback.py` — Base wrapper with error handling
- Selector fallback dictionary

### Phase 2: Actions (3-4 hours)
- `post_tweet()` — Most common use case
- `search_tweets()` — DOM extraction
- `get_user_info()` — Profile scraping
- `reply_to_tweet()` — Reply flow

### Phase 3: Integration (2 hours)
- Modify `tools_social.py` to try twikit → fallback to Playwright
- Add human behavior module
- Warmup protocol
- Cloudflare detection

### Phase 4: Polish (2 hours)
- Selector monitoring (auto-detect when X changes DOM)
- Screenshot capture for debugging
- Progress indicators in CLI
- Documentation update

**Total estimate: ~9-11 hours of focused work**

---

## 8. Testing Strategy

1. **Cookie injection test:** Does X recognize the session? (check if home timeline loads)
2. **Post test:** Can we post and see the tweet on timeline?
3. **Search test:** Can we search and get real results?
4. **Rate limit test:** What happens after 10 rapid posts?
5. **Cloudflare test:** Does stealth bypass CF on first visit?
6. **Long session test:** Does the browser stay stable for 30+ minutes?

---

## Open Questions

1. Should we cache the browser instance between actions (faster) or launch fresh each time (safer)?
2. Do we need a "headless stealth" mode for CI/testing, or only headed for production?
3. Should we screenshot every action for debugging/audit?
4. How do we detect when X changes DOM selectors? (screenshot diffing? ML-based element finding?)

---

*Plan v1.0 — Ready for implementation approval*
