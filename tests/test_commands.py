"""Slash-command registry + dispatcher (B1 refactor)."""
import asyncio


class _Runtime:
    _tokens_used = 4200
    _cost_used = 0.0123
    tools = {"web_search": 1, "http": 1}


class _WorkingMemory:
    def __init__(self):
        self.cleared = False

    def clear(self):
        self.cleared = True


def _ctx(text):
    from majestic.cli.commands import CommandContext
    return CommandContext(
        text=text, profile_name="default",
        working_memory=_WorkingMemory(), runtime=_Runtime(),
    )


def test_simple_commands_registered():
    from majestic.cli.commands import registered
    for c in ["/help", "/skills", "/tools", "/agents", "/memory", "/budget", "/new"]:
        assert c in registered(), f"{c} not registered"


def test_dispatch_known_returns_true():
    from majestic.cli.commands import dispatch
    for c in ["/help", "/tools", "/budget"]:
        assert asyncio.run(dispatch(_ctx(c))) is True, c


def test_dispatch_unknown_returns_none():
    from majestic.cli.commands import dispatch
    # Unknown command → None so the caller falls through to skills/agent
    assert asyncio.run(dispatch(_ctx("/does-not-exist"))) is None


def test_new_clears_working_memory():
    from majestic.cli.commands import dispatch, CommandContext
    wm = _WorkingMemory()
    ctx = CommandContext(text="/new", profile_name="default",
                         working_memory=wm, runtime=_Runtime())
    assert asyncio.run(dispatch(ctx)) is True
    assert wm.cleared is True


if __name__ == "__main__":
    test_simple_commands_registered()
    test_dispatch_known_returns_true()
    test_dispatch_unknown_returns_none()
    test_new_clears_working_memory()
    print("All command tests passed!")
