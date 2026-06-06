"""API testing and HTTP tools for Ferrox agent.

Provides enhanced HTTP operations with authentication support, OpenAPI schema parsing,
and request/response history tracking.
"""

import json
from typing import Any, Optional

# Import tracer
from opentelemetry import trace
from pydantic_ai import RunContext

from ..modes import Mode
from ..permissions import PermissionAction, PermissionEngine

tracer = trace.get_tracer(__name__)

# Import _current_agent
try:
    from ferrox.agent.orchestrator import _current_agent
except ImportError:
    _current_agent = None

# Import output formatters
try:
    from ..ui.output import format_tool_call
except ImportError:
    format_tool_call = None

# Shared permission engine
permissions = PermissionEngine()

# Request/response history
_request_history: list[dict[str, Any]] = []


async def api_test_tool(
    ctx: RunContext,
    url: str,
    method: str = "GET",
    headers: Optional[dict[str, str]] = None,
    body: Optional[str] = None,
    auth: Optional[dict[str, str]] = None,
    expected_status: Optional[int] = None,
    assertions: Optional[list[str]] = None,
) -> str:
    """Test an API endpoint with optional authentication and assertions.

    Args:
        url: API endpoint URL
        method: HTTP method (GET, POST, PUT, DELETE, PATCH, etc.)
        headers: Request headers
        body: Request body (JSON string)
        auth: Authentication credentials (e.g., {"type": "bearer", "token": "..."} or {"type": "basic", "username": "...", "password": "..."})
        expected_status: Expected HTTP status code
        assertions: List of assertion strings to validate response
    """
    with tracer.start_as_current_span("api_test_tool") as span:
        span.set_attribute("url", url)
        span.set_attribute("method", method)
        span.set_attribute("expected_status", expected_status)

        try:
            mode = (
                ctx.deps.mode if hasattr(ctx, "deps") and hasattr(ctx.deps, "mode") else Mode.NORMAL
            )

            # API calls are read-only by default (GET), write operations need permission
            if method.upper() not in ["GET", "HEAD", "OPTIONS"] and not permissions.check_access(
                url, PermissionAction.WRITE, mode
            ):
                error_msg = f"Permission denied: {method} requests require write access to {url}"
                span.set_attribute("access", "denied")
                if _current_agent:
                    _current_agent._log_tool_call("api_test", {"url": url, "method": method})
                    _current_agent._log_tool_result("api_test", error_msg, False)
                return error_msg

            if format_tool_call:
                format_tool_call("api_test", {"url": url, "method": method})

            try:
                import httpx
            except ImportError:
                error_msg = "httpx not installed. Run: pip install httpx"
                span.set_attribute("error", error_msg)
                if _current_agent:
                    _current_agent._log_tool_call("api_test", {"url": url})
                    _current_agent._log_tool_result("api_test", error_msg, False)
                return error_msg

            # Prepare request
            request_headers = headers or {}
            auth_kwargs = {}

            if auth:
                if auth.get("type") == "bearer":
                    request_headers["Authorization"] = f"Bearer {auth['token']}"
                elif auth.get("type") == "basic":
                    auth_kwargs["auth"] = (auth["username"], auth["password"])
                elif auth.get("type") == "api_key":
                    request_headers[auth.get("header_name", "X-API-Key")] = auth["token"]

            # Parse body if provided
            request_body = None
            if body:
                try:
                    # Try to parse as JSON
                    json.loads(body)
                    request_headers["Content-Type"] = "application/json"
                    request_body = body
                except json.JSONDecodeError:
                    # Use as plain text
                    request_body = body

            # Execute request
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=request_headers,
                    content=request_body,
                    **auth_kwargs,
                )

            # Record in history
            history_entry = {
                "url": url,
                "method": method,
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "response_length": len(response.content),
            }
            _request_history.append(history_entry)
            if len(_request_history) > 100:  # Keep last 100 requests
                _request_history.pop(0)

            # Format response
            output = "API Test Result:\n"
            output += f"  URL: {url}\n"
            output += f"  Method: {method}\n"
            output += f"  Status Code: {response.status_code}\n"
            output += f"  Response Time: {response.elapsed.total_seconds():.3f}s\n"

            # Check expected status
            if expected_status and response.status_code != expected_status:
                output += (
                    f"  ❌ FAILED: Expected status {expected_status}, got {response.status_code}\n"
                )
            else:
                output += "  ✓ Status code matches expectation\n"

            output += "\nResponse Headers:\n"
            for key, value in response.headers.items():
                output += f"  {key}: {value}\n"

            # Parse response body
            try:
                response_json = response.json()
                output += "\nResponse Body (JSON):\n"
                output += json.dumps(response_json, indent=2)[:2000]  # Limit to 2000 chars
                if len(json.dumps(response_json, indent=2)) > 2000:
                    output += "\n... (truncated)"
            except json.JSONDecodeError:
                output += f"\nResponse Body (text, {len(response.content)} chars):\n"
                output += response.text[:2000]
                if len(response.text) > 2000:
                    output += "\n... (truncated)"

            # Run assertions if provided
            if assertions:
                output += "\n\nAssertions:\n"
                response_text = response.text
                for assertion in assertions:
                    try:
                        # Simple assertion evaluation (be careful with this in production)
                        # For now, just check if assertion string exists in response
                        if assertion in response_text:
                            output += f"  ✓ {assertion}\n"
                        else:
                            output += f"  ❌ {assertion} (not found in response)\n"
                    except Exception as e:
                        output += f"  ❌ {assertion} (error: {str(e)})\n"

            if _current_agent:
                _current_agent._log_tool_call("api_test", {"url": url, "method": method})
                _current_agent._log_tool_result("api_test", f"Status {response.status_code}", True)

            return output

        except Exception as e:
            error_msg = f"Error testing API: {str(e)}"
            span.set_attribute("error", error_msg)
            if _current_agent:
                _current_agent._log_tool_call("api_test", {"url": url})
                _current_agent._log_tool_result("api_test", error_msg, False)
            return error_msg


