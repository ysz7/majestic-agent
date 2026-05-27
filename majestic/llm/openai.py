"""
OpenAI LLM provider (https://api.openai.com).

Uses httpx async — no openai SDK dependency.  Accepts standard OpenAI
chat-completion message format directly, so no conversion is required.

Required env var:  OPENAI_API_KEY
Optional env vars: OPENAI_ORG_ID   (x-org-id header, optional)
                   OPENAI_BASE_URL (override for Azure / proxy endpoints)
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from .base import BaseLLM, LLMError

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://api.openai.com/v1"
_TIMEOUT = 120.0  # seconds


class OpenAILLM(BaseLLM):
    """LLM provider backed by the OpenAI Chat Completions API."""

    provider_name = "openai"

    def __init__(
        self,
        api_key: str | None = None,
        org_id: str | None = None,
        base_url: str | None = None,
        timeout: float = _TIMEOUT,
    ) -> None:
        self._api_key: str = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._org_id: str = org_id or os.environ.get("OPENAI_ORG_ID", "")
        self._base_url: str = (
            base_url
            or os.environ.get("OPENAI_BASE_URL", _DEFAULT_BASE_URL)
        ).rstrip("/")
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        if self._org_id:
            headers["OpenAI-Organization"] = self._org_id
        return headers

    @staticmethod
    def _parse_cost(usage: dict, input_tokens: int, output_tokens: int) -> float:
        """
        OpenAI does not include a cost field in the response.  Use the rough
        estimate: $0.001 / 1 K tokens (blended prompt + completion).
        """
        return BaseLLM._estimate_cost(input_tokens, output_tokens)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @staticmethod
    def _to_openai_tools(tools: list[dict]) -> list[dict]:
        """Convert generic tool schemas to OpenAI ``tools`` format."""
        result = []
        for t in tools:
            result.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": (
                        t.get("parameters")
                        or t.get("input_schema")
                        or {"type": "object", "properties": {}}
                    ),
                },
            })
        return result

    async def chat(
        self,
        messages: list[dict],
        model: str,
        **kwargs: Any,
    ) -> dict:
        """Send a chat completion request to the OpenAI API."""
        if not self._api_key:
            raise LLMError("OPENAI_API_KEY is not set", provider=self.provider_name)

        tools_raw: list[dict] | None = kwargs.pop("tools", None)

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            **kwargs,
        }
        if tools_raw:
            payload["tools"] = self._to_openai_tools(tools_raw)
            payload["tool_choice"] = "auto"

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers=self._headers(),
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

        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(
                f"Unexpected response structure: {exc} — body: {str(data)[:300]}",
                provider=self.provider_name,
            ) from exc

        content: str = message.get("content") or ""
        native_tool_call: dict | None = None

        tool_calls = message.get("tool_calls")
        if tool_calls:
            import json as _json
            tc = tool_calls[0]  # use first tool call
            try:
                args = _json.loads(tc["function"]["arguments"])
            except (KeyError, ValueError):
                args = {}
            tc_json = _json.dumps(
                {"name": tc["function"]["name"], "args": args},
                ensure_ascii=False,
            )
            content = f"TOOL_CALL: {tc_json}"
            native_tool_call = {
                "id": tc.get("id", ""),
                "name": tc["function"]["name"],
                "input": args,
            }

        usage = data.get("usage") or {}
        input_tokens: int = int(usage.get("prompt_tokens", 0))
        output_tokens: int = int(usage.get("completion_tokens", 0))
        cost: float = self._parse_cost(usage, input_tokens, output_tokens)

        logger.debug(
            "OpenAI chat | model=%s | in=%d out=%d cost=$%.6f native_tool=%s",
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

    async def is_available(self) -> bool:
        """
        Probe the OpenAI API by listing available models.

        Returns True if the API key is valid and the endpoint is reachable.
        Never raises.
        """
        if not self._api_key:
            return False

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self._base_url}/models",
                    headers=self._headers(),
                )
            return response.status_code == 200
        except Exception as exc:  # noqa: BLE001
            logger.debug("OpenAI is_available check failed: %s", exc)
            return False
