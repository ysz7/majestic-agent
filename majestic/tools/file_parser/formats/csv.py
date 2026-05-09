import csv


def parse(path: str) -> str:
    """Parse CSV file using stdlib csv module, return formatted text."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        rows = list(reader)

    if not rows:
        return ""

    header = " | ".join(rows[0])
    preview_rows = rows[1:21]
    data = "\n".join(" | ".join(row) for row in preview_rows)
    total = len(rows) - 1

    result = f"{header}\n{data}"
    if total > 20:
        result += f"\n... ({total} total rows)"
    return result