async def api_mock_tool(
    ctx: RunContext, endpoint: str, response: str, method: str = "GET", status_code: int = 200
) -> str:
    """Generate a mock API response definition for testing purposes.

    Args:
        endpoint: API endpoint path (e.g., /api/users)
        response: Mock response data (JSON string)
        method: HTTP method to mock
        status_code: Mock status code
    """
    with tracer.start_as_current_span("api_mock_tool") as span:
        span.set_attribute("endpoint", endpoint)
        span.set_attribute("method", method)
        span.set_attribute("status_code", status_code)

        try:
            (ctx.deps.mode if hasattr(ctx, "deps") and hasattr(ctx.deps, "mode") else Mode.NORMAL)

            # Mock generation is read-only, always allowed
            if format_tool_call:
                format_tool_call("api_mock", {"endpoint": endpoint, "method": method})

            # Validate response is valid JSON
            try:
                json.loads(response)
            except json.JSONDecodeError:
                error_msg = "Response must be valid JSON"
                span.set_attribute("error", error_msg)
                if _current_agent:
                    _current_agent._log_tool_call("api_mock", {"endpoint": endpoint})
                    _current_agent._log_tool_result("api_mock", error_msg, False)
                return error_msg

            # Generate mock definition
            mock_def = {
                "endpoint": endpoint,
                "method": method,
                "status_code": status_code,
                "response": json.loads(response),
            }

            output = "Mock API Response Definition:\n\n"
            output += json.dumps(mock_def, indent=2)
            output += "\n\nThis mock can be used with a mocking server or testing framework."

            if _current_agent:
                _current_agent._log_tool_call("api_mock", {"endpoint": endpoint})
                _current_agent._log_tool_result("api_mock", "Mock definition generated", True)

            return output

        except Exception as e:
            error_msg = f"Error generating mock: {str(e)}"
            span.set_attribute("error", error_msg)
            if _current_agent:
                _current_agent._log_tool_call("api_mock", {"endpoint": endpoint})
                _current_agent._log_tool_result("api_mock", error_msg, False)
            return error_msg


