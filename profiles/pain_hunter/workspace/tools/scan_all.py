"""
Run all scanners for a niche.
Usage: python scan_all.py "e-commerce logistics"
"""
import asyncio, json, sys
from scan_reddit import scan as scan_reddit
from scan_hn import scan as scan_hn
from scan_github import scan as scan_github
from scan_producthunt import scan as scan_producthunt
from scan_quora import scan as scan_quora
from scan_indiehackers import scan as scan_indiehackers


SCANNER_NAMES = ["reddit", "hn", "github", "producthunt", "quora", "indiehackers"]
SCANNERS = [scan_reddit, scan_hn, scan_github, scan_producthunt, scan_quora, scan_indiehackers]


async def scan_all(niche: str) -> dict:
    results = await asyncio.gather(
        *[scanner(niche) for scanner in SCANNERS],
        return_exceptions=True,
    )

    summary = {}
    total_content = 0
    total_urls = 0
    errors = []

    for name, result in zip(SCANNER_NAMES, results):
        if isinstance(result, Exception):
            summary[name] = {"error": str(result), "status": "failed"}
            errors.append(name)
        else:
            summary[name] = result
            summary[name]["status"] = "ok"
            total_content += result.get("content_length", 0)
            total_urls += result.get("urls_fetched", 0)

    return {
        "niche": niche,
        "sources": summary,
        "totals": {
            "sources_succeeded": len(SCANNER_NAMES) - len(errors),
            "sources_failed": len(errors),
            "failed_sources": errors,
            "total_urls_fetched": total_urls,
            "total_content_bytes": total_content,
        },
    }


if __name__ == "__main__":
    niche = sys.argv[1] if len(sys.argv) > 1 else "e-commerce logistics"
    result = asyncio.run(scan_all(niche))
    print(json.dumps(result, indent=2))
