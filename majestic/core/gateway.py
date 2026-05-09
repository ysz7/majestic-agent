"""
Gateway — normalises raw channel input into a structured task dict.

Responsibilities:
- Attach session metadata and conversation history from working memory.
- Inject the persona defined in the profile's settings.
- Detect file attachments that require the file_parser tool.
- Persist the incoming user message to working memory.
- Build the LLM system prompt from persona fields.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from majestic.memory.working import WorkingMemory

# ---------------------------------------------------------------------------
# Known extensions that require file parsing before LLM ingestion
# ---------------------------------------------------------------------------

_PARSEABLE_EXTENSIONS = {
    ".pdf", ".docx", ".doc",
    ".txt", ".md",
    ".csv", ".json", ".yaml", ".yml",
    ".py", ".js", ".ts",
    ".html", ".htm", ".xml",
}


def _needs_parser(path: str) -> bool:
    """Return True if *path* has an extension handled by the file_parser tool."""
    _, ext = os.path.splitext(path)
    return ext.lower() in _PARSEABLE_EXTENSIONS


class Gateway:
    """Normalises raw channel input and builds the context for the agent loop.

    Parameters
    ----------
    settings:
        The loaded persona / profile settings object.  Expected attributes:

        - ``agent_name``        (str)
        - ``agent_role``        (str)
        - ``agent_tone``        (str)
        - ``agent_restrictions`` (list[str])
        - ``agent_context``     (str)

        The object may be a Pydantic model, a SimpleNamespace, or any
        attribute-based container — the Gateway only uses ``getattr``.

    working_memory:
        An instance of :class:`~majestic.memory.working.WorkingMemory`
        scoped to the current session.

    channel:
        The active :class:`~majestic.channels.base.BaseChannel` used to
        communicate with the user.  Stored for future use (e.g. sending
        status notifications mid-task).
    """

    def __init__(
        self,
        settings: Any,
        working_memory: "WorkingMemory",
        channel: Any,
    ) -> None:
        self.settings = settings
        self.memory = working_memory
        self.channel = channel

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def process(self, raw_input: dict) -> dict:
        """Normalise *raw_input* from a channel into a fully-enriched task dict.

        Parameters
        ----------
        raw_input:
            Dict as returned by :py:meth:`BaseChannel.receive`, with keys
            ``text``, ``attachments``, and ``session_id``.

        Returns
        -------
        dict with keys:
            text            (str)        — user's message text.
            attachments     (list[str])  — file paths found in the input.
            parseable_files (list[str])  — subset of attachments needing file_parser.
            session_id      (str)        — session identifier.
            persona         (dict)       — persona fields from settings.
            system_prompt   (str)        — fully rendered system prompt.
            history         (list[dict]) — conversation messages so far.
        """
        text: str = raw_input.get("text", "")
        attachments: list[str] = raw_input.get("attachments", [])
        session_id: str = raw_input.get("session_id", "")

        # ------------------------------------------------------------------
        # Identify attachments that the file_parser tool should pre-process.
        # ------------------------------------------------------------------
        parseable_files = [p for p in attachments if _needs_parser(p)]

        # ------------------------------------------------------------------
        # Persist the user message into working memory so that the agent loop
        # can retrieve full conversation history at any time.
        # ------------------------------------------------------------------
        if text:
            self.memory.add_message("user", text)

        # ------------------------------------------------------------------
        # Build persona snapshot for this turn.
        # ------------------------------------------------------------------
        persona = self._extract_persona()

        # ------------------------------------------------------------------
        # Retrieve conversation history (includes the message we just added).
        # ------------------------------------------------------------------
        history = self.memory.get_messages()

        return {
            "text": text,
            "attachments": attachments,
            "parseable_files": parseable_files,
            "session_id": session_id,
            "persona": persona,
            "system_prompt": self.build_system_prompt(),
            "history": history,
        }

    def build_system_prompt(self) -> str:
        """Render a system prompt from the persona fields in *settings*.

        The prompt is assembled in this order:

        1. Identity line: ``"You are <name>, <role>."``
        2. Tone line: ``"Tone: <tone>."``
        3. Restrictions (if any), joined by ``"; "``.
        4. Free-form context block (if non-empty).

        Returns
        -------
        str
            A single multi-line string ready to be used as the ``system``
            message in the LLM messages list.
        """
        s = self.settings
        name = self._get(s, "agent_name", "Assistant")
        role = self._get(s, "agent_role", "AI assistant")
        tone = self._get(s, "agent_tone", "helpful")
        restrictions: list[str] = self._get(s, "agent_restrictions", []) or []
        context: str = self._get(s, "agent_context", "") or ""

        parts: list[str] = [
            f"You are {name}, {role}.",
            f"Tone: {tone}.",
        ]

        if restrictions:
            parts.append("Restrictions: " + "; ".join(restrictions))

        if context.strip():
            parts.append(context.strip())

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_persona(self) -> dict:
        """Return a plain dict with the persona fields from *settings*."""
        s = self.settings
        return {
            "name": self._get(s, "agent_name", "Assistant"),
            "role": self._get(s, "agent_role", "AI assistant"),
            "tone": self._get(s, "agent_tone", "helpful"),
            "restrictions": self._get(s, "agent_restrictions", []) or [],
            "context": self._get(s, "agent_context", "") or "",
        }

    @staticmethod
    def _get(obj: Any, key: str, default: Any = None) -> Any:
        """Attribute-safe getter that works for both objects and dicts."""
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)