async def openapi_parse_tool(ctx: RunContext, url_or_path: str) -> str:
    """Parse OpenAPI/Swagger schema from URL or file path.

    Args:
        url_or_path: URL to OpenAPI spec or local file path
    """
    with tracer.start_as_current_span("openapi_parse_tool") as span:
        span.set_attribute("url_or_path", url_or_path)

        try:
            (ctx.deps.mode if hasattr(ctx, "deps") and hasattr(ctx.deps, "mode") else Mode.NORMAL)

            # OpenAPI parsing is read-only, always allowed
            if format_tool_call:
                format_tool_call("openapi_parse", {"url_or_path": url_or_path})

            # Determine if URL or file path
            if url_or_path.startswith(("http://", "https://")):
                # Fetch from URL
                try:
                    import httpx

                    async with httpx.AsyncClient(timeout=30) as client:
                        response = await client.get(url_or_path)
                        response.raise_for_status()
                        spec = response.json()
                except ImportError:
                    error_msg = "httpx not installed. Run: pip install httpx"
                    span.set_attribute("error", error_msg)
                    if _current_agent:
                        _current_agent._log_tool_call("openapi_parse", {"url_or_path": url_or_path})
                        _current_agent._log_tool_result("openapi_parse", error_msg, False)
                    return error_msg
            else:
                # Read from file
                try:
                    with open(url_or_path) as f:
                        spec = json.load(f)
                except FileNotFoundError:
                    error_msg = f"File not found: {url_or_path}"
                    span.set_attribute("error", error_msg)
                    if _current_agent:
                        _current_agent._log_tool_call("openapi_parse", {"url_or_path": url_or_path})
                        _current_agent._log_tool_result("openapi_parse", error_msg, False)
                    return error_msg
                except json.JSONDecodeError:
                    error_msg = f"Invalid JSON in file: {url_or_path}"
                    span.set_attribute("error", error_msg)
                    if _current_agent:
                        _current_agent._log_tool_call("openapi_parse", {"url_or_path": url_or_path})
                        _current_agent._log_tool_result("openapi_parse", error_msg, False)
                    return error_msg

            # Parse OpenAPI spec
            output = "OpenAPI Specification\n"
            output += "=====================\n\n"

            if spec.get("openapi"):
                output += f"OpenAPI Version: {spec['openapi']}\n"
            elif spec.get("swagger"):
                output += f"Swagger Version: {spec['swagger']}\n"

            if spec.get("info"):
                info = spec["info"]
                output += f"Title: {info.get('title', 'N/A')}\n"
                output += f"Version: {info.get('version', 'N/A')}\n"
                output += f"Description: {info.get('description', 'N/A')[:200]}...\n"

            output += f"\nBase URL: {spec.get('servers', [{}])[0].get('url', 'N/A') if spec.get('servers') else 'N/A'}\n\n"

            # List endpoints
            if spec.get("paths"):
                output += f"Available Endpoints ({len(spec['paths'])}):\n"
                for path, methods in spec["paths"].items():
                    for method, details in methods.items():
                        details.get("operationId", "N/A")
                        summary = details.get("summary", "N/A")
                        output += f"  {method.upper():6} {path:40} - {summary[:50]}\n"
            else:
                output += "No endpoints found in specification.\n"

            # List schemas if available
            if spec.get("components", {}).get("schemas"):
                output += f"\nDefined Schemas ({len(spec['components']['schemas'])}):\n"
                for schema_name in list(spec["components"]["schemas"].keys())[:20]:  # Limit to 20
                    output += f"  - {schema_name}\n"
                if len(spec["components"]["schemas"]) > 20:
                    output += f"  ... ({len(spec['components']['schemas']) - 20} more)\n"

            if _current_agent:
                _current_agent._log_tool_call("openapi_parse", {"url_or_path": url_or_path})
                _current_agent._log_tool_result("openapi_parse", "Parsed successfully", True)

            return output

        except Exception as e:
            error_msg = f"Error parsing OpenAPI spec: {str(e)}"
            span.set_attribute("error", error_msg)
            if _current_agent:
                _current_agent._log_tool_call("openapi_parse", {"url_or_path": url_or_path})
                _current_agent._log_tool_result("openapi_parse", error_msg, False)
            return error_msg


async def api_history_tool(ctx: RunContext, limit: int = 10) -> str:
    """Get recent API request history.

    Args:
        limit: Number of recent requests to show (default: 10)
    """
    with tracer.start_as_current_span("api_history_tool") as span:
        span.set_attribute("limit", limit)

        try:
            (ctx.deps.mode if hasattr(ctx, "deps") and hasattr(ctx.deps, "mode") else Mode.NORMAL)

            # History is read-only, always allowed
            if format_tool_call:
                format_tool_call("api_history", {"limit": limit})

            if not _request_history:
                return "No API request history available."

            output = f"Recent API Requests (last {min(limit, len(_request_history))}):\n\n"

            for entry in reversed(_request_history[-limit:]):
                output += f"  {entry['method']:6} {entry['url']}\n"
                output += f"    Status: {entry['status_code']} | Size: {entry['response_length']} bytes\n\n"

            if _current_agent:
                _current_agent._log_tool_call("api_history", {"limit": limit})
                _current_agent._log_tool_result(
                    "api_history", f"Retrieved {min(limit, len(_request_history))} entries", True
                )

            return output

        except Exception as e:
            error_msg = f"Error getting API history: {str(e)}"
            span.set_attribute("error", error_msg)
            if _current_agent:
                _current_agent._log_tool_call("api_history", {"limit": limit})
                _current_agent._log_tool_result("api_history", error_msg, False)
            return error_msg


async def api_diff_tool(ctx: RunContext, url1: str, url2: str, method: str = "GET") -> str:
    """Compare responses from two API endpoints.

    Args:
        url1: First API endpoint URL
        url2: Second API endpoint URL
        method: HTTP method to use for both requests
    """
    with tracer.start_as_current_span("api_diff_tool") as span:
        span.set_attribute("url1", url1)
        span.set_attribute("url2", url2)
        span.set_attribute("method", method)

        try:
            (ctx.deps.mode if hasattr(ctx, "deps") and hasattr(ctx.deps, "mode") else Mode.NORMAL)

            # API diff is read-only, always allowed
            if format_tool_call:
                format_tool_call("api_diff", {"url1": url1, "url2": url2})

            try:
                import httpx
            except ImportError:
                error_msg = "httpx not installed. Run: pip install httpx"
                span.set_attribute("error", error_msg)
                if _current_agent:
                    _current_agent._log_tool_call("api_diff", {"url1": url1})
                    _current_agent._log_tool_result("api_diff", error_msg, False)
                return error_msg

            # Fetch both responses
            async with httpx.AsyncClient(timeout=30) as client:
                resp1 = await client.request(method, url1)
                resp2 = await client.request(method, url2)

            output = "API Response Comparison:\n\n"
            output += f"Endpoint 1: {url1}\n"
            output += f"  Status: {resp1.status_code}\n"
            output += f"  Size: {len(resp1.content)} bytes\n"
            output += f"  Time: {resp1.elapsed.total_seconds():.3f}s\n\n"

            output += f"Endpoint 2: {url2}\n"
            output += f"  Status: {resp2.status_code}\n"
            output += f"  Size: {len(resp2.content)} bytes\n"
            output += f"  Time: {resp2.elapsed.total_seconds():.3f}s\n\n"

            # Compare status codes
            if resp1.status_code != resp2.status_code:
                output += f"⚠️  Status codes differ: {resp1.status_code} vs {resp2.status_code}\n"
            else:
                output += "✓ Status codes match\n"

            # Compare response sizes
            size_diff = len(resp1.content) - len(resp2.content)
            output += f"Size difference: {size_diff} bytes\n"

            # Try JSON comparison
            try:
                json1 = resp1.json()
                json2 = resp2.json()

                if json1 == json2:
                    output += "✓ JSON responses are identical\n"
                else:
                    output += "⚠️  JSON responses differ\n"

                    # Show diff of keys
                    keys1 = set(json1.keys()) if isinstance(json1, dict) else set()
                    keys2 = set(json2.keys()) if isinstance(json2, dict) else set()

                    only_in_1 = keys1 - keys2
                    only_in_2 = keys2 - keys1

                    if only_in_1:
                        output += f"  Only in response 1: {only_in_1}\n"
                    if only_in_2:
                        output += f"  Only in response 2: {only_in_2}\n"
            except (json.JSONDecodeError, TypeError, ValueError):
                output += "Could not compare as JSON (responses may not be JSON)\n"

            if _current_agent:
                _current_agent._log_tool_call("api_diff", {"url1": url1, "url2": url2})
                _current_agent._log_tool_result("api_diff", "Comparison completed", True)

            return output

        except Exception as e:
            error_msg = f"Error comparing API responses: {str(e)}"
            span.set_attribute("error", error_msg)
            if _current_agent:
                _current_agent._log_tool_call("api_diff", {"url1": url1})
                _current_agent._log_tool_result("api_diff", error_msg, False)
            return error_msg
