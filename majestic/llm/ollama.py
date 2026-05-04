"""Ollama provider — local models via OpenAI-compatible API."""
import json
import os
import re as _re
import subprocess
import time
import urllib.request
from typing import Iterator

from .base import LLMProvider, LLMResponse, ToolCall, Usage, register
from .openrouter import OpenRouterProvider

_DEFAULT_BASE = "http://localhost:11434"

_SPURIOUS_JSON_RE = _re.compile(r'\{[^{}]*"method"\s*:\s*"[^"]+[^{}]*\}', _re.DOTALL)


def _strip_spurious_json(text: str) -> str:
    """Remove browser-API JSON objects that local models write as text."""
    cleaned = _SPURIOUS_JSON_RE.sub("", text).strip()
    return cleaned if cleaned else text


# Core tools local models should always have access to (in priority order)
_LOCAL_PRIORITY_TOOLS = [
    "search_knowledge", "search_web", "get_news", "get_briefing", "get_market_data",
    "run_research", "read_file", "write_file", "remember", "history_search",
    "db_search", "get_datetime", "run_python", "workspace_list",
]


def _limit_tools_for_local(tools: list[dict]) -> list[dict]:
    """For local models: drop MCP/browser tools, keep at most ollama_max_tools (default 15)."""
    try:
        from majestic import config as cfg
        max_tools = int(cfg.get("llm.ollama_max_tools") or 15)
    except Exception:
        max_tools = 15

    # Exclude browser/MCP tools — they confuse local models
    filtered = [t for t in tools if not t.get("name", "").startswith("mcp_")]

    # Sort: priority tools first, rest after
    priority = {name: i for i, name in enumerate(_LOCAL_PRIORITY_TOOLS)}
    filtered.sort(key=lambda t: priority.get(t.get("name", ""), 999))

    return filtered[:max_tools]


def _try_rescue_tool_call(content: str, converted_tools: list[dict]) -> "ToolCall | None":
    """If model wrote a JSON object as text instead of a tool_call, match it to the best tool.

    Heuristic: score each tool by how many of its known parameters appear in the JSON keys.
    """
    stripped = content.strip()
    # Only act when the whole response is a JSON object
    if not (stripped.startswith("{") and stripped.endswith("}")):
        return None
    try:
        args = json.loads(stripped)
    except Exception:
        return None
    if not isinstance(args, dict):
        return None
    arg_keys = set(args.keys()) - {"language", "version"}  # ignore meta keys
    if not arg_keys:
        return None
    best_name, best_score = None, 0
    for tool in (converted_tools or []):
        fn = tool.get("function", {})
        params = set(fn.get("parameters", {}).get("properties", {}).keys())
        score = len(arg_keys & params)
        if score > best_score:
            best_score, best_name = score, fn.get("name")
    if best_name and best_score > 0:
        return ToolCall(id=f"rescued_{best_name}", name=best_name, arguments=args)
    return None


def _ollama_base() -> str:
    try:
        from majestic import config as cfg
        return (cfg.get("llm.ollama_url") or _DEFAULT_BASE).rstrip("/")
    except Exception:
        return _DEFAULT_BASE
_started_proc: subprocess.Popen | None = None   # process we launched
_loaded_ctx: dict[str, int] = {}               # model → last loaded num_ctx (module-level, survives re-instantiation)


def _ollama_running() -> bool:
    try:
        urllib.request.urlopen(f"{_ollama_base()}/api/tags", timeout=2)
        return True
    except Exception:
        return False


def list_local_models() -> list[str]:
    """Return model names currently installed in Ollama."""
    try:
        with urllib.request.urlopen(f"{_ollama_base()}/api/tags", timeout=3) as r:
            return [m["name"] for m in json.loads(r.read()).get("models", [])]
    except Exception:
        pass
    try:
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=5)
        return [ln.split()[0] for ln in result.stdout.splitlines()[1:] if ln.split()]
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


