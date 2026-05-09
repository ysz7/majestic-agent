"""
Majestic channel package.

Channels are the I/O boundary between external surfaces (CLI, HTTP, WebSocket,
Slack, …) and the agent runtime.  Import the concrete implementations from
their own modules; this package exports only the abstract base so that other
packages can type-hint against it without importing transport-specific deps.
"""

from .base import BaseChannel

__all__ = ["BaseChannel"]
