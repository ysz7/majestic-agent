from textual.message import Message


class UserMessage(Message):
    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


class AgentToken(Message):
    def __init__(self, token: str) -> None:
        super().__init__()
        self.token = token


class AgentDone(Message):
    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


class ToolCallEvent(Message):
    def __init__(self, tool_name: str, args_preview: str = "") -> None:
        super().__init__()
        self.tool_name = tool_name
        self.args_preview = args_preview


class InfoEvent(Message):
    def __init__(self, text: str, level: str = "info") -> None:
        super().__init__()
        self.text = text
        self.level = level  # "info" | "ok" | "warn" | "err"


class SpinnerStart(Message):
    def __init__(self, text: str = "Thinking...") -> None:
        super().__init__()
        self.text = text


class SpinnerStop(Message):
    pass


class BudgetUpdate(Message):
    def __init__(
        self,
        tokens: int,
        tokens_limit: int,
        cost: float,
        cost_limit: float,
    ) -> None:
        super().__init__()
        self.tokens = tokens
        self.tokens_limit = tokens_limit
        self.cost = cost
        self.cost_limit = cost_limit


class TaskReport(Message):
    def __init__(self, steps: int, tokens: int, cost: float, elapsed: float) -> None:
        super().__init__()
        self.steps = steps
        self.tokens = tokens
        self.cost = cost
        self.elapsed = elapsed
