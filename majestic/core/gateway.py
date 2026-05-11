"""
Gateway — normalises raw channel input into a structured task dict.

Responsibilities:
- Detect and strip prompt injection attempts in user input.
- Attach session metadata and conversation history from working memory.
- Inject the persona defined in the profile's settings.
- Detect file attachments that require the file_parser tool.
- Persist the incoming user message to working memory.
- Update user profile from interaction.
- Build the LLM system prompt from persona fields, episodic history,
  user profile summary, and semantic knowledge base context.
"""

from __future__ import annotations

import logging
import os
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from majestic.memory.working import WorkingMemory
    from majestic.memory.episodic import EpisodicMemory
    from majestic.memory.user_profile import UserProfile
    from majestic.memory.semantic import SemanticMemory

logger = logging.getLogger(__name__)

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

# ---------------------------------------------------------------------------
# Prompt injection detection patterns
# ---------------------------------------------------------------------------

_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions?", re.I),
    re.compile(r"disregard\s+(your|all)\s+(previous\s+)?instructions?", re.I),
    re.compile(r"you\s+are\s+now\s+a\b", re.I),
    re.compile(r"forget\s+(everything|all\s+previous)", re.I),
    re.compile(r"\bnew\s+instructions?\s*:", re.I),
    re.compile(r"\bsystem\s*:\s*(you\s+are|ignore)", re.I),
    re.compile(r"</?(system|instructions?)>", re.I),
    re.compile(r"pretend\s+(you\s+are|to\s+be)\s+", re.I),
]


def _detect_injection(text: str) -> list[str]:
    """Return list of matched injection pattern descriptions, empty if clean."""
    matched = []
    for pat in _INJECTION_PATTERNS:
        if pat.search(text):
            matched.append(pat.pattern)
    return matched


def _strip_injection(text: str) -> str:
    """Replace injection phrases with [REDACTED]."""
    for pat in _INJECTION_PATTERNS:
        text = pat.sub("[REDACTED]", text)
    return text


def _needs_parser(path: str) -> bool:
    """Return True if *path* has an extension handled by the file_parser tool."""
    _, ext = os.path.splitext(path)
    return ext.lower() in _PARSEABLE_EXTENSIONS


class Gateway:
    """Normalises raw channel input and builds the context for the agent loop.

    Parameters
    ----------
    settings:
        The loaded persona / profile settings object.
    working_memory:
        An instance of WorkingMemory scoped to the current session.
    channel:
        The active BaseChannel used to communicate with the user.
    episodic_memory:
        Optional EpisodicMemory — last N tasks injected into system prompt.
    user_profile:
        Optional UserProfile — language and topic preferences appended to prompt.
    semantic_memory:
        Optional SemanticMemory — RAG search results appended to system prompt.
    """

    def __init__(
        self,
        settings: Any,
        working_memory: "WorkingMemory",
        channel: Any,
        episodic_memory: "EpisodicMemory | None" = None,
        user_profile: "UserProfile | None" = None,
        semantic_memory: "SemanticMemory | None" = None,
    ) -> None:
        self.settings = settings
        self.memory = working_memory
        self.channel = channel
        self.episodic = episodic_memory
        self.user_profile = user_profile
        self.semantic = semantic_memory

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def process(self, raw_input: dict) -> dict:
        """Normalise *raw_input* from a channel into a fully-enriched task dict."""
        text: str = raw_input.get("text", "")
        attachments: list[str] = raw_input.get("attachments", [])
        session_id: str = raw_input.get("session_id", "")

        # ------------------------------------------------------------------
        # Prompt injection detection — strip and log, do not raise.
        # ------------------------------------------------------------------
        injection_detected = False
        if text:
            matched = _detect_injection(text)
            if matched:
                injection_detected = True
                logger.warning(
                    "Prompt injection attempt detected in user input "
                    "(patterns: %s). Sanitising.", matched
                )
                text = _strip_injection(text)

        # ------------------------------------------------------------------
        # Identify attachments that the file_parser tool should pre-process.
        # ------------------------------------------------------------------
        parseable_files = [p for p in attachments if _needs_parser(p)]

        # ------------------------------------------------------------------
        # Persist the user message into working memory.
        # ------------------------------------------------------------------
        if text:
            self.memory.add_message("user", text)

        # ------------------------------------------------------------------
        # Update user profile from this interaction.
        # ------------------------------------------------------------------
        if self.user_profile and text:
            try:
                self.user_profile.update_from_interaction(text, {})
            except Exception as exc:
                logger.debug("UserProfile update failed (non-fatal): %s", exc)

        # ------------------------------------------------------------------
        # Build enriched system prompt (persona + episodic + profile + RAG).
        # ------------------------------------------------------------------
        persona = self._extract_persona()
        history = self.memory.get_messages()
        system_prompt = self._build_enriched_system_prompt(text)

        return {
            "text": text,
            "attachments": attachments,
            "parseable_files": parseable_files,
            "session_id": session_id,
            "persona": persona,
            "system_prompt": system_prompt,
            "history": history,
            "injection_detected": injection_detected,
        }

    def build_system_prompt(self) -> str:
        """Render the base system prompt from persona fields only."""
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

    def _build_enriched_system_prompt(self, current_query: str = "") -> str:
        """Persona + episodic history + user profile + RAG context."""
        parts = [self.build_system_prompt()]

        # Episodic: last 5 completed tasks as brief reference
        if self.episodic:
            try:
                recent = self.episodic.get_recent(5)
                if recent:
                    lines = ["\n[PAST TASKS — reference only, do not repeat them]"]
                    for t in recent:
                        task_preview = t["task"][:80].replace("\n", " ")
                        result_preview = t["result"][:100].replace("\n", " ")
                        lines.append(f"- {task_preview}: {result_preview}")
                    parts.append("\n".join(lines))
            except Exception as exc:
                logger.debug("Episodic memory injection failed (non-fatal): %s", exc)

        # User profile: preferred language + frequent topics
        if self.user_profile:
            try:
                lang = self.user_profile.get("preferred_language", "")
                topics = self.user_profile.get("common_topics", "")
                profile_lines = ["\n[USER PROFILE]"]
                if lang:
                    profile_lines.append(f"Preferred language: {lang}")
                if topics:
                    profile_lines.append(f"Frequent topics: {topics}")
                if len(profile_lines) > 1:
                    parts.append("\n".join(profile_lines))
            except Exception as exc:
                logger.debug("UserProfile injection failed (non-fatal): %s", exc)

        # Semantic RAG: search indexed knowledge base with the current query
        if self.semantic and current_query:
            try:
                results = self.semantic.search(current_query, limit=3)
                rag_block = self.semantic.format_for_prompt(results)
                if rag_block:
                    parts.append("\n" + rag_block)
            except Exception as exc:
                logger.debug("Semantic RAG injection failed (non-fatal): %s", exc)

        return "\n".join(parts)

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
