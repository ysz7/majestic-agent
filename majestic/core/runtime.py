import asyncio
import inspect
import json
import logging
import re
import time
import uuid
from typing import Any

from pydantic import BaseModel, ValidationError


class _ToolCall(BaseModel):
    name: str
    args: dict = {}

from majestic import display

logger = logging.getLogger(__name__)


class BudgetExceeded(Exception):
    pass


class HitlDenied(Exception):
    """Raised when the user denies a HITL-gated action."""
    pass


class AgentRuntime:
    MAX_ITERATIONS = 30
    TIMEOUT_SECONDS = 300
    MAX_DELEGATIONS = 4  # cap fire-and-forget delegate_to_agent calls per task

    # Tools whose results are safe to cache (read-only, deterministic enough)
    _CACHEABLE_TOOLS = frozenset({"web_search", "web_fetch"})
    _TOOL_CACHE_TTL = 300.0  # seconds — matches ReAct loop timeout

    def __init__(
        self,
        settings,
        working_memory,
        llm_router=None,
        tools: dict = None,
        checkpoint_store=None,
        reflection_engine=None,
        planner=None,
        context_manager=None,
        hitl_enabled: bool = False,
        stream_callback=None,
    ):
        self.settings = settings
        self.memory = working_memory
        self.llm = llm_router
        self.tools = tools or {}
        self._checkpoints = checkpoint_store   # CheckpointStore | None
        self._reflection = reflection_engine   # ReflectionEngine | None
        self._planner = planner                # Planner | None
        self._context_mgr = context_manager   # ContextManager | None
        self._hitl_enabled = hitl_enabled
        self._stream_callback = stream_callback  # callable(token: str) | None
        self._tokens_used = 0
        self._cost_used = 0.0
        self._delegation_count = 0
        self._tool_cache: dict[str, tuple[Any, float]] = {}

    async def run(
        self,
        task: str,
        task_id: str = None,
        system_prompt: str = "",
    ) -> str:
        """
        Full ReAct loop:
        1. Load top-3 lessons from lessons DB via planner
        2. Build initial messages (system_prompt + lessons + task)
        3. Recover from checkpoint if available (crash resume)
        4. LOOP:
           a. REASON: call LLM
           b. Parse: FINAL_ANSWER -> done; TOOL_CALL -> check HITL -> execute
           c. OBSERVE: add result to context
           d. Save checkpoint
           e. Check budget
        5. REFLECT after task ends
        """
        task_id = task_id or str(uuid.uuid4())
        start_time = time.time()
        self._tokens_used = 0
        self._cost_used = 0.0
        self._delegation_count = 0

        # ------------------------------------------------------------------
        # 1. Load lessons and inject into system prompt
        # ------------------------------------------------------------------
        lessons_context = ""
        if self._planner:
            try:
                lessons_context = self._planner.get_lessons_context(task)
            except Exception as exc:
                logger.debug("Lessons load failed (non-fatal): %s", exc)

        # ------------------------------------------------------------------
        # 2. Build initial messages
        # ------------------------------------------------------------------
        messages: list[dict] = []
        full_system = system_prompt
        if lessons_context:
            full_system = (full_system + "\n\n" + lessons_context).strip()
        if full_system:
            messages.append({"role": "system", "content": full_system})
        messages.append({"role": "user", "content": task})

        steps: list[dict] = []
        resume_from = 0
        display.reset_tool_counter()

        # ------------------------------------------------------------------
        # 3. Crash recovery — reload messages/steps from last checkpoint
        # ------------------------------------------------------------------
        if self._checkpoints:
            try:
                latest = self._checkpoints.load_latest(task_id)
                if latest:
                    saved = latest["step_data"]
                    messages = saved.get("messages", messages)
                    steps = saved.get("steps", steps)
                    resume_from = latest["step_num"] + 1
                    logger.info(
                        "Resuming task %s from step %d", task_id, resume_from
                    )
            except Exception as exc:
                logger.warning("Checkpoint load failed, starting fresh: %s", exc)

        iteration = resume_from
        final_result = "Task reached maximum iterations without completing."

        try:
            async with asyncio.timeout(self.TIMEOUT_SECONDS):
                while iteration < self.MAX_ITERATIONS:
                    iteration += 1

                    # Pre-check budget before spending tokens on this step
                    self._check_budget()

                    # Compress context if approaching model limit
                    if self._context_mgr:
                        model_limit = getattr(self.llm, "context_limit", None)
                        messages = await self._context_mgr.compress_if_needed(messages, model_limit)

                    # REASON — stream only on first response (no tools used yet);
                    # subsequent iterations use the spinner so tree display stays clean
                    if self._stream_callback and not steps:
                        response = await self._reason(messages, steps)
                    else:
                        with display.Spinner("Thinking..."):
                            response = await self._reason(messages, steps)
                    self._track_usage(response)
                    self._check_budget()

                    content = response["content"]

                    # Phase K.2 — a structured native tool call is authoritative:
                    # if present, it means the model chose a tool (not a final
                    # answer), so skip the text-marker checks and use it directly.
                    native_tc = response.get("native_tool_call")

                    # FINAL_ANSWER
                    if not native_tc and self._is_final(content):
                        final_result = self._extract_final(content)
                        break

                    # TOOL_CALL — prefer the structured native call over regex parsing
                    if native_tc:
                        tool_call = {"name": native_tc["name"], "args": native_tc.get("input", {})}
                    else:
                        tool_call = self._parse_tool_call(content)
                    if tool_call:
                        tool_name = tool_call["name"]
                        tool_args = tool_call.get("args", {})

                        # HITL check before dangerous actions
                        if self._hitl_enabled and self._planner:
                            action_desc = f"{tool_name} {json.dumps(tool_args)}"
                            if self._planner.needs_hitl(action_desc):
                                approved = await self._ask_hitl(tool_name, tool_args)
                                if not approved:
                                    messages.append({"role": "assistant", "content": content})
                                    messages.append({
                                        "role": "user",
                                        "content": f"[HITL] Action '{tool_name}' was denied by the user. Choose a different approach.",
                                    })
                                    steps.append({
                                        "tool": tool_name,
                                        "args": tool_args,
                                        "result": "DENIED by user (HITL)",
                                    })
                                    await self._save_checkpoint(task_id, iteration, messages, steps)
                                    continue

                        # Delegation cap — prevent fire-and-forget loop
                        if tool_name == "delegate_to_agent":
                            self._delegation_count += 1
                            if self._delegation_count > self.MAX_DELEGATIONS:
                                messages.append({"role": "assistant", "content": content})
                                messages.append({
                                    "role": "user",
                                    "content": (
                                        "[SYSTEM] Delegation limit reached. "
                                        "Sub-agents process tasks asynchronously — you will not receive their results here. "
                                        "Synthesize what you know and give a FINAL_ANSWER now."
                                    ),
                                })
                                steps.append({"tool": tool_name, "args": tool_args, "result": "BLOCKED: delegation cap"})
                                await self._save_checkpoint(task_id, iteration, messages, steps)
                                continue

                        # Execute tool
                        with display.Spinner(f"{tool_name}..."):
                            result = await self._execute_tool(tool_name, tool_args)
                        display.tool_done(tool_name, tool_args, result)

                        messages.append({"role": "assistant", "content": content})
                        messages.append({
                            "role": "user",
                            "content": f"Tool result ({tool_name}):\n{result}",
                        })
                        steps.append({
                            "tool": tool_name,
                            "args": tool_args,
                            "result": str(result)[:500],
                        })
                    else:
                        # No tool call — treat as final answer
                        final_result = content
                        break

                    # Save checkpoint after each completed step
                    await self._save_checkpoint(task_id, iteration, messages, steps)

        except asyncio.TimeoutError:
            final_result = "Task timed out."
        except BudgetExceeded as e:
            final_result = f"Task stopped: {e}"

        duration = time.time() - start_time
        display.task_report(len(steps), self._tokens_used, self._cost_used, duration)

        # ------------------------------------------------------------------
        # 5. Reflect and clean up checkpoint
        # ------------------------------------------------------------------
        if self._reflection:
            try:
                await self._reflection.reflect(
                    task=task,
                    result=final_result,
                    steps=steps,
                    tokens_used=self._tokens_used,
                    cost=self._cost_used,
                    duration_s=duration,
                )
            except Exception as exc:
                logger.warning("Reflection failed (non-fatal): %s", exc)

        if self._checkpoints:
            try:
                self._checkpoints.complete_task(task_id)
            except Exception as exc:
                logger.debug("Checkpoint cleanup failed (non-fatal): %s", exc)

        return final_result

    # ------------------------------------------------------------------
    # Checkpoint helper
    # ------------------------------------------------------------------

    async def _save_checkpoint(
        self, task_id: str, step_num: int, messages: list, steps: list
    ) -> None:
        if not self._checkpoints:
            return
        try:
            self._checkpoints.save_step(
                task_id=task_id,
                step_num=step_num,
                step_data={
                    "messages": messages,
                    "steps": steps,
                },
            )
        except Exception as exc:
            logger.warning("Checkpoint save failed (non-fatal): %s", exc)

    # ------------------------------------------------------------------
    # HITL helper
    # ------------------------------------------------------------------

    async def _ask_hitl(self, tool_name: str, tool_args: dict) -> bool:
        """Prompt the user for approval. Returns True = approved."""
        args_preview = json.dumps(tool_args, ensure_ascii=False)[:120]
        display.warn(f"HITL — potentially dangerous action: {tool_name}")
        display.info(f"  Args: {args_preview}")
        try:
            answer = await asyncio.to_thread(display.ask, "Approve?", "n")
            return answer.strip().lower() in ("y", "yes")
        except (EOFError, OSError, SystemExit):
            logger.warning("HITL: non-interactive environment, action denied.")
            return False

    # ------------------------------------------------------------------
    # LLM reasoning
    # ------------------------------------------------------------------

    def _build_tool_schemas(self) -> list[dict]:
        """
        Build a list of tool schemas for native function calling.

        Prefers ``tool_schema()`` on the bound method's owner object;
        falls back to building a minimal schema from the function's
        docstring and ``inspect.signature``.
        """
        schemas: list[dict] = []
        for name, fn in self.tools.items():
            # 1. Try tool_schema() on the owning object (e.g. PythonExecutor)
            obj = getattr(fn, "__self__", None)
            if obj is not None and hasattr(obj, "tool_schema"):
                schemas.append(obj.tool_schema())
                continue

            # 2. Build from docstring + signature
            doc = (getattr(fn, "__doc__", "") or "").strip()
            description = doc.splitlines()[0][:200] if doc else name

            properties: dict = {}
            required: list[str] = []
            try:
                sig = inspect.signature(fn)
                for pname, param in sig.parameters.items():
                    if pname == "self":
                        continue
                    ann = param.annotation
                    if ann is int or ann is inspect.Parameter.empty and "count" in pname.lower():
                        ptype = "integer"
                    elif ann is float:
                        ptype = "number"
                    elif ann is bool:
                        ptype = "boolean"
                    elif ann is list or (hasattr(ann, "__origin__") and ann.__origin__ is list):
                        properties[pname] = {"type": "array", "items": {"type": "string"}}
                        if param.default is inspect.Parameter.empty:
                            required.append(pname)
                        continue
                    else:
                        ptype = "string"
                    properties[pname] = {"type": ptype}
                    if param.default is inspect.Parameter.empty:
                        required.append(pname)
            except (ValueError, TypeError):
                pass

            schemas.append({
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            })
        return schemas

    async def _reason(self, messages: list, steps: list) -> dict:
        """Call LLM for reasoning step."""
        if self.tools:
            from datetime import date as _date
            today = _date.today().isoformat()
            year  = today[:4]

            tool_list = "\n".join(
                f"- {name}: {getattr(fn, '__doc__', '').splitlines()[0] if getattr(fn, '__doc__', '') else ''}"
                for name, fn in self.tools.items()
            )
            tool_msg = (
                f"\n\nToday's date: {today}.\n"
                f"Search rule: ALWAYS use {year} in web_search queries — never use past years like 2024 or 2023.\n"
                "Knowledge-base rule: if the system prompt contains a [KNOWLEDGE BASE] section with relevant context, "
                "use it to answer directly and skip web_search entirely.\n"
                "Research rule: for news, trends, AI, tech, finance, science — ALWAYS call `research` first "
                "(it queries curated sources and is faster than web_search). "
                "Use web_search only for specific factual look-ups or when `research` returns nothing relevant.\n\n"
                f"Available tools:\n{tool_list}\n\n"
                "=== RESPONSE FORMAT — follow exactly, never translate these keywords ===\n\n"
                "To call a tool, output ONLY this (nothing before or after on the same line):\n"
                'TOOL_CALL: {"name": "exact_tool_name", "args": {"param": "value"}}\n\n'
                "Example:\n"
                f'TOOL_CALL: {{"name": "web_search", "args": {{"query": "best solo business {year}"}}}}\n\n'
                "After seeing the tool result, continue reasoning and call more tools or give the final answer.\n\n"
                "When you have enough information, output ONLY:\n"
                "FINAL_ANSWER: your complete answer here\n\n"
                "CRITICAL: The keywords TOOL_CALL and FINAL_ANSWER must be written exactly as shown above (English, no translation). "
                "Your answer content must follow any language instruction in the system prompt."
            )
            enhanced = list(messages)
            if enhanced and enhanced[0]["role"] == "system":
                enhanced[0] = {
                    "role": "system",
                    "content": enhanced[0]["content"] + tool_msg,
                }
            else:
                enhanced.insert(0, {"role": "system", "content": tool_msg.strip()})

            tool_schemas = self._build_tool_schemas()
        else:
            enhanced = messages
            tool_schemas = []

        # Phase K.2 — prefer structured (native) tool use on capable models:
        # the provider parses tool_use/tool_calls reliably and returns a
        # native_tool_call. Weak/free models (and Ollama) fall back to the
        # text-based TOOL_CALL protocol, which also keeps token streaming.
        if (
            tool_schemas
            and self.llm is not None
            and getattr(self.llm, "supports_native_tools", None)
            and self.llm.supports_native_tools("reason")
        ):
            return await self.llm.chat(enhanced, step_type="reason", tools=tool_schemas)
        if self._stream_callback:
            return await self._reason_streamed(enhanced, {})
        return await self.llm.chat(enhanced, step_type="reason")

    async def _reason_streamed(self, messages: list, chat_kwargs: dict) -> dict:
        """
        Stream reasoning tokens to the callback.

        Shows only text that appears BEFORE the first FINAL_ANSWER: / TOOL_CALL:
        marker, so those keywords never leak to the user and the final answer
        can be rendered cleanly by the channel without duplication.

        Uses a lookahead buffer (_LOOKAHEAD chars) to prevent partial marker
        tokens from leaking when a BPE token straddles the marker boundary.
        """
        import sys as _sys
        from majestic.llm.base import BaseLLM as _BaseLLM

        _LOOKAHEAD = 15  # > len("FINAL_ANSWER:") = 13; holds partial markers

        buffer: list[str] = []
        shown_chars = 0        # chars of full content already sent to callback
        stop_streaming = False

        # Drop native tool schemas — streaming uses the text-based protocol
        stream_kwargs = {k: v for k, v in chat_kwargs.items() if k != "tools"}

        try:
            async for token in self.llm.stream(messages, step_type="reason", **stream_kwargs):
                buffer.append(token)
                if stop_streaming:
                    continue

                full = "".join(buffer)

                # Find the earliest FINAL_ANSWER: or TOOL_CALL: marker
                safe_end = len(full)
                for pat in (self._RE_FINAL, self._RE_TOOLPFX):
                    m = pat.search(full)
                    if m and m.start() < safe_end:
                        safe_end = m.start()

                if safe_end < len(full):
                    # Complete marker found — show only text before it
                    to_show = full[shown_chars:safe_end]
                    if to_show.strip():
                        if shown_chars == 0:
                            _sys.stdout.write("\n")
                        self._stream_callback(to_show)
                        shown_chars = safe_end
                    stop_streaming = True
                    if shown_chars > 0:
                        _sys.stdout.write("\n")
                        _sys.stdout.flush()
                else:
                    # No complete marker yet — emit all except the last LOOKAHEAD
                    # chars so we never accidentally show the start of a marker
                    safe_emit = max(shown_chars, len(full) - _LOOKAHEAD)
                    to_show = full[shown_chars:safe_emit]
                    if to_show:
                        if shown_chars == 0:
                            _sys.stdout.write("\n")
                        self._stream_callback(to_show)
                        shown_chars = safe_emit

        except Exception as exc:
            logger.warning("Streaming failed, using buffered content: %s", exc)
            if not buffer:
                return await self.llm.chat(messages, step_type="reason", **chat_kwargs)

        content = "".join(buffer)
        if not content:
            return await self.llm.chat(messages, step_type="reason", **chat_kwargs)

        # After stream ends: emit any chars still in the lookahead buffer,
        # stopping before any marker found in the remaining portion.
        if not stop_streaming and shown_chars < len(content):
            safe_end = len(content)
            for pat in (self._RE_FINAL, self._RE_TOOLPFX):
                m = pat.search(content, shown_chars)
                if m and m.start() < safe_end:
                    safe_end = m.start()
            to_show = content[shown_chars:safe_end]
            if to_show.strip():
                if shown_chars == 0:
                    _sys.stdout.write("\n")
                self._stream_callback(to_show)
                shown_chars = safe_end
            if shown_chars > 0:
                _sys.stdout.write("\n")
                _sys.stdout.flush()

        input_chars = sum(len(str(m.get("content", ""))) for m in messages)
        input_tokens = input_chars // 4
        output_tokens = len(content) // 4
        cost = _BaseLLM._estimate_cost(input_tokens, output_tokens)

        return {
            "content": content,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": cost,
        }

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    # patterns compiled once
    _RE_FINAL   = re.compile(r"(?i)final[_\s-]?answer\s*:\s*")
    _RE_TOOLPFX = re.compile(r"(?i)tool[_\s-]?call\s*:\s*")

    def _is_final(self, content: str) -> bool:
        return bool(self._RE_FINAL.search(content))

    def _extract_final(self, content: str) -> str:
        m = self._RE_FINAL.search(content)
        return content[m.end():].strip() if m else content.strip()

    def _parse_tool_call(self, content: str) -> dict | None:
        # 1. Recognized prefix (case-insensitive: TOOL_CALL:, Tool Call:, etc.)
        m = self._RE_TOOLPFX.search(content)
        if m:
            result = self._json_at(content, m.end())
            if result:
                return result

        # 2. Fallback: bare {"name": "...", "args": ...} anywhere in response
        for fm in re.finditer(r'\{[^{]*?"name"\s*:\s*"', content):
            result = self._json_at(content, fm.start())
            if result:
                return result

        return None

    def _json_at(self, content: str, pos: int) -> dict | None:
        """Parse a JSON object starting at or after `pos`. Returns validated tool call or None."""
        tail = content[pos:]
        start = tail.find("{")
        if start == -1:
            return None
        depth = 0
        for i, ch in enumerate(tail[start:]):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        raw = json.loads(tail[start : start + i + 1])
                        if "name" in raw:
                            raw.setdefault("args", {})
                            return _ToolCall(**raw).model_dump()
                    except (json.JSONDecodeError, ValueError, ValidationError):
                        pass
                    break
        return None

    # ------------------------------------------------------------------
    # Tool execution
    # ------------------------------------------------------------------

    async def _execute_tool(self, name: str, args: dict) -> Any:
        if name not in self.tools:
            return f"Error: tool '{name}' not found"

        # Check TTL cache for read-only tools
        cache_key: str | None = None
        if name in self._CACHEABLE_TOOLS:
            cache_key = f"{name}:{json.dumps(args, sort_keys=True)}"
            now = time.time()
            if cache_key in self._tool_cache:
                cached_result, cached_at = self._tool_cache[cache_key]
                if now - cached_at < self._TOOL_CACHE_TTL:
                    logger.debug("Tool cache hit: %s", name)
                    return cached_result

        try:
            fn = self.tools[name]
            if asyncio.iscoroutinefunction(fn):
                result = await fn(**args)
            else:
                result = fn(**args)
        except Exception as e:
            return f"Tool error: {e}"

        if cache_key is not None:
            self._tool_cache[cache_key] = (result, time.time())

        return result

    # ------------------------------------------------------------------
    # Budget tracking
    # ------------------------------------------------------------------

    def _track_usage(self, response: dict):
        input_tokens = response.get("input_tokens", 0)
        output_tokens = response.get("output_tokens", 0)
        self._tokens_used += input_tokens + output_tokens
        cost = response.get("cost") or 0.0
        if not cost and (input_tokens or output_tokens):
            from majestic.llm.base import BaseLLM
            cost = BaseLLM._estimate_cost(input_tokens, output_tokens)
        self._cost_used += cost

    def _check_budget(self):
        limits = self.settings.limits

        max_tokens = limits.get("max_tokens_per_task", 0)
        if max_tokens > 0:
            pct = self._tokens_used / max_tokens
            if pct >= 1.0:
                display.budget_exceeded("token", f"{self._tokens_used:,}", f"{max_tokens:,}")
                raise BudgetExceeded(
                    f"Token limit reached: {self._tokens_used}/{max_tokens}"
                )
            if pct >= 0.8:
                display.budget_warn(int(pct * 100), "token", f"{self._tokens_used:,}", f"{max_tokens:,}")

        max_cost = limits.get("max_cost_per_task", 0)
        if max_cost > 0:
            pct = self._cost_used / max_cost
            if pct >= 1.0:
                display.budget_exceeded("cost", f"${self._cost_used:.4f}", f"${max_cost}")
                raise BudgetExceeded(
                    f"Cost limit reached: ${self._cost_used:.4f}/${max_cost}"
                )
            if pct >= 0.8:
                display.budget_warn(int(pct * 100), "cost", f"${self._cost_used:.4f}", f"${max_cost}")
