import asyncio
import json
import logging
import time
import uuid
from typing import Any

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

    def __init__(
        self,
        settings,
        working_memory,
        llm_router=None,
        tools: dict = None,
        checkpoint_store=None,
        reflection_engine=None,
        planner=None,
        hitl_enabled: bool = False,
    ):
        self.settings = settings
        self.memory = working_memory
        self.llm = llm_router
        self.tools = tools or {}
        self._checkpoints = checkpoint_store   # CheckpointStore | None
        self._reflection = reflection_engine   # ReflectionEngine | None
        self._planner = planner                # Planner | None
        self._hitl_enabled = hitl_enabled
        self._tokens_used = 0
        self._cost_used = 0.0

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

                    # REASON
                    with display.Spinner("Thinking..."):
                        response = await self._reason(messages, steps)
                    self._track_usage(response)
                    self._check_budget()

                    content = response["content"]

                    # FINAL_ANSWER
                    if self._is_final(content):
                        final_result = self._extract_final(content)
                        break

                    # TOOL_CALL
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

                        # Execute tool
                        display.info(f"Using {tool_name}...")
                        with display.Spinner(f"Running {tool_name}..."):
                            result = await self._execute_tool(tool_name, tool_args)

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
                logger.debug("Reflection failed (non-fatal): %s", exc)

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
            logger.debug("Checkpoint save failed (non-fatal): %s", exc)

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

    async def _reason(self, messages: list, steps: list) -> dict:
        """Call LLM for reasoning step."""
        if self.tools:
            tool_list = "\n".join(
                f"- {name}: {getattr(fn, '__doc__', '').splitlines()[0] if getattr(fn, '__doc__', '') else ''}"
                for name, fn in self.tools.items()
            )
            tool_msg = (
                f"\nAvailable tools:\n{tool_list}\n\n"
                "To use a tool, respond with:\n"
                'TOOL_CALL: {"name": "tool_name", "args": {...}}\n\n'
                "To give final answer:\n"
                "FINAL_ANSWER: <your answer>"
            )
            enhanced = list(messages)
            if enhanced and enhanced[0]["role"] == "system":
                enhanced[0] = {
                    "role": "system",
                    "content": enhanced[0]["content"] + tool_msg,
                }
            else:
                enhanced.insert(0, {"role": "system", "content": tool_msg.strip()})
        else:
            enhanced = messages

        return await self.llm.chat(enhanced, step_type="reason")

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    def _is_final(self, content: str) -> bool:
        return "FINAL_ANSWER:" in content

    def _extract_final(self, content: str) -> str:
        idx = content.find("FINAL_ANSWER:")
        return content[idx + len("FINAL_ANSWER:"):].strip()

    def _parse_tool_call(self, content: str) -> dict | None:
        if "TOOL_CALL:" not in content:
            return None
        idx = content.find("TOOL_CALL:")
        json_str = content[idx + len("TOOL_CALL:"):].strip()
        try:
            start = json_str.find("{")
            end = json_str.rfind("}") + 1
            if start == -1:
                return None
            return json.loads(json_str[start:end])
        except (json.JSONDecodeError, ValueError):
            return None

    # ------------------------------------------------------------------
    # Tool execution
    # ------------------------------------------------------------------

    async def _execute_tool(self, name: str, args: dict) -> Any:
        if name not in self.tools:
            return f"Error: tool '{name}' not found"
        try:
            fn = self.tools[name]
            if asyncio.iscoroutinefunction(fn):
                return await fn(**args)
            return fn(**args)
        except Exception as e:
            return f"Tool error: {e}"

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