def _preload_with_context(model: str, num_ctx: int) -> None:
    """Force Ollama to reload model with the desired num_ctx via native API.

    Must read the full streaming response — otherwise Ollama won't finish processing.
    """
    global _loaded_ctx
    body = json.dumps({"model": model, "prompt": "", "options": {"num_ctx": num_ctx}}).encode()
    req = urllib.request.Request(f"{_ollama_base()}/api/generate", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()  # must consume full response for Ollama to finish loading
        _loaded_ctx[model] = num_ctx
    except Exception:
        pass


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
            self._client = OpenAI(base_url=f"{_ollama_base()}/v1", api_key="ollama")
        return self._client

    def _ensure_context(self, num_ctx: int) -> None:
        """Reload model via native API if context size changed (uses module-level cache)."""
        if _loaded_ctx.get(self._model) != num_ctx:
            _preload_with_context(self._model, num_ctx)

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
        num_ctx = 8192
        try:
            from majestic import config as cfg
            num_ctx = int(cfg.get("llm.num_ctx") or num_ctx)
        except Exception:
            pass
        self._ensure_context(num_ctx)
        kwargs: dict = {
            "model":       self._model,
            "messages":    msgs,
            "max_tokens":  max_tokens,
            "temperature": self._temperature,
            "extra_body":  {"options": {"num_ctx": num_ctx}},
        }
        converted_tools: list[dict] = []
        if tools:
            tools = _limit_tools_for_local(tools)
            converted_tools = OpenRouterProvider._convert_tools(tools)
            kwargs["tools"] = converted_tools
            kwargs["tool_choice"] = "auto"
            tool_names = [t["function"]["name"] for t in converted_tools]
            tool_hint = (
                "\n\nCRITICAL RULE: You MUST use the tool_calls API to call any tool. "
                "NEVER write JSON objects, code blocks, or raw arguments in your text reply — "
                "that breaks the system and the user gets no answer. "
                "If the user asks about saved data, news, or knowledge — call search_knowledge. "
                "If the user asks about current events — call get_news or search_web. "
                f"Tools available: {', '.join(tool_names)}."
            )
            if msgs and msgs[0].get("role") == "system":
                msgs[0]["content"] += tool_hint
            else:
                msgs.insert(0, {"role": "system", "content": tool_hint})

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
            raw_tcs = getattr(choice.message, "tool_calls", None) or []
            valid_names = set(kwargs.get("tools") and [t["function"]["name"] for t in kwargs["tools"]] or [])
            for tc in raw_tcs:
                fn_name = tc.function.name
                # Skip tool calls with names not in the schema (MCP browser, etc.)
                if valid_names and fn_name not in valid_names:
                    content = (content + f"\n[attempted unknown tool: {fn_name}]").strip()
                    continue
                try:
                    args = json.loads(tc.function.arguments)
                except Exception:
                    args = {}
                tool_calls.append(ToolCall(id=tc.id, name=fn_name, arguments=args))
            # If model wrote a JSON object as text, try to rescue it as a tool call
            if not tool_calls and content and converted_tools:
                rescued = _try_rescue_tool_call(content, converted_tools)
                if rescued:
                    tool_calls = [rescued]
                    content = ""
                else:
                    content = _strip_spurious_json(content)

        return LLMResponse(
            content=content,
            usage=usage,
            finish_reason=(choice.finish_reason or "stop") if choice else "stop",
            model=self._model,
            tool_calls=tool_calls,
        )

    def stream(self, messages: list[dict], system: str = "", max_tokens: int = 4096) -> Iterator[str]:
        client = self._get_client()
        converted = OpenRouterProvider._convert_messages(messages)
        msgs = ([{"role": "system", "content": system}] if system else []) + converted
        stream = client.chat.completions.create(model=self._model, messages=msgs,
                                                max_tokens=max_tokens, temperature=self._temperature,
                                                stream=True)
        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content

    def unload(self) -> None:
        """Ask Ollama to release the model from VRAM."""
        try:
            body = json.dumps({"model": self._model, "keep_alive": 0}).encode()
            req = urllib.request.Request(f"{_ollama_base()}/api/generate", data=body,
                                         headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass
