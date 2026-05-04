"""Script execution log and usage metrics."""
from __future__ import annotations

import json
import time
from pathlib import Path


def _log_path() -> Path:
    from majestic.constants import WORKSPACE_DIR
    d = WORKSPACE_DIR / "scripts"
    d.mkdir(parents=True, exist_ok=True)
    return d / ".log.jsonl"


def record_run(name: str, exit_code: int, duration_ms: int, source: str = "agent") -> None:
    try:
        entry = {
            "name": name,
            "ts": int(time.time()),
            "exit_code": exit_code,
            "duration_ms": duration_ms,
            "source": source,
        }
        with _log_path().open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def get_stats(name: str) -> dict:
    return get_all_stats().get(name, {})


def get_all_stats() -> dict[str, dict]:
    stats: dict[str, dict] = {}
    try:
        p = _log_path()
        if not p.exists():
            return stats
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except Exception:
                continue
            name = e.get("name", "")
            if not name:
                continue
            if name not in stats:
                stats[name] = {"runs": 0, "successes": 0, "last_ts": 0, "last_error_code": None}
            s = stats[name]
            s["runs"] += 1
            if e.get("exit_code", 1) == 0:
                s["successes"] += 1
            else:
                s["last_error_code"] = e.get("exit_code")
            if e.get("ts", 0) > s["last_ts"]:
                s["last_ts"] = e["ts"]
    except Exception:
        pass
    for s in stats.values():
        s["failures"] = s["runs"] - s["successes"]
        s["success_rate"] = round(s["successes"] / s["runs"], 2) if s["runs"] else 0.0
    return stats
