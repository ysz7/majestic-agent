"""Health check server — delegates to the unified API server."""
PORT = 8080


def start(port: int = PORT) -> None:
    """Start the API server (includes /health endpoint). Safe to call multiple times."""
    from majestic.api.server import start as _start
    _start(port=port)
