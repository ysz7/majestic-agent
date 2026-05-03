"""HTTP request tool — GET/POST/PUT/DELETE to external APIs."""
from __future__ import annotations

from majestic.tools.registry import tool

_MAX_RESPONSE = 4000


@tool(
    name="http_request",
    description=(
        "Make an HTTP request (GET/POST/PUT/DELETE) to an external API or URL. "
        "Returns status code and response body. "
        "Use for REST API calls, webhooks, or checking endpoint status."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Full URL to request",
            },
            "method": {
                "type": "string",
                "description": "HTTP method: GET, POST, PUT, PATCH, DELETE (default: GET)",
            },
            "headers": {
                "type": "object",
                "description": "Optional request headers as key-value pairs",
            },
            "body": {
                "type": "string",
                "description": "Request body (for POST/PUT/PATCH). JSON string or plain text.",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default: 15)",
            },
        },
        "required": ["url"],
    },
)
def http_request(
    url: str,
    method: str = "GET",
    headers: dict | None = None,
    body: str = "",
    timeout: int = 15,
) -> str:
    import json
    import urllib.error
    import urllib.request

    method = method.upper()
    req_headers = {"User-Agent": "majestic-agent/1.0"}
    if headers:
        req_headers.update(headers)

    data: bytes | None = None
    if body:
        data = body.encode("utf-8")
        if "Content-Type" not in req_headers:
            req_headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            raw = resp.read(_MAX_RESPONSE * 4)
    except urllib.error.HTTPError as e:
        status = e.code
        raw = e.read(_MAX_RESPONSE * 4)
    except urllib.error.URLError as e:
        return f"[request error] {e.reason}"
    except Exception as e:
        return f"[request error] {e}"

    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:
        return f"HTTP {status} — (binary response)"

    # Pretty-print JSON if possible
    try:
        parsed = json.loads(text)
        text = json.dumps(parsed, ensure_ascii=False, indent=2)
    except Exception:
        pass

    if len(text) > _MAX_RESPONSE:
        text = text[:_MAX_RESPONSE] + f"\n… (truncated, {len(text)} chars total)"

    return f"HTTP {status}\n{text}"
