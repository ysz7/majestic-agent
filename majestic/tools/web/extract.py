"""Web page content extractor."""
from majestic.tools.registry import tool


@tool(
    name="web_extract",
    description=(
        "Fetch and extract the main text content from a web page URL. "
        "Use when you have a specific URL and need to read its content."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to fetch and extract content from",
            },
        },
        "required": ["url"],
    },
)
def web_extract(url: str) -> str:
    try:
        import requests
        headers = {"User-Agent": "Mozilla/5.0 (compatible; Majestic/1.0)"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        if "text/html" not in content_type and "text/plain" not in content_type:
            return f"Unsupported content type: {content_type}"

        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
        except ImportError:
            text = resp.text

        # Trim to reasonable size
        lines = [l for l in text.splitlines() if l.strip()]
        return "\n".join(lines[:200])
    except Exception as e:
        return f"Failed to fetch {url}: {e}"
