"""Debug logger for Ferrox CLI"""

import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

DEBUG_LOG_FILE = Path.home() / ".ferrox" / "debug.log"


def setup_logger(verbose: bool = False) -> logging.Logger:
    """Setup Ferrox logger"""
    logger = logging.getLogger("ferrox")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    # Remove existing handlers
    logger.handlers.clear()

    # File handler
    DEBUG_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(DEBUG_LOG_FILE)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    logger.addHandler(file_handler)

    # Console handler (only if verbose)
    if verbose:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
        logger.addHandler(console_handler)

    return logger


def log_request(
    logger: logging.Logger,
    request_id: int,
    provider_name: str,
    model: str,
    base_url: str,
    tokens_in: int = 0,
    tokens_out: int = 0,
    success: bool = True,
    error: Optional[str] = None
):
    """Log an API request"""
    status = "OK" if success else "FAILED"
    msg = f"Request #{request_id} | Provider: {provider_name} | Model: {model} | Status: {status}"
    if tokens_in or tokens_out:
        msg += f" | Tokens: {tokens_in} in / {tokens_out} out"
    if error:
        msg += f" | Error: {error}"

    if success:
        logger.info(msg)
    else:
        logger.error(msg)


def log_tool_execution(
    logger: logging.Logger,
    tool_name: str,
    args: dict,
    success: bool,
    result: Optional[str] = None,
    error: Optional[str] = None
):
    """Log tool execution"""
    status = "OK" if success else "FAILED"
    msg = f"Tool: {tool_name} | Args: {args} | Status: {status}"
    if result and len(result) < 100:
        msg += f" | Result: {result[:100]}"
    if error:
        msg += f" | Error: {error}"

    if success:
        logger.debug(msg)
    else:
        logger.warning(msg)


def log_fallback(
    logger: logging.Logger,
    from_model: str,
    to_model: str,
    reason: str
):
    """Log model fallback"""
    logger.info(f"FALLBACK: {from_model} -> {to_model} | Reason: {reason}")


def log_provider_validation(
    logger: logging.Logger,
    provider_name: str,
    base_url: str,
    success: bool,
    models_count: int = 0,
    error: Optional[str] = None
):
    """Log provider validation"""
    status = "VALID" if success else "INVALID"
    msg = f"Provider: {provider_name} ({base_url}) | Status: {status}"
    if success:
        msg += f" | Models: {models_count}"
    if error:
        msg += f" | Error: {error}"

    if success:
        logger.info(msg)
    else:
        logger.warning(msg)


def log_permission(
    logger: logging.Logger,
    action: str,
    path: str,
    granted: bool,
    mode: str
):
    """Log permission check"""
    result = "GRANTED" if granted else "DENIED"
    logger.info(f"Permission: {action} '{path}' | Result: {result} | Mode: {mode}")


def log_mode_change(
    logger: logging.Logger,
    from_mode: str,
    to_mode: str
):
    """Log mode change"""
    logger.info(f"Mode: {from_mode} -> {to_mode}")


# Global logger instance (will be initialized on first use)
_logger: Optional[logging.Logger] = None


def get_logger(verbose: bool = False) -> logging.Logger:
    """Get or create the global logger"""
    global _logger
    if _logger is None:
        _logger = setup_logger(verbose)
    return _logger