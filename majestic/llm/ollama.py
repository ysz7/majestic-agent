"""
Ollama provider — local models via OpenAI-compatible API.

Tool schemas expected in Anthropic format and converted to OpenAI format internally.
Auto-starts `ollama serve` if not running; tracks the process so repl can stop it on exit.
"""
import json
import os
import subprocess
import time
import urllib.request
from typing import Iterator

from .base import LLMProvider, LLMResponse, ToolCall, Usage, register
from .openrouter import OpenRouterProvider  # reuse conversion helpers

_BASE_URL   = "http://localhost:11434/v1"
_TAGS_URL   = "http://localhost:11434/api/tags"
_started_proc: subprocess.Popen | None = None   # process we launched


def _ollama_running() -> bool:
    try:
        urllib.request.urlopen(_TAGS_URL, timeout=2)
        return True
    except Exception:
        return False


def list_local_models() -> list[str]:
    """Return model names currently installed in Ollama."""
    try:
        import json as _json
        with urllib.request.urlopen(_TAGS_URL, timeout=3) as r:
            data = _json.loads(r.read())
            return [m["name"] for m in data.get("models", [])]
    except Exception:
        pass
    try:
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=5)
        models = []
        for line in result.stdout.splitlines()[1:]:   # skip header row
            parts = line.split()
            if parts:
                models.append(parts[0])
        return models
    except Exception:
        return []


def start_ollama() -> bool:
    """Launch `ollama serve` in background. Returns True if ready."""
    global _started_proc
    if _ollama_running():
        return True
    if _started_proc is not None:
        return _ollama_running()
    print("  Starting Ollama...", end="", flush=True)
    try:
        _started_proc = subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        print("\n  Ollama not found — install it from https://ollama.com", flush=True)
        return False
    except Exception as e:
        print(f"\n  Failed to start Ollama: {e}", flush=True)
        return False

    for _ in range(20):   # up to 10 s
        time.sleep(0.5)
        if _ollama_running():
            print(" ready", flush=True)
            return True
    print(" timed out", flush=True)
    return False


def shutdown_ollama() -> None:
    """Terminate the Ollama process we started (no-op if we didn't start it)."""
    global _started_proc
    if _started_proc is not None:
        try:
            _started_proc.terminate()
        except Exception:
            pass
        _started_proc = None


@register("ollama")
class OllamaProvider(LLMProvider):
    def __init__(self, model: str | None = None, temperature: float = 0.1, **_):
        self._model = model or os.getenv("OLLAMA_MODEL", "gemma3")
        self._temperature = temperature
        self._client = None

    def _get_client(self):
        if self._client is None:
            if not _ollama_running():
                start_ollama()
            from openai import OpenAI
            self._client = OpenAI(base_url=_BASE_URL, api_key="ollama")
        return self._client

    @property
    def model_id(self) -> str:
        return self._model

    def complete(
        self,
        messages: list[dict],
        system: str = "",
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        client = self._get_client()
        converted = OpenRouterProvider._convert_messages(messages)
        msgs = ([{"role": "system", "content": system}] if system else []) + converted
        kwargs: dict = {
            "model":       self._model,
            "messages":    msgs,
            "max_tokens":  max_tokens,
            "temperature": self._temperature,
        }
        if tools:
            kwargs["tools"] = OpenRouterProvider._convert_tools(tools)
            kwargs["tool_choice"] = "auto"

        resp = client.chat.completions.create(**kwargs)
        u = resp.usage
        usage = Usage(
            input_tokens=getattr(u, "prompt_tokens", 0) or 0,
            output_tokens=getattr(u, "completion_tokens", 0) or 0,
        )
        choice = resp.choices[0] if resp.choices else None
        content = ""
        tool_calls: list[ToolCall] = []
        if choice:
            content = choice.message.content or ""
            for tc in getattr(choice.message, "tool_calls", None) or []:
                try:
                    args = json.loads(tc.function.arguments)
                except Exception:
                    args = {}
                tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))

        return LLMResponse(
            content=content,
            usage=usage,
            finish_reason=(choice.finish_reason or "stop") if choice else "stop",
            model=self._model,
            tool_calls=tool_calls,
        )

    def stream(
        self,
        messages: list[dict],
        system: str = "",
        max_tokens: int = 4096,
    ) -> Iterator[str]:
        client = self._get_client()
        converted = OpenRouterProvider._convert_messages(messages)
        msgs = ([{"role": "system", "content": system}] if system else []) + converted
        stream = client.chat.completions.create(
            model=self._model,
            messages=msgs,
            max_tokens=max_tokens,
            temperature=self._temperature,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content

    def unload(self) -> None:
        """Ask Ollama to release the model from VRAM."""
        try:
            import requests
            requests.post(
                "http://localhost:11434/api/generate",
                json={"model": self._model, "keep_alive": 0},
                timeout=5,
            )
        except Exception:
            pass
