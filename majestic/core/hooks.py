"""Hooks lifecycle layer (Phase K.4).

A deterministic, auditable hook system around the agent loop — the majestic
analogue of Claude Code's PreToolUse/PostToolUse/... hooks.

Events:
  session_start       fired once when a task run begins
  user_prompt_submit  fired with the incoming task text (may block)
  pre_tool_use        fired before a tool runs — may ALLOW / DENY / MODIFY args
  post_tool_use       fired after a tool runs — observe / log (cannot block)
  stop                fired when a task run ends

Handlers are Python callables (sync or async) ``handler(event, context) ->
HookDecision | None``. Command hooks declared in persona.yaml run an external
process with the JSON context on stdin and read a JSON decision from stdout.

Decision semantics for pre_tool_use (and user_prompt_submit):
  - any handler returns action="deny"   -> blocked
  - a handler returns action="modify"   -> its args replace the call args
  - otherwise                           -> allowed
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from fnmatch import fnmatch
from typing import Any, Awaitable, Callable

logger = logging.getLogger("majestic.hooks")

# Event names
SESSION_START = "session_start"
USER_PROMPT_SUBMIT = "user_prompt_submit"
PRE_TOOL_USE = "pre_tool_use"
POST_TOOL_USE = "post_tool_use"
STOP = "stop"

_COMMAND_TIMEOUT = 15.0


@dataclass
class HookDecision:
    """Outcome a hook can return. ``None`` from a handler means "no opinion"."""
    action: str = "allow"          # allow | deny | modify
    args: dict | None = None        # replacement args when action == "modify"
    reason: str = ""

    @property
    def denied(self) -> bool:
        return self.action == "deny"


Handler = Callable[[str, dict], Any]  # returns HookDecision | None | Awaitable


@dataclass
class HookBus:
    """Registry + dispatcher for lifecycle hooks."""

    _handlers: dict[str, list[Handler]] = field(default_factory=lambda: defaultdict(list))

    def on(self, event: str, handler: Handler) -> None:
        self._handlers[event].append(handler)

    def add_command_hook(self, event: str, command: list[str], matcher: str = "*") -> None:
        """Register an external-command hook (JSON on stdin -> JSON decision)."""
        async def _runner(ev: str, ctx: dict) -> HookDecision | None:
            if ev in (PRE_TOOL_USE, POST_TOOL_USE) and not fnmatch(ctx.get("tool", ""), matcher):
                return None
            return await _run_command_hook(command, ev, ctx)
        self.on(event, _runner)

    async def fire(self, event: str, context: dict) -> HookDecision:
        """Run all handlers for *event*; resolve to a single decision.

        deny wins; otherwise the last modify (if any) applies; else allow.
        """
        decision = HookDecision(action="allow")
        for handler in self._handlers.get(event, []):
            try:
                res = handler(event, context)
                if inspect.isawaitable(res):
                    res = await res
            except Exception as exc:  # noqa: BLE001 — a broken hook must not crash the agent
                logger.warning("Hook for '%s' failed (ignored): %s", event, exc)
                continue
            if not isinstance(res, HookDecision):
                continue
            if res.denied:
                return res
            if res.action == "modify":
                decision = res
        return decision


async def _run_command_hook(command: list[str], event: str, context: dict) -> HookDecision | None:
    """Run an external command hook: JSON context on stdin, JSON decision on stdout."""
    payload = json.dumps({"event": event, **context})
    try:
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, _ = await asyncio.wait_for(
            proc.communicate(payload.encode("utf-8")), timeout=_COMMAND_TIMEOUT
        )
    except (asyncio.TimeoutError, FileNotFoundError, OSError) as exc:
        logger.warning("Command hook %s failed: %s", command, exc)
        return None
    text = (out or b"").decode("utf-8", "replace").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return HookDecision(
        action=str(data.get("action", "allow")),
        args=data.get("args"),
        reason=str(data.get("reason", "")),
    )


def build_hook_bus(settings, *, planner=None, hitl_ask=None, hitl_enabled: bool = False) -> HookBus:
    """Construct a HookBus from persona.yaml hooks + the built-in HITL hook.

    persona.yaml shape::

        hooks:
          - event: pre_tool_use
            matcher: "python_exec"      # glob on tool name (pre/post only)
            command: ["python", "scripts/audit_hook.py"]
    """
    bus = HookBus()

    # Phase K.5 — permission policy enforced as the first pre_tool_use hook.
    from majestic.core.permissions import PermissionPolicy

    policy = PermissionPolicy.from_settings(settings)

    async def _permission_hook(event: str, ctx: dict) -> HookDecision | None:
        tool = ctx.get("tool", "")
        verdict = policy.decide(tool)
        if verdict == "deny":
            return HookDecision(action="deny", reason=f"permission ({policy.mode}): '{tool}' not allowed")
        if verdict == "ask":
            if hitl_ask is None:
                # No interactive prompt available (server/desktop) — fail safe.
                return HookDecision(action="deny", reason=f"permission: '{tool}' requires approval (non-interactive)")
            approved = await hitl_ask(tool, ctx.get("args", {}))
            if not approved:
                return HookDecision(action="deny", reason="permission: denied at prompt")
        return None  # allow

    bus.on(PRE_TOOL_USE, _permission_hook)

    # Persona-declared command hooks.
    for spec in getattr(settings, "hooks", []) or []:
        try:
            event = spec.get("event")
            command = spec.get("command")
            matcher = spec.get("matcher", "*")
            if event and command:
                cmd = [command] if isinstance(command, str) else list(command)
                bus.add_command_hook(event, cmd, matcher)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Invalid hook spec %s: %s", spec, exc)

    # Built-in HITL as a pre_tool_use hook.
    if hitl_enabled and planner is not None and hitl_ask is not None:
        async def _hitl_hook(event: str, ctx: dict) -> HookDecision | None:
            tool = ctx.get("tool", "")
            args = ctx.get("args", {})
            try:
                if planner.needs_hitl(f"{tool} {json.dumps(args, ensure_ascii=False)}"):
                    approved = await hitl_ask(tool, args)
                    if not approved:
                        return HookDecision(action="deny", reason="denied by user (HITL)")
            except Exception:
                return None
            return None
        bus.on(PRE_TOOL_USE, _hitl_hook)

    return bus
