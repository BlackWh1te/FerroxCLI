"""Monitoring and error tracking with Sentry"""

import os
from typing import Optional

import sentry_sdk

from ferrox import __version__
from sentry_sdk.integrations.asyncio import AsyncioIntegration


def init_sentry(
    dsn: Optional[str] = None, environment: Optional[str] = None, traces_sample_rate: float = 1.0
) -> bool:
    """
    Initialize Sentry for error tracking and performance monitoring

    Args:
        dsn: Sentry DSN (defaults to SENTRY_DSN environment variable)
        environment: Environment name (defaults to SENTRY_ENVIRONMENT or 'development')
        traces_sample_rate: Sample rate for performance tracing (0.0 to 1.0)

    Returns:
        True if Sentry was initialized, False otherwise
    """
    sentry_dsn = dsn or os.getenv("SENTRY_DSN")

    if not sentry_dsn:
        # No DSN provided, skip initialization
        return False

    sentry_env = environment or os.getenv("SENTRY_ENVIRONMENT", "development")

    try:
        sentry_sdk.init(
            dsn=sentry_dsn,
            integrations=[AsyncioIntegration()],
            traces_sample_rate=traces_sample_rate,
            environment=sentry_env,
            # Set release to version if available
            release=os.getenv("FERROX_VERSION", __version__),
            # Ignore common errors that might not be actionable
            ignore_errors=[
                KeyboardInterrupt,
                # Add other errors to ignore as needed
            ],
        )
        return True
    except Exception as e:
        # Fail silently if Sentry initialization fails
        print(f"Warning: Failed to initialize Sentry: {e}")
        return False


def capture_exception(exception: Exception) -> None:
    """
    Capture an exception in Sentry

    Args:
        exception: The exception to capture
    """
    sentry_sdk.capture_exception(exception)


def capture_message(message: str, level: str = "info") -> None:
    """
    Capture a message in Sentry

    Args:
        message: The message to capture
        level: Log level (debug, info, warning, error)
    """
    sentry_sdk.capture_message(message, level=level)


def add_breadcrumb(message: str, category: str = "default", level: str = "info", **kwargs) -> None:
    """
    Add a breadcrumb to Sentry for context

    Args:
        message: Breadcrumb message
        category: Breadcrumb category
        level: Breadcrumb level
        **kwargs: Additional breadcrumb data
    """
    sentry_sdk.add_breadcrumb(message=message, category=category, level=level, **kwargs)


def set_user_context(user_id: str, **kwargs) -> None:
    """
    Set user context in Sentry

    Args:
        user_id: User identifier
        **kwargs: Additional user context
    """
    sentry_sdk.set_user({"id": user_id, **kwargs})


def set_tag(key: str, value: str) -> None:
    """
    Set a tag in Sentry

    Args:
        key: Tag key
        value: Tag value
    """
    sentry_sdk.set_tag(key, value)
