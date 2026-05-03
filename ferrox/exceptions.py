"""Custom exception classes for Ferrox"""


class FerroxError(Exception):
    """Base exception for all Ferrox errors"""

    def __init__(self, message: str, details: dict = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

    def __str__(self):
        if self.details:
            return f"{self.message} | Details: {self.details}"
        return self.message


class ConfigurationError(FerroxError):
    """Configuration-related errors"""

    pass


class ProviderError(FerroxError):
    """Provider/API errors"""

    pass


class AuthenticationError(ProviderError):
    """Authentication failures"""

    pass


class RateLimitError(ProviderError):
    """Rate limit exceeded"""

    pass


class ModelNotFoundError(ProviderError):
    """Model not found"""

    pass


class PermissionDeniedError(FerroxError):
    """Permission denied errors"""

    pass


class ToolExecutionError(FerroxError):
    """Tool execution failures"""

    pass


class FileAccessError(FerroxError):
    """File access errors"""

    pass


class AgentError(FerroxError):
    """Agent execution errors"""

    pass


class ValidationError(FerroxError):
    """Validation errors"""

    pass


class TimeoutError(FerroxError):
    """Timeout errors"""

    pass


class NetworkError(FerroxError):
    """Network-related errors"""

    pass


class APIError(FerroxError):
    """API-related errors"""

    def __init__(self, message: str, status_code: int = None, details: dict = None):
        self.status_code = status_code
        details = details or {}
        if status_code:
            details["status_code"] = status_code
        super().__init__(message, details)
