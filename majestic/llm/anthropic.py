"""
Anthropic LLM provider (https://api.anthropic.com).

Sends requests to the Anthropic Messages API using httpx (no SDK dependency).
Converts OpenAI-style message lists to Anthropic format automatically:
  - "system" role messages are extracted and merged into the top-level
    ``system`` field.
  - "user" / "assistant" role messages are passed as-is in ``messages``.

Required env var: ANTHROPIC_API_KEY
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from .base import BaseLLM, LLMError

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.anthropic.com/v1"
_API_VERSION = "2023-06-01"
_TIMEOUT = 120.0  # seconds
_DEFAULT_MAX_TOKENS = 4096


class AnthropicLLM(BaseLLM):
    """LLM provider backed by the Anthropic Messages API."""

    provider_name = "anthropic"

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = _TIMEOUT,
    ) -> None:
        self._api_key: str = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self, cache: bool = False) -> dict[str, str]:
        h = {
            "x-api-key": self._api_key,
            "anthropic-version": _API_VERSION,
            "content-type": "application/json",
        }
        if cache:
            h["anthropic-beta"] = "prompt-caching-2024-07-31"
        return h

    @staticmethod
    def _convert_messages(messages: list[dict]) -> tuple[str, list[dict]]:
        """
        Split an OpenAI-style message list into Anthropic format.

        Handles standard messages plus two internal types written by the
        runtime when native tool calling is active:
          - {"role": "assistant", "_tool_use": {"id", "name", "input"}, "content": ""}
          - {"role": "tool", "tool_use_id": ..., "content": ...}
        """
        system_parts: list[str] = []
        converted: list[dict] = []

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "") or ""

            if role == "system":
                if content:
                    system_parts.append(content)

            elif role == "assistant" and "_tool_use" in msg:
                tc = msg["_tool_use"]
                blocks = []
                if content:
                    blocks.append({"type": "text", "text": content})
                blocks.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["name"],
                    "input": tc["input"],
                })
                converted.append({"role": "assistant", "content": blocks})

            elif role == "tool":
                converted.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.get("tool_use_id", ""),
                        "content": str(content),
                    }],
                })

            elif role in ("user", "assistant"):
                converted.append({"role": role, "content": content})

        system_prompt = "\n\n".join(system_parts)
        return system_prompt, converted

    @staticmethod
    def _to_anthropic_tools(tools: list[dict]) -> list[dict]:
        """Convert generic tool schemas to Anthropic ``tools`` format."""
        result = []
        for t in tools:
            result.append({
                "name": t["name"],
                "description": t.get("description", ""),
                "input_schema": (
                    t.get("input_schema")
                    or t.get("parameters")
                    or {"type": "object", "properties": {}}
                ),
            })
        return result

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: list[dict],
        model: str,
        **kwargs: Any,
    ) -> dict:
        """Send a chat request to the Anthropic Messages API."""
        if not self._api_key:
            raise LLMError("ANTHROPIC_API_KEY is not set", provider=self.provider_name)

        use_cache: bool = kwargs.pop("use_cache", False)
        tools_raw: list[dict] | None = kwargs.pop("tools", None)

        system_prompt, converted_messages = self._convert_messages(messages)

        if not converted_messages:
            raise LLMError(
                "No user/assistant messages found after conversion",
                provider=self.provider_name,
            )

        if converted_messages[0]["role"] != "user":
            raise LLMError(
                "Anthropic requires the first message to have role='user'",
                provider=self.provider_name,
            )

        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": kwargs.pop("max_tokens", _DEFAULT_MAX_TOKENS),
            "messages": converted_messages,
        }
        if system_prompt:
            if use_cache:
                payload["system"] = [
                    {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}
                ]
            else:
                payload["system"] = system_prompt
        if tools_raw:
            payload["tools"] = self._to_anthropic_tools(tools_raw)
        payload.update(kwargs)

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                response = await client.post(
                    f"{_BASE_URL}/messages",
                    headers=self._headers(cache=use_cache),
                    json=payload,
                )
            except httpx.TimeoutException as exc:
                raise LLMError(
                    f"Request timed out after {self._timeout}s: {exc}",
                    provider=self.provider_name,
                ) from exc
            except httpx.RequestError as exc:
                raise LLMError(
                    f"Network error: {exc}",
                    provider=self.provider_name,
                ) from exc

        if response.status_code != 200:
            body = response.text[:500]
            raise LLMError(
                f"HTTP {response.status_code}: {body}",
                provider=self.provider_name,
                status_code=response.status_code,
            )

        try:
            data = response.json()
        except Exception as exc:
            raise LLMError(
                f"Invalid JSON response: {exc}",
                provider=self.provider_name,
            ) from exc

        # Parse content blocks — handle both text and tool_use.
        try:
            content_blocks: list[dict] = data["content"]
        except (KeyError, TypeError) as exc:
            raise LLMError(
                f"Unexpected response structure: {exc} — body: {str(data)[:300]}",
                provider=self.provider_name,
            ) from exc

        text_parts: list[str] = []
        native_tool_call: dict | None = None

        for block in content_blocks:
            btype = block.get("type")
            if btype == "text":
                text_parts.append(block.get("text", ""))
            elif btype == "tool_use":
                # Convert to the text-based TOOL_CALL format the runtime expects.
                import json as _json
                tc_json = _json.dumps(
                    {"name": block["name"], "args": block.get("input", {})},
                    ensure_ascii=False,
                )
                text_parts.append(f"TOOL_CALL: {tc_json}")
                # Also expose structured form for callers that want it.
                native_tool_call = {
                    "id": block.get("id", ""),
                    "name": block["name"],
                    "input": block.get("input", {}),
                }

        content = "\n".join(text_parts)

        usage = data.get("usage") or {}
        input_tokens: int = int(usage.get("input_tokens", 0))
        output_tokens: int = int(usage.get("output_tokens", 0))
        cost: float = self._estimate_cost(input_tokens, output_tokens)

        logger.debug(
            "Anthropic chat | model=%s | in=%d out=%d cost=$%.6f native_tool=%s",
            model,
            input_tokens,
            output_tokens,
            cost,
            native_tool_call["name"] if native_tool_call else None,
        )

        result = {
            "content": content,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": cost,
        }
        if native_tool_call:
            result["native_tool_call"] = native_tool_call
        return result

    async def stream(
        self,
        messages: list[dict],
        model: str,
        **kwargs: Any,
    ):
        """Stream text tokens via Anthropic SSE. Drops tools/cache kwargs gracefully."""
        if not self._api_key:
            raise LLMError("ANTHROPIC_API_KEY is not set", provider=self.provider_name)

        import json as _json

        use_cache: bool = kwargs.pop("use_cache", False)
        kwargs.pop("tools", None)  # native tool calling not supported in stream mode

        system_prompt, converted_messages = self._convert_messages(messages)

        if not converted_messages or converted_messages[0]["role"] != "user":
            raise LLMError(
                "Anthropic requires at least one user message to start",
                provider=self.provider_name,
            )

        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": kwargs.pop("max_tokens", _DEFAULT_MAX_TOKENS),
            "messages": converted_messages,
            "stream": True,
        }
        if system_prompt:
            if use_cache:
                payload["system"] = [
                    {"type": "text", "text": system_prompt,
                     "cache_control": {"type": "ephemeral"}}
                ]
            else:
                payload["system"] = system_prompt
        payload.update(kwargs)

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                async with client.stream(
                    "POST",
                    f"{_BASE_URL}/messages",
                    headers=self._headers(cache=use_cache),
                    json=payload,
                ) as response:
                    if response.status_code != 200:
                        body = await response.aread()
                        raise LLMError(
                            f"HTTP {response.status_code}: {body[:500].decode('utf-8', errors='replace')}",
                            provider=self.provider_name,
                            status_code=response.status_code,
                        )
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data = line[6:].strip()
                        if not data or data == "[DONE]":
                            continue
                        try:
                            event = _json.loads(data)
                        except _json.JSONDecodeError:
                            continue
                        if event.get("type") == "content_block_delta":
                            delta = event.get("delta", {})
                            if delta.get("type") == "text_delta":
                                text = delta.get("text", "")
                                if text:
                                    yield text
            except httpx.TimeoutException as exc:
                raise LLMError(
                    f"Stream timed out after {self._timeout}s: {exc}",
                    provider=self.provider_name,
                ) from exc
            except httpx.RequestError as exc:
                raise LLMError(
                    f"Network error during stream: {exc}",
                    provider=self.provider_name,
                ) from exc

    async def is_available(self) -> bool:
        """
        Probe the Anthropic API.

        Uses the models list endpoint (GET /v1/models, introduced in
        anthropic-version 2023-06-01) which consumes no tokens.
        Falls back gracefully — never raises.
        """
        if not self._api_key:
            return False

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{_BASE_URL}/models",
                    headers=self._headers(),
                )
            # 200 → available.  401/403 → bad key (not available).
            return response.status_code == 200
        except Exception as exc:  # noqa: BLE001
            logger.debug("Anthropic is_available check failed: %s", exc)
            return False
