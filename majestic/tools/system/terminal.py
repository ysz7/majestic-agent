"""System terminal tool — execute shell commands with timeout + user approval."""
from majestic.tools.registry import tool

_TIMEOUT = 30
_BLOCKED = {"rm -rf /", ":(){ :|:& };:", "mkfs", "dd if=/dev/zero"}


def _is_allowed(base: str) -> bool:
    """Return True if base command is in the allowed_commands list or all commands allowed."""
    from majestic import config as _cfg
    if _cfg.get("agent.allow_commands", False):
        return True
    allowed = _cfg.get("agent.allowed_commands") or []
    return base in allowed


def _save_allowed(base: str) -> None:
    """Append base command to agent.allowed_commands in config."""
    from majestic import config as _cfg
    current = list(_cfg.get("agent.allowed_commands") or [])
    if base not in current:
        current.append(base)
        _cfg.set_value("agent.allowed_commands", current)


def _request_approval(command: str, base: str) -> str | None:
    """Ask the user for approval. Returns None if approved, else denial message."""
    import sys
    if not sys.stdin.isatty():
        return (
            f"Command blocked (non-interactive mode): {command!r}. "
            f"Add '{base}' to agent.allowed_commands or set agent.allow_commands: true in config."
        )
    try:
        from majestic.cli.repl_helpers import pause_active_spinner, resume_active_spinner
        pause_active_spinner()
    except Exception:
        pass
    sys.__stdout__.write(f"\n  [approve] {command!r}\n  Allow? [y / N / always] ")
    sys.__stdout__.flush()
    try:
        answer = sys.__stdin__.readline().strip().lower()
    except EOFError:
        answer = "n"
    finally:
        try:
            from majestic.cli.repl_helpers import resume_active_spinner
            resume_active_spinner()
        except Exception:
            pass
    if answer == "always":
        _save_allowed(base)
        return None
    if answer == "y":
        return None
    return f"Command denied by user: {command!r}"


@tool(
    name="run_command",
    description=(
        "Execute a shell command and return its output. "
        "Use for system tasks: listing files, running scripts, checking processes, etc. "
        "Commands have a 30-second timeout."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Shell command to execute",
            },
        },
        "required": ["command"],
    },
)
def run_command(command: str) -> str:
    import subprocess

    cmd_lower = command.lower()
    for blocked in _BLOCKED:
        if blocked in cmd_lower:
            return f"Command blocked for safety: {command!r}"

    base = command.strip().split()[0] if command.strip() else ""
    if not _is_allowed(base):
        denial = _request_approval(command, base)
        if denial:
            return denial

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
        output = result.stdout + result.stderr
        if not output.strip():
            return f"Command exited with code {result.returncode} (no output)"
        return output[:4000]
    except subprocess.TimeoutExpired:
        return f"Command timed out after {_TIMEOUT}s: {command!r}"
    except Exception as e:
        return f"Error running command: {e}"
