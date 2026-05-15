import asyncio
import re
from pathlib import Path
from .venv_manager import VenvManager

# Patterns that indicate shell-escape or code-injection risk.
# These are blocked regardless of source to prevent prompt-injection abuse.
_BLOCKED_PATTERNS = [
    re.compile(r"\bos\.system\s*\("),
    re.compile(r"\bsubprocess\b.{0,60}\bshell\s*=\s*True"),
    re.compile(r"\beval\s*\(\s*(?:input|request|user|data)\b"),
    re.compile(r"\bexec\s*\(\s*(?:input|request|user|data)\b"),
    re.compile(r"__import__\s*\(\s*['\"]os['\"]"),
    re.compile(r"\bpty\b|\bpexpect\b"),
    re.compile(r"\bimport\s+pickle\b|__import__\s*\(\s*['\"]pickle['\"]"),
    re.compile(r"\bcompile\s*\("),
    re.compile(r"\bimport\s+ctypes\b|__import__\s*\(\s*['\"]ctypes['\"]"),
    re.compile(r"\bimportlib\.import_module\s*\("),
    re.compile(r"\bimport\s+getpass\b|__import__\s*\(\s*['\"]getpass['\"]"),
    re.compile(r"\binput\s*\("),
]


def _check_code_safety(code: str) -> str | None:
    """Return a description of the first blocked pattern found, or None if safe."""
    for pat in _BLOCKED_PATTERNS:
        if pat.search(code):
            return pat.pattern
    return None


class PythonExecutor:
    TIMEOUT = 30

    def __init__(self, workspace_dir: str, script_tracker=None):
        self.workspace = Path(workspace_dir)
        self.venv = VenvManager(workspace_dir)
        self.tracker = script_tracker  # ScriptTracker | None

    async def run(self, code: str, install_packages: list[str] = None) -> str:
        """
        Write code to temp file, run in .venv, return stdout+stderr.
        Timeout: 30 seconds. Records execution in ScriptTracker.
        """
        blocked = _check_code_safety(code)
        if blocked:
            return f"Error: code blocked by security policy (pattern: {blocked})"

        self.venv.ensure_venv()
        if install_packages:
            self.venv.pip_install(install_packages)

        temp_dir = self.workspace / "workspace" / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)

        script_path = temp_dir / "temp_script.py"
        script_path.write_text(code)

        python = self.venv.get_python()
        success = False
        output = ""
        try:
            proc = await asyncio.create_subprocess_exec(
                python,
                str(script_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.workspace),
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self.TIMEOUT
            )
            output = stdout.decode() + (
                ("\nSTDERR:\n" + stderr.decode()) if stderr else ""
            )
            success = proc.returncode == 0
            return output[:5000]
        except asyncio.TimeoutError:
            proc.kill()
            output = "Error: script timed out after 30 seconds"
            return output
        finally:
            if self.tracker:
                self.tracker.record(
                    lang="python",
                    code=code,
                    success=success,
                    output=output,
                )

    def tool_schema(self) -> dict:
        return {
            "name": "python_exec",
            "description": "Write and execute a Python script. Returns stdout output.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python code to execute",
                    },
                    "install_packages": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "pip packages to install before running",
                    },
                },
                "required": ["code"],
            },
        }
