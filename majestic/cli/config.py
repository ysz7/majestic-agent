"""
majestic config — interactive persona.yaml editor.

Usage:
  majestic config              → edit default profile
  majestic config <name>       → edit named profile

Wizard flow:
  ① Name  ② Role  ③ Tone  ④ Language  ⑤ Port
  ⑥ Restrictions  ⑦ Limits  ⑧ Context  → [Save]
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import yaml

from majestic import display

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_LANGUAGES = ["en", "de", "fr", "es", "ru", "pt", "zh", "ja", "other"]


# ── questionary wrappers (fallback to display helpers) ────────────────────────

def _q_text(prompt: str, default: str = "") -> str:
    try:
        import questionary
        result = questionary.text(prompt, default=default).ask()
        if result is None:
            raise SystemExit(0)
        return result
    except ImportError:
        return display.ask(prompt, default)


def _q_select(prompt: str, choices: list[str], default: str | None = None) -> str:
    try:
        import questionary
        def_choice = default if (default and default in choices) else choices[0]
        result = questionary.select(prompt, choices=choices, default=def_choice).ask()
        if result is None:
            raise SystemExit(0)
        return result
    except ImportError:
        idx = choices.index(default) if (default and default in choices) else 0
        i = display.choose(prompt, choices, default=idx)
        return choices[i]


def _q_confirm(prompt: str, default: bool = True) -> bool:
    try:
        import questionary
        result = questionary.confirm(prompt, default=default).ask()
        if result is None:
            raise SystemExit(0)
        return result
    except ImportError:
        ans = display.ask(prompt, "y" if default else "n")
        return ans.strip().lower() in ("y", "yes")


# ── field editors ─────────────────────────────────────────────────────────────

def _edit_text(label: str, current: str) -> str:
    return _q_text(f"{label}:", default=current)


def _edit_select(label: str, current: str, options: list[str]) -> str:
    choices = options if current in options else [current] + options
    return _q_select(f"{label}:", choices=choices, default=current)


def _edit_port(label: str, current: int) -> int:
    while True:
        raw = _q_text(f"{label} (1024–65535):", default=str(current))
        try:
            val = int(raw)
            if 1024 <= val <= 65535:
                return val
            display.warn("Port must be between 1024 and 65535.")
        except ValueError:
            display.warn("Please enter a valid integer.")


def _edit_restrictions(current_list: list[str]) -> list[str]:
    items = list(current_list)
    while True:
        count = len(items)
        label = f"⑥ Restrictions ({count} item{'s' if count != 1 else ''}):"
        action = _q_select(label, choices=["View all", "Add", "Remove", "Done"])
        if action == "Done":
            return items
        if action == "View all":
            if not items:
                display.info("  (none)")
            else:
                for i, r in enumerate(items, 1):
                    display.info(f"  {i}. {r}")
        elif action == "Add":
            new = _q_text("New restriction:").strip()
            if new:
                items.append(new)
                display.ok("Added.")
        elif action == "Remove":
            if not items:
                display.warn("No restrictions to remove.")
                continue
            choices = [f"{i}. {r}" for i, r in enumerate(items, 1)] + ["Cancel"]
            sel = _q_select("Select to remove:", choices=choices)
            if sel != "Cancel":
                idx = int(sel.split(".")[0]) - 1
                items.pop(idx)
                display.ok("Removed.")


def _edit_limits(current: dict[str, Any]) -> dict[str, Any]:
    display.info("  Enter 0 for unlimited.")
    max_tokens = current.get("max_tokens_per_task", 0)
    max_cost = current.get("max_cost_per_task", 0.0)

    while True:
        raw = _q_text("Max tokens per task:", default=str(max_tokens))
        try:
            new_tokens = int(raw)
            if new_tokens >= 0:
                break
            display.warn("Must be 0 or greater.")
        except ValueError:
            display.warn("Please enter a whole number.")

    while True:
        raw = _q_text("Max cost per task (USD):", default=str(max_cost))
        try:
            new_cost = float(raw)
            if new_cost >= 0.0:
                break
            display.warn("Must be 0 or greater.")
        except ValueError:
            display.warn("Please enter a number (e.g. 0.50).")

    return {"max_tokens_per_task": new_tokens, "max_cost_per_task": new_cost}


def _edit_context(current: str) -> str:
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    if editor:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", encoding="utf-8", delete=False
        ) as f:
            f.write(current)
            tmp_path = f.name
        try:
            subprocess.run([editor, tmp_path], check=False)
            return Path(tmp_path).read_text(encoding="utf-8")
        finally:
            Path(tmp_path).unlink(missing_ok=True)
    else:
        display.info("  No $EDITOR set. Enter new context (single line; blank = keep current):")
        raw = _q_text("Context:", default="").strip()
        return raw if raw else current


# ── wizard entry point ────────────────────────────────────────────────────────

def run_wizard(profile_name: str = "default") -> None:
    profile_dir = _PROJECT_ROOT / "profiles" / profile_name
    if not profile_dir.exists():
        display.err(f"Profile '{profile_name}' not found.")
        display.info(f"Create it with:  majestic new {profile_name}")
        return

    persona_file = profile_dir / "persona.yaml"
    if persona_file.exists():
        with persona_file.open("r", encoding="utf-8") as fh:
            data: dict[str, Any] = yaml.safe_load(fh) or {}
    else:
        data = {}

    print()
    display.info(f"Configuring: {profile_name}")
    print()

    # ① Name
    data["name"] = _edit_text("① Name", str(data.get("name", "Assistant")))

    # ② Role
    data["role"] = _edit_text("② Role", str(data.get("role", "General purpose AI assistant")))

    # ③ Tone
    data["tone"] = _edit_text("③ Tone", str(data.get("tone", "helpful, concise")))

    # ④ Language
    data["language"] = _edit_select(
        "④ Language",
        str(data.get("language", "en")),
        _LANGUAGES,
    )

    # ⑤ Port
    current_port = data.get("port")
    try:
        current_port = int(current_port) if current_port is not None else 8000
    except (TypeError, ValueError):
        current_port = 8000
    data["port"] = _edit_port("⑤ Port", current_port)

    # ⑥ Restrictions
    restrictions = data.get("restrictions", [])
    if not isinstance(restrictions, list):
        restrictions = []
    print()
    data["restrictions"] = _edit_restrictions(restrictions)

    # ⑦ Limits
    limits = data.get("limits", {})
    if not isinstance(limits, dict):
        limits = {}
    print()
    display.info("⑦ Limits")
    data["limits"] = _edit_limits(limits)

    # ⑧ Context
    context = data.get("context", "")
    if not isinstance(context, str):
        context = str(context) if context else ""
    preview = context[:60].replace("\n", " ")
    if len(context) > 60:
        preview += "…"
    print()
    if preview:
        display.info(f"⑧ Context: {preview!r}")
    else:
        display.info("⑧ Context: (empty)")
    if _q_confirm("Edit context?", default=False):
        data["context"] = _edit_context(context)

    # ── Save ──────────────────────────────────────────────────────────────────
    print()
    if not _q_confirm("Save changes to persona.yaml?", default=True):
        display.warn("Cancelled — no changes written.")
        return

    tmp_file = persona_file.with_suffix(".yaml.tmp")
    try:
        with tmp_file.open("w", encoding="utf-8") as fh:
            yaml.dump(data, fh, allow_unicode=True, sort_keys=False, default_flow_style=False)
        tmp_file.replace(persona_file)
    except Exception as exc:  # pylint: disable=broad-except
        tmp_file.unlink(missing_ok=True)
        display.err(f"Failed to save: {exc}")
        return

    display.ok(f"Saved — profiles/{profile_name}/persona.yaml updated")


def run(profile_name: str = "default") -> None:
    run_wizard(profile_name)
