"""Scripts API — list, run, delete scripts from workspace/scripts/."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _scripts_dir() -> Path:
    from majestic.constants import WORKSPACE_DIR
    d = WORKSPACE_DIR / "scripts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _parse_frontmatter(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.rstrip()
                if not line.startswith("# "):
                    break
                if ": " in line:
                    key, _, val = line[2:].partition(": ")
                    result[key.strip()] = val.strip()
    except Exception:
        pass
    return result


def handle_list_scripts() -> dict:
    d = _scripts_dir()
    scripts = []
    for p in sorted(d.glob("*.py")):
        meta = _parse_frontmatter(p)
        stat = p.stat()
        params_str = meta.get("params", "")
        params = [x.strip() for x in params_str.split(",") if x.strip()] if params_str else []
        scripts.append({
            "name": p.stem,
            "description": meta.get("description", ""),
            "params": params,
            "tags": [t.strip() for t in meta.get("tags", "").split(",") if t.strip()],
            "created": meta.get("created", ""),
            "size": stat.st_size,
            "modified_at": int(stat.st_mtime),
        })
    return {"scripts": scripts}


def handle_run_script(body: dict) -> dict:
    name = body.get("name", "")
    params = body.get("params") or {}
    timeout = min(max(1, int(body.get("timeout", 30))), 120)

    if not name:
        return {"ok": False, "error": "name is required"}

    safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in name.strip())
    d = _scripts_dir()
    path = d / f"{safe}.py"

    if not path.exists():
        return {"ok": False, "error": f"Script '{safe}' not found"}

    env = {**os.environ}
    for k, v in params.items():
        env[str(k)] = str(v)

    try:
        result = subprocess.run(
            [sys.executable, str(path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=str(d.parent),
        )
        return {
            "ok": True,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Timed out after {timeout}s"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def handle_delete_script(name: str) -> dict:
    safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in name.strip())
    d = _scripts_dir()
    path = d / f"{safe}.py"
    if not path.exists():
        return {"ok": False, "error": "Not found"}
    path.unlink()
    return {"ok": True}
