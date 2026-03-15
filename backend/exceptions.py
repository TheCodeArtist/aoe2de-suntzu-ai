from __future__ import annotations


class CaptureError(Exception):
    """Raised when the game window cannot be found or a screenshot fails."""


class AIError(Exception):
    """Raised when the LLM API call fails or returns an unexpected response."""


class ConfigError(Exception):
    """Raised when config.json is missing, malformed, or contains invalid values."""
