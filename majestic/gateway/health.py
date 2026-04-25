"""Minimal HTTP health check server — runs on a daemon thread alongside the gateway."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = 8080
_started = False


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/health":
            body = json.dumps({"status": "ok"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *_) -> None:
        pass  # suppress HTTP access logs


def start(port: int = PORT) -> None:
    """Start the health server once. Safe to call multiple times."""
    global _started
    if _started:
        return
    _started = True
    server = HTTPServer(("0.0.0.0", port), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True, name="health").start()
