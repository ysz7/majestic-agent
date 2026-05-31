from dataclasses import dataclass, field
from datetime import datetime, timezone

@dataclass
class TaskMetrics:
    task_id: str
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    tokens_input: int = 0
    tokens_output: int = 0
    cost_usd: float = 0.0
    llm_calls: int = 0
    tool_calls: int = 0

    def add_llm_call(self, input_tokens: int, output_tokens: int, cost: float):
        self.tokens_input += input_tokens
        self.tokens_output += output_tokens
        self.cost_usd += cost
        self.llm_calls += 1

    def add_tool_call(self):
        self.tool_calls += 1

    def duration_s(self) -> float:
        return (datetime.now(timezone.utc) - self.started_at).total_seconds()

    def summary(self) -> str:
        return (
            f"Tokens: {self.tokens_input + self.tokens_output} "
            f"(in: {self.tokens_input}, out: {self.tokens_output}) | "
            f"Cost: ${self.cost_usd:.4f} | "
            f"LLM calls: {self.llm_calls} | "
            f"Tool calls: {self.tool_calls} | "
            f"Time: {self.duration_s():.1f}s"
        )
