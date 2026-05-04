"""Headless Browser Tools for Ferrox - Devin-parity feature
Enables AI to navigate web pages, take screenshots, and interact with local web apps
"""

import os
from typing import Optional

from pydantic_ai import RunContext

from ferrox.exceptions import ToolExecutionError

# Import tracer with try/except to avoid circular import
try:
    from opentelemetry import trace

    tracer = trace.get_tracer(__name__)
except (ImportError, AttributeError):
    tracer = None


def _get_current_agent():
    """Lazy getter for _current_agent to avoid circular import."""
    try:
        from ferrox.agent.orchestrator import _current_agent

        return _current_agent
    except (ImportError, AttributeError):
        return None


async def browse_url_tool(
    ctx: RunContext, url: str, action: str = "screenshot", selector: Optional[str] = None
) -> str:
    """Navigate to a URL and perform an action."""
    span = tracer.start_as_current_span("browse_url_tool") if tracer else None
    if span:
        span.set_attribute("url", url)
        span.set_attribute("action", action)

    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)

                if action == "screenshot":
                    screenshot_dir = os.path.expanduser("~/.ferrox/screenshots")
                    os.makedirs(screenshot_dir, exist_ok=True)
                    screenshot_path = os.path.join(screenshot_dir, f"screenshot_{os.getpid()}.png")
                    await page.screenshot(path=screenshot_path, full_page=True)
                    result = (
                        f"Screenshot saved to: {screenshot_path}\nPage title: {await page.title()}"
                    )
                    agent = _get_current_agent()
                    if agent:
                        agent._log_tool_call("browse_url", {"url": url, "action": "screenshot"})
                        agent._log_tool_result("browse_url", "Screenshot captured", True)
                    return result

                elif action == "click" and selector:
                    await page.click(selector, timeout=10000)
                    await page.wait_for_timeout(2000)
                    result = f"Clicked element: {selector}\nPage title: {await page.title()}"
                    agent = _get_current_agent()
                    if agent:
                        agent._log_tool_call(
                            "browse_url", {"url": url, "action": "click", "selector": selector}
                        )
                        agent._log_tool_result("browse_url", "Element clicked", True)
                    return result

                elif action == "extract_text":
                    text = await page.evaluate("document.body.innerText")
                    text = text[:3000] if len(text) > 3000 else text
                    result = f"Page Content (truncated):\n{text}\n\nURL: {url}"
                    agent = _get_current_agent()
                    if agent:
                        agent._log_tool_call("browse_url", {"url": url, "action": "extract_text"})
                        agent._log_tool_result("browse_url", f"Extracted {len(text)} chars", True)
                    return result

                elif action == "title":
                    title = await page.title()
                    result = f"Title: {title}\nURL: {page.url}"
                    agent = _get_current_agent()
                    if agent:
                        agent._log_tool_call("browse_url", {"url": url, "action": "title"})
                        agent._log_tool_result("browse_url", f"Title: {title}", True)
                    return result

                else:
                    return f"Unknown action: {action}. Use: screenshot, click, extract_text, title"

            except Exception as e:
                agent = _get_current_agent()
                if agent:
                    agent._log_tool_call("browse_url", {"url": url, "action": action})
                    agent._log_tool_result("browse_url", str(e), False)
                return f"Browser error: {e}"
            finally:
                await browser.close()

    except ImportError:
        raise ToolExecutionError(
            "Playwright not installed. Run: pip install playwright && playwright install chromium",
            {"url": url, "action": action},
        ) from None
    except Exception as e:
        agent = _get_current_agent()
        if agent:
            agent._log_tool_call("browse_url", {"url": url, "action": action})
            agent._log_tool_result("browse_url", str(e), False)
        raise ToolExecutionError(f"Browser error: {e}", {"url": url, "action": action}) from e


async def click_element_tool(ctx: RunContext, url: str, selector: str) -> str:
    """Click an element on a page."""
    return await browse_url_tool(ctx, url, action="click", selector=selector)


async def screenshot_tool(ctx: RunContext, url: str) -> str:
    """Take a screenshot of a URL."""
    return await browse_url_tool(ctx, url, action="screenshot")


async def extract_text_tool(ctx: RunContext, url: str) -> str:
    """Extract text content from a URL."""
    return await browse_url_tool(ctx, url, action="extract_text")
