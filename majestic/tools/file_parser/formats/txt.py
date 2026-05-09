def parse(path: str) -> str:
    """Read plain text file and return its contents."""
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()
