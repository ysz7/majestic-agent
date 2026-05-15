import ipaddress
import socket
from urllib.parse import urlparse

import httpx

_PRIVATE_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]

_BLOCKED_HOSTS = {"metadata.google.internal", "metadata.internal"}


def _check_url_safety(url: str) -> str | None:
    """Return an error string if the URL targets a private or internal address."""
    try:
        host = urlparse(url).hostname or ""
        if host.lower() in _BLOCKED_HOSTS:
            return f"Blocked: {host} is a reserved metadata endpoint"
        for _, _, _, _, sockaddr in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(sockaddr[0])
            for net in _PRIVATE_NETS:
                if ip in net:
                    return f"Blocked: {ip} is a private/internal address"
    except Exception:
        pass
    return None


async def get(url: str, headers: dict = None, params: dict = None) -> dict:
    """HTTP GET request. Returns {"status": int, "body": str, "headers": dict}"""
    if err := _check_url_safety(url):
        return {"status": 403, "body": err, "headers": {}}
    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        resp = await client.get(url, headers=headers or {}, params=params or {})
        return {
            "status": resp.status_code,
            "body": resp.text,
            "headers": dict(resp.headers),
        }


async def post(url: str, json: dict = None, data: dict = None, headers: dict = None) -> dict:
    """HTTP POST request. Returns {"status": int, "body": str, "headers": dict}"""
    if err := _check_url_safety(url):
        return {"status": 403, "body": err, "headers": {}}
    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        resp = await client.post(url, json=json, data=data, headers=headers or {})
        return {
            "status": resp.status_code,
            "body": resp.text,
            "headers": dict(resp.headers),
        }


def tool_schemas() -> list[dict]:
    """Return JSON schemas for both tools."""
    return [
        {
            "name": "http_get",
            "description": "Make an HTTP GET request to a URL. Returns status code, body, and headers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to request"},
                    "headers": {
                        "type": "object",
                        "description": "Optional HTTP headers to include",
                        "additionalProperties": {"type": "string"},
                    },
                    "params": {
                        "type": "object",
                        "description": "Optional query parameters",
                        "additionalProperties": {"type": "string"},
                    },
                },
                "required": ["url"],
            },
        },
        {
            "name": "http_post",
            "description": "Make an HTTP POST request to a URL. Returns status code, body, and headers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to request"},
                    "json": {
                        "type": "object",
                        "description": "JSON body to send",
                    },
                    "data": {
                        "type": "object",
                        "description": "Form data to send",
                        "additionalProperties": {"type": "string"},
                    },
                    "headers": {
                        "type": "object",
                        "description": "Optional HTTP headers to include",
                        "additionalProperties": {"type": "string"},
                    },
                },
                "required": ["url"],
            },
        },
    ]
