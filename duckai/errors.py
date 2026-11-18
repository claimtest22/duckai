"""
Error hierarchy for duckai.
"""

from typing import Any, Optional


class DuckAIException(Exception):
    """Base exception for all duckai errors."""

    def __init__(self, message: str = "", *, status: Optional[int] = None, payload: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.payload = payload


class ChallengeError(DuckAIException):
    """Raised when the VQD hash challenge cannot be solved or is rejected."""


class RateLimitError(DuckAIException):
    """Raised on HTTP 429."""


class AuthError(DuckAIException):
    """Raised on missing or invalid VQD tokens (418 / no hash)."""


class HTTPException(DuckAIException):
    """Generic HTTP failure."""


class ModelUnavailable(DuckAIException):
    """Requested model is not available."""
