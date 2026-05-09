import httpx
import re


async def fetch(url: str, max_chars: int = 10000) -> str:
    """
    Fetch URL and extract clean readable text.
    Uses trafilatura if available, falls back to simple HTML stripping.
    Truncates to max_chars.
    Returns clean text content.
    """
    try:
        import trafilatura
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            html = resp.text
        text = trafilatura.extract(html) or ""
        if not text:
            text = _strip_html(html)
    except ImportError:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
        text = _strip_html(resp.text)

    return text[:max_chars] if len(text) > max_chars else text


def _strip_html(html: str) -> str:
    """Simple HTML tag stripper."""
    text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def tool_schema() -> dict:
    return {
        "name": "web_fetch",
        "description": "Fetch a URL and get clean readable text content",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to fetch"},
                "max_chars": {
                    "type": "integer",
                    "description": "Max characters to return",
                    "default": 10000,
                },
            },
            "required": ["url"],
        },
    }
