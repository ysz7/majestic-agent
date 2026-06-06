"""Permission model (Phase K.5).

Adds permission *modes* and per-tool allow/deny/ask rules on top of the hook
layer (K.4). The policy is enforced as a built-in ``pre_tool_use`` hook, so a
denial blocks the tool exactly like any other hook decision.

persona.yaml shape::

    permissions:
      mode: default            # default | auto | plan | bypass
      allow: ["web_search", "research", "file_read"]
      ask:   ["python_exec", "node_exec", "http_*"]
      deny:  ["delegate_to_agent"]

Modes:
  default  rules apply; unmatched tools are allowed (permissive baseline)
  auto     "ask" rules are auto-approved; "deny" still denies
  plan     read-only — every tool is blocked
  bypass   allow everything, ignore rules

Rule precedence (default/auto): deny > ask > allow > (unmatched -> allow).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatch


@dataclass
class PermissionPolicy:
    mode: str = "default"
    allow: list[str] = field(default_factory=list)
    ask: list[str] = field(default_factory=list)
    deny: list[str] = field(default_factory=list)

    @staticmethod
    def _match(tool: str, patterns: list[str]) -> bool:
        return any(fnmatch(tool, p) for p in patterns)

    def decide(self, tool: str) -> str:
        """Return one of: ``allow`` | ``deny`` | ``ask``."""
        if self.mode == "bypass":
            return "allow"
        if self.mode == "plan":
            return "deny"
        if self._match(tool, self.deny):
            return "deny"
        if self._match(tool, self.ask):
            return "allow" if self.mode == "auto" else "ask"
        if self._match(tool, self.allow):
            return "allow"
        return "allow"  # permissive baseline for unmatched tools

    @classmethod
    def from_settings(cls, settings) -> "PermissionPolicy":
        raw = getattr(settings, "permissions", {}) or {}
        mode = str(raw.get("mode", "default")).lower()
        if mode not in ("default", "auto", "plan", "bypass"):
            mode = "default"

        def _list(key: str) -> list[str]:
            v = raw.get(key, [])
            return [str(x) for x in v] if isinstance(v, list) else []

        return cls(mode=mode, allow=_list("allow"), ask=_list("ask"), deny=_list("deny"))
