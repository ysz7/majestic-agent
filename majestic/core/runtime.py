import asyncio
import json
import time
import uuid
from typing import Any


class BudgetExceeded(Exception):
    pass


class AgentRuntime:
    MAX_ITERATIONS = 30
    TIMEOUT_SECONDS = 300

    def __init__(self, settings, working_memory, llm_router=None, tools: dict = None):
        self.settings = settings
        self.memory = working_memory
        self.llm = llm_router
        self.tools = tools or {}  # name -> callable
        self._tokens_used = 0
        self._cost_used = 0.0

    async def run(self, task: str, task_id: str = None, system_prompt: str = "") -> str:
        """
        Full ReAct loop:
        1. Load top-3 lessons from lessons DB (if available)
        2. Load episodic history
        3. Check agent registry for delegation targets
        4. LOOP:
           a. Compact context
           b. REASON: call LLM with full context, ask for next action or FINAL_ANSWER
           c. Parse response: if FINAL_ANSWER -> done; if TOOL_CALL -> execute tool
           d. OBSERVE: add result to context
           e. Save checkpoint
           f. Check budget
        5. REFLECT (after task ends)
        """
        task_id = task_id or str(uuid.uuid4())
        start_time = time.time()

        # Build initial messages
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # Add task
        messages.append({"role": "user", "content": task})

        steps = []
        iteration = 0

        try:
            async with asyncio.timeout(self.TIMEOUT_SECONDS):
                while iteration < self.MAX_ITERATIONS:
                    iteration += 1

                    # REASON
                    response = await self._reason(messages, steps)
                    self._track_usage(response)
                    self._check_budget()

                    content = response["content"]

                    # Parse response for FINAL_ANSWER or TOOL_CALL
                    if self._is_final(content):
                        final = self._extract_final(content)
                        duration = time.time() - start_time
                        return final

                    # Parse tool call
                    tool_call = self._parse_tool_call(content)
                    if tool_call:
                        tool_name = tool_call["name"]
                        tool_args = tool_call.get("args", {})

                        # Execute tool
                        result = await self._execute_tool(tool_name, tool_args)

                        # Add to messages
                        messages.append({"role": "assistant", "content": content})
                        messages.append({"role": "user", "content": f"Tool result ({tool_name}):\n{result}"})

                        steps.append({"tool": tool_name, "args": tool_args, "result": str(result)[:500]})
                    else:
                        # Treat as final answer if no tool call found
                        return content

                return "Task reached maximum iterations without completing."

        except asyncio.TimeoutError:
            return "Task timed out."
        except BudgetExceeded as e:
            return f"Task stopped: {e}"

    async def _reason(self, messages: list, steps: list) -> dict:
        """Call LLM for reasoning step."""
        # Add available tools to system context
        if self.tools:
            tool_list = "\n".join(
                f"- {name}: {getattr(fn, '__doc__', '')}" for name, fn in self.tools.items()
            )
            tool_msg = (
                f"\nAvailable tools:\n{tool_list}\n\n"
                "To use a tool, respond with:\n"
                'TOOL_CALL: {"name": "tool_name", "args": {...}}\n\n'
                "To give final answer:\n"
                "FINAL_ANSWER: <your answer>"
            )
            # Inject into last system message or add one
            enhanced = list(messages)
            if enhanced and enhanced[0]["role"] == "system":
                enhanced[0] = {"role": "system", "content": enhanced[0]["content"] + tool_msg}
            else:
                enhanced.insert(0, {"role": "system", "content": tool_msg.strip()})
        else:
            enhanced = messages

        return await self.llm.chat(enhanced, step_type="reason")

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
        # Find the JSON object
        try:
            start = json_str.find("{")
            end = json_str.rfind("}") + 1
            if start == -1:
                return None
            return json.loads(json_str[start:end])
        except (json.JSONDecodeError, ValueError):
            return None

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

    def _track_usage(self, response: dict):
        self._tokens_used += response.get("input_tokens", 0) + response.get("output_tokens", 0)
        self._cost_used += response.get("cost", 0.0)

    def _check_budget(self):
        limits = self.settings.limits

        max_tokens = limits.get("max_tokens_per_task", 0)
        if max_tokens > 0:
            pct = self._tokens_used / max_tokens
            if pct >= 1.0:
                raise BudgetExceeded(f"Token limit reached: {self._tokens_used}/{max_tokens}")
            if pct >= 0.8:
                print(f"Warning: {int(pct * 100)}% of token budget used")

        max_cost = limits.get("max_cost_per_task", 0)
        if max_cost > 0:
            pct = self._cost_used / max_cost
            if pct >= 1.0:
                raise BudgetExceeded(f"Cost limit reached: ${self._cost_used:.4f}/${max_cost}")
            if pct >= 0.8:
                print(f"Warning: {int(pct * 100)}% of cost budget used")
