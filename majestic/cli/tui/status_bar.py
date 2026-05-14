from textual.widgets import Static


class StatusBar(Static):
    def __init__(self, **kwargs) -> None:
        super().__init__("", **kwargs)
        self._tokens = 0
        self._tokens_limit = 0
        self._cost = 0.0
        self._cost_limit = 0.0
        self._thinking: str = ""

    def set_thinking(self, text: str) -> None:
        self._thinking = text
        self._refresh()

    def set_idle(self) -> None:
        self._thinking = ""
        self._refresh()

    def update_budget(
        self,
        tokens: int,
        tokens_limit: int,
        cost: float,
        cost_limit: float,
    ) -> None:
        self._tokens = tokens
        self._tokens_limit = tokens_limit
        self._cost = cost
        self._cost_limit = cost_limit
        self._refresh()

    def _refresh(self) -> None:
        tok_str = f"{self._tokens:,}"
        tok_lim = str(self._tokens_limit) if self._tokens_limit else "unlimited"
        cost_str = f"${self._cost:.4f}"
        cost_lim = f"${self._cost_limit:.2f}" if self._cost_limit else "unlimited"

        tok_pct = (self._tokens / self._tokens_limit * 100) if self._tokens_limit else 0
        cost_pct = (self._cost / self._cost_limit * 100) if self._cost_limit else 0
        pct = max(tok_pct, cost_pct)

        if pct >= 100:
            budget_color = "red"
        elif pct >= 80:
            budget_color = "yellow"
        else:
            budget_color = "dim"

        budget = (
            f"[{budget_color}]BUDGET[/]  "
            f"tokens {tok_str} / {tok_lim}"
            f"  [dim]·[/dim]  cost {cost_str} / {cost_lim}"
        )

        if self._thinking:
            spinner = "[cyan]⠿[/cyan]"
            content = f" {spinner} [dim]{self._thinking}[/dim]  [dim]│[/dim]  {budget}"
        else:
            content = f"  {budget}"

        self.update(content)
