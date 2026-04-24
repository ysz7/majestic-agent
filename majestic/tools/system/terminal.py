"""System terminal tool — execute shell commands with timeout."""
from majestic.tools.registry import tool

_TIMEOUT = 30
_BLOCKED = {"rm -rf /", ":(){ :|:& };:", "mkfs", "dd if=/dev/zero"}


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
