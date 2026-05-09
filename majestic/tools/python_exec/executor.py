import asyncio
from pathlib import Path
from .venv_manager import VenvManager


class PythonExecutor:
    TIMEOUT = 30

    def __init__(self, workspace_dir: str):
        self.workspace = Path(workspace_dir)
        self.venv = VenvManager(workspace_dir)

    async def run(self, code: str, install_packages: list[str] = None) -> str:
        """
        Write code to temp file, run in .venv, return stdout+stderr.
        Timeout: 30 seconds.
        """
        self.venv.ensure_venv()
        if install_packages:
            self.venv.pip_install(install_packages)

        tools_dir = self.workspace / "workspace" / "tools"
        tools_dir.mkdir(parents=True, exist_ok=True)

        script_path = tools_dir / "temp_script.py"
        script_path.write_text(code)

        python = self.venv.get_python()
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
            return output[:5000]
        except asyncio.TimeoutError:
            proc.kill()
            return "Error: script timed out after 30 seconds"

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
